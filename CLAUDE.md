# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

**Litmus** — BDD-style metric definitions with built-in data trust checks. Users write `.metric` files in a Gherkin-inspired plain-English DSL (Given/When/Then + a Trust block), and the CLI runs automated data-quality checks against a warehouse.

Package published on PyPI as **`litmus-data`**; the import name and CLI entry point are **`litmus`** (`litmus.cli:main`). Python **3.10+**.

## Common commands

```bash
make dev                  # pip install -e ".[dev]"
make test                 # pytest tests/ -v --tb=short
make test-cov             # same, with --cov=litmus --cov-report=term-missing
make lint                 # ruff check + mypy on litmus/
make format               # ruff format + ruff check --fix
make check                # lint + test (used before committing)

# Run a single test / single file / single test node
pytest tests/test_parser/test_parser.py
pytest tests/test_parser/test_parser.py::test_name -v
pytest -k "freshness"

# Exercise the CLI end-to-end against the bundled examples
litmus check examples/metrics/                      # run trust checks against a warehouse
litmus check examples/metrics/ --no-history         # skip SQLite history writes (disables change/drift rules)
litmus parse examples/metrics/revenue.metric        # debug: dump parsed MetricSpec
litmus explain examples/metrics/revenue.metric      # plain-English doc
litmus report examples/metrics/ -f html -o out.html
litmus share examples/metrics/                      # self-contained HTML dashboard
litmus export examples/metrics/ dbt -o exports/     # emit dbt tests/sources
litmus import-dbt path/to/target/manifest.json
```

CI (`.github/workflows/ci.yml`) runs lint → pytest-with-coverage → mypy across Python 3.10/3.11/3.12, then builds the package. `release.yml` publishes to PyPI; `examples.yml` smoke-tests the bundled examples; `action.yml` at the repo root publishes Litmus as a reusable **GitHub Action** ("Litmus check") — changes to check behavior or CLI flags must keep that action's contract intact (`inputs.path`, `inputs.config`, `fail-on-warning`, `outputs.report-json`).

## Architecture

The flow through the codebase is a **four-stage pipeline**, and each stage corresponds to one top-level subpackage under `litmus/`. Understanding the handoff between stages is the fastest way to get productive:

```
.metric file  ──▶  parser/  ──▶  spec/MetricSpec  ──▶  checks/runner  ──▶  reporters/
                                                              │
                                                              ▼
                                                        connectors/  (warehouse I/O)
```

### 1. `litmus/parser/` — `.metric` → `MetricSpec`

Hand-rolled lexer + recursive-descent parser, **not** PLY/Lark.

- `lexer.py` — line-oriented tokenizer. Each non-blank line is matched against ordered regexes in `_LINE_PATTERNS` (order matters: more specific patterns must come first). Produces `Token(type, value, line)`.
- `ast_nodes.py` — dataclass AST (`HeaderNode`, `GivenBlock`, `WhenBlock`, `TrustBlock`, and rule nodes like `FreshnessRuleNode`, `NullRuleNode`, `VolumeRuleNode`, `RangeRuleNode`, `ChangeRuleNode`).
- `parser.py` — `_Parser.parse()` enforces the fixed section order `Header → Source → Given → When → Result → Trust?`. Trust rules are then re-parsed line-by-line using regex inside `_parse_trust_rule`. The top-level entrypoints `parse_metric_file` / `parse_metric_string` **lower the AST to a `MetricSpec`** — downstream code only sees `MetricSpec`, never AST nodes.
- `errors.py` — typed parse errors (`MissingHeaderError`, `MissingSectionError`, `UnexpectedTokenError`, `InvalidTrustRuleError`).

When extending the DSL: add a `TokenType` + regex in `lexer.py`, add an AST node in `ast_nodes.py`, wire up parsing in `parser.py`, and mirror the shape in `spec/metric_spec.py`.

### 2. `litmus/spec/` — the shared data model

