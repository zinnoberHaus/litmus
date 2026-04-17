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

Single-file Click app with subcommands `init`, `check`, `parse`, `explain`, `import-dbt`, `export`, `report`, `share`. Heavy imports (connectors, reporters, generators, history) are done **lazily inside each command** to keep `litmus --help` fast — preserve that pattern when adding subcommands.

Exit code contract: `litmus check` exits `1` if **any** suite has `failed > 0` or `errors > 0`; warnings alone don't fail the run. The reusable GitHub Action (`action.yml`) layers an optional `fail-on-warning` flag on top — if you change the exit-code contract, update the action too.

## Tests

- `tests/conftest.py` provides the shared fixtures: `test_db` (in-memory DuckDB seeded with an `orders` table — schema is documented in the fixture docstring), `sample_metric_text`, `sample_metric_file`.
- Layout mirrors the source tree: `tests/test_parser/`, `tests/test_checks/`, `tests/test_generators/`, `tests/test_reporters/`, plus top-level `test_cli.py`.
- Prefer using the `test_db` fixture over mocking the connector — checks are I/O-bound on real SQL and mocks hide bugs.

## Conventions

- `ruff` with `target-version = "py310"`, `line-length = 100`, rulesets `E, F, I, N, W, UP` (pyproject.toml). `make lint` runs `ruff check litmus/ tests/` + `mypy litmus/`. `from __future__ import annotations` is used throughout.
- `mypy` is run but `--ignore-missing-imports` in CI — don't rely on strict typing of third-party libs.
- Warehouse credentials and the history DB location are via env vars only (`LITMUS_WAREHOUSE_USER`, `LITMUS_WAREHOUSE_PASSWORD`, `LITMUS_HISTORY_DB`).
- When adding a new trust rule: touch `lexer.py`, `ast_nodes.py`, `parser.py` (`_parse_trust_rule`), `spec/metric_spec.py`, `checks/runner.py`, a new `checks/<rule>.py`, every reporter (console/json/html/markdown), `generators/plain_english.py` so `explain` stays in sync, and — if the JSON shape changes — a new version under `schemas/`. Stateful rules additionally need a column in `checks/history.py` and an `ALTER TABLE` migration.