`metric_spec.py` defines `MetricSpec` and `TrustSpec` (plus `FreshnessRule`, `NullRule`, `VolumeRule`, `RangeRule`, `ChangeRule`). **This is the boundary between parsing and everything else** — all downstream code (checks, reporters, generators) consumes `MetricSpec`, never touches the AST or raw tokens.

### 3. `litmus/checks/` — trust validation

`runner.run_checks(connector, spec, history=...)` iterates the rules on `spec.trust` and dispatches to per-rule check functions. Each check returns a `CheckResult(status, message, actual_value, threshold, …)`; the suite returns a `CheckSuite` with `passed/warnings/failed/errors` counts and a `trust_score` (warnings count as 0.5).

Current check modules:
- **Stateless (current-run only):** `freshness.py`, `null_rate.py`, `volume.py`, `range.py`, `duplicate_rate.py`, `custom.py` (user-supplied SQL assertions).
- **Stateful (compare against history):** `change.py`, `schema_drift.py`, `distribution_shift.py` — these consult the `HistoryStore` in `history.py` and need prior runs to do anything useful. On first run they typically return `PASSED` with a "baseline recorded" message.

Status values: `PASSED`, `WARNING` (within 90% of limit, see `WARNING_THRESHOLD` in `freshness.py`), `FAILED`, `ERROR` (connector blew up).

Conventions baked into the runner that matter when adding checks:
- The **primary table** is `spec.sources[0]` — all per-table checks default to it.
- Default timestamp column is `"updated_at"`, default value column is `"amount"`. Overrides are passed via `timestamp_column` / `value_column` params to `run_checks`.
- The runner computes `current_value = connector.get_column_sum(primary_table, v_col)` and `current_columns = connector.get_columns(primary_table)` **once** and threads them into change/drift checks and the history write. If you add a new stateful check, reuse these — don't re-query.
- History writes are wrapped in `try/except pass`: **a history-write failure must never break a check run**. Preserve this when touching the runner.

### 3b. `litmus/checks/history.py` — SQLite history store

Backs every cross-run check (`change_rules`, `schema_drift`, `distribution_shift_rules`). Schema is auto-migrated via `ALTER TABLE`, so adding a new column for a future rule type is the expected extension pattern. Default DB path is `~/.litmus/history.db`, overridable via `$LITMUS_HISTORY_DB` or the `--history-db` flag. Columns: `metric_name, value_sum, row_count, recorded_at, run_id, commit_sha, schema_fingerprint, column_means_json`. `run_id` / `commit_sha` are plumbed from CI env vars — keep them optional.

### 4. `litmus/connectors/` — warehouse abstraction

`base.BaseConnector` is the ABC every warehouse must implement: `connect`, `execute_query`, `get_table_freshness`, `get_row_count`, `get_null_rate`, `get_column_sum`, `get_column_mean`, `get_columns`, `close`. Implementations: `duckdb.py` (zero-config default), `sqlite.py`, `postgres.py`, `snowflake.py`, `bigquery.py`. Optional deps are gated via `[postgres]` / `[snowflake]` / `[bigquery]` / `[all]` extras in `pyproject.toml` — DuckDB and SQLite need no extras.

Connectors are constructed by `config.settings.get_connector(cfg)` based on `warehouse.type`. Credentials are **read from env vars** `LITMUS_WAREHOUSE_USER` / `LITMUS_WAREHOUSE_PASSWORD` (via `WarehouseConfig.user` / `.password` properties) — never put them in `litmus.yml`.

### 5. `litmus/reporters/` and `litmus/generators/`

- `reporters/` — `console.py` (Rich-based, the default), `html_reporter.py`, `json_reporter.py`, `markdown_reporter.py`. All consume `list[tuple[MetricSpec, CheckSuite]]`. The JSON reporter's output is versioned — the canonical schema lives at `schemas/v1/check-suite.schema.json` and is selected via `litmus check --schema-version v1`. **Any change to the JSON shape requires a new schema version**, not an in-place edit of `v1`.
- `generators/plain_english.py` — powers `litmus explain` (business-friendly docs from a spec).
- `generators/sql_generator.py` — lowers a `MetricSpec` to SQL.
- `generators/dbt_importer.py` / `dbt_exporter.py` — the inbound path reads a dbt `manifest.json` (semantic-layer `metrics` section, falls back to `nodes` of type `model`) and emits `.metric` files with `TODO` markers; the outbound path turns `.metric` files into dbt tests/sources (used by `litmus export ... dbt`).
- `generators/share_html.py` + `generators/assets/` — powers `litmus share`, a single-file HTML dashboard intended to be hosted publicly (e.g. GitHub Pages).

### CLI wiring (`litmus/cli.py`)

Single-file Click app with subcommands `init`, `check`, `parse`, `explain`, `explain-run`, `import-dbt`, `export`, `report`, `share`. Heavy imports (connectors, reporters, generators, history) are done **lazily inside each command** to keep `litmus --help` fast — preserve that pattern when adding subcommands.

Exit code contract: `litmus check` exits `1` if **any** suite has `failed > 0` or `errors > 0`; warnings alone don't fail the run. The reusable GitHub Action (`action.yml`) layers an optional `fail-on-warning` flag on top — if you change the exit-code contract, update the action too.

### 6. `litmus_api/` — FastAPI catalog + embeddable badges (v0.2 wedge)

Separate package next to `litmus/`. Provides the hosted metric catalog, run history, and embeddable trust-badge SVG that the CLI can push to. Install with the `[server]` extras.

Schema is managed by **Alembic**, not `create_all`:

```bash
# Prod / shared DBs: run migrations explicitly before the server starts
alembic -c litmus_api/migrations/alembic.ini upgrade head

# Dev convenience: auto-apply on app startup
LITMUS_AUTO_MIGRATE=true uvicorn litmus_api.main:app
```

- `litmus_api/main.py::init_schema()` — precedence is (1) in-memory SQLite → `create_all` (tests only), (2) `LITMUS_AUTO_MIGRATE=true` → `alembic upgrade head`, (3) default → do nothing (ops run migrations as a separate deploy step).
- `litmus_api/migrations/` — `alembic.ini`, `env.py` (reads URL from `Settings().database_url`), and `versions/0001_initial_schema.py`, `versions/0002_metric_revisions.py`. Use `alembic revision --autogenerate -m "..."` to generate new migrations; **review the output** — autogenerate misses ENUM changes, CHECK constraints, and index renames.
- Models (`litmus_api/models/__init__.py`): `Org`, `ApiKey`, `Metric`, `MetricRevision`, `Run`, `CheckResult`, `RunExplanation`, `EmbedKey`.
- `MetricRevision` is append-only. `POST /api/v1/metrics` writes a new revision only when the submitted `spec_text` differs from the latest stored revision — identical re-upserts (common in CI) are deduped. `GET /api/v1/metrics/{id}/revisions` returns up to 30 entries, **oldest-last** so clients can render a top-to-bottom timeline without reversing. `MetricOut.revision_count` reflects the total on every response.
- `tests/test_api/conftest.py` deliberately skips Alembic — it calls `Base.metadata.create_all` directly so each test gets a fresh DB in milliseconds. `tests/test_api/test_migrations.py` locks in the invariant that `alembic upgrade head` and `create_all` produce identical schemas.

#### Webhook ingestion

`POST /webhooks/github` (mounted at the root, not under `/api/v1`) accepts GitHub `push` events and upserts any added/modified `.metric` files into the catalog. The route verifies `X-Hub-Signature-256` against `LITMUS_GITHUB_WEBHOOK_SECRET` (env var, required — an unset secret returns 401, never silently accepts). Non-`push` events return `{"status":"ignored"}`. Files are fetched from `raw.githubusercontent.com` using stdlib `urllib.request`, so the feature works only for **public repos** — private repos would need a GitHub App OAuth flow which the OSS wedge deliberately does not ship. Setup steps live in `docs/github-webhook.md`. Both the HTTP route (`POST /api/v1/metrics`) and the webhook share `_perform_upsert(session, org, payload)` in `litmus_api/routes/metrics.py`, so a `.metric` edit lands the same way whether it came in via `litmus check --push` or a `git push`.

#### dbt lineage

Two endpoints on `/api/v1/metrics/{id}/lineage`:

- **POST** `{nodes, edges}` replaces the stored subgraph atomically (delete + re-insert), keeping `litmus import-dbt --push` idempotent. Node kinds are `"source" | "model" | "metric"`.
- **GET** returns the stored graph, or a 2-node spec-derived stub (`source.primary_table → metric.name`) when nothing has been imported yet, so the UI never renders an empty lineage block.

`litmus/generators/dbt_importer.py::build_lineage(manifest, metric_name)` walks the manifest's `parent_map` up to **3 hops** upstream and returns a `Lineage(nodes, edges)` dataclass. The CLI's `litmus import-dbt --push --endpoint <url> [--api-key ...]` flow writes local `.metric` files first (authoritative), then upserts each metric and POSTs its lineage to the server. The transport reuses `litmus/api_push.py`'s stdlib-urllib helper, so `import-dbt` stays zero-dependency.

### AI run explanations (`litmus_api/ai/`)

Optional, opt-in-per-install feature for the hosted server. `litmus_api/ai/explain.py` exposes `explain_run(session, run_id)` which asks Claude Sonnet 4.6 for a one-paragraph hypothesis + suggested action when a run fails or errors. Uses the `anthropic` SDK (gated behind the `[ai]` extras — not pulled into `[server]`), forced tool-use for a hard output contract, and upserts a `RunExplanation` row so repeat reads are free. The feature is triggered exclusively by `POST /api/v1/runs/{id}/explain` (CLI: `litmus explain-run <id> --endpoint ...`); it never runs on ingestion and never explains passed/warning runs. **Privacy disclosure:** the prompt includes metric metadata, trust rules, current `CheckResult` rows, and the last 5 runs' aggregates — never raw warehouse rows or SQL. Full details in `docs/ai-explanations.md`. If `LITMUS_ANTHROPIC_API_KEY` (or `ANTHROPIC_API_KEY`) is unset, the route returns 500 "not configured" and the UI gracefully shows a muted fallback instead of a crash.

## Tests

- `tests/conftest.py` provides the shared fixtures: `test_db` (in-memory DuckDB seeded with an `orders` table — schema is documented in the fixture docstring), `sample_metric_text`, `sample_metric_file`.
- Layout mirrors the source tree: `tests/test_parser/`, `tests/test_checks/`, `tests/test_generators/`, `tests/test_reporters/`, plus top-level `test_cli.py`.
- Prefer using the `test_db` fixture over mocking the connector — checks are I/O-bound on real SQL and mocks hide bugs.

## Conventions

- `ruff` with `target-version = "py310"`, `line-length = 100`, rulesets `E, F, I, N, W, UP` (pyproject.toml). `make lint` runs `ruff check litmus/ tests/` + `mypy litmus/`. `from __future__ import annotations` is used throughout.
- `mypy` is run but `--ignore-missing-imports` in CI — don't rely on strict typing of third-party libs.
- Warehouse credentials and the history DB location are via env vars only (`LITMUS_WAREHOUSE_USER`, `LITMUS_WAREHOUSE_PASSWORD`, `LITMUS_HISTORY_DB`).
- When adding a new trust rule: touch `lexer.py`, `ast_nodes.py`, `parser.py` (`_parse_trust_rule`), `spec/metric_spec.py`, `checks/runner.py`, a new `checks/<rule>.py`, every reporter (console/json/html/markdown), `generators/plain_english.py` so `explain` stays in sync, and — if the JSON shape changes — a new version under `schemas/`. Stateful rules additionally need a column in `checks/history.py` and an `ALTER TABLE` migration.
