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
litmus check examples/metrics/
litmus parse examples/metrics/revenue.metric        # debug: dump parsed MetricSpec
litmus explain examples/metrics/revenue.metric      # plain-English doc
litmus report examples/metrics/ -f html -o out.html
litmus import-dbt path/to/target/manifest.json
```

CI (`.github/workflows/ci.yml`) runs lint → pytest-with-coverage → mypy across Python 3.10/3.11/3.12, then builds the package.

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

`runner.run_checks(connector, spec)` iterates the rules on `spec.trust` and dispatches to per-rule check functions in `freshness.py`, `null_rate.py`, `volume.py`, `range.py`. Each check returns a `CheckResult(status, message, actual_value, threshold, …)`; the suite returns a `CheckSuite` with `passed/warnings/failed/errors` counts and a `trust_score` (warnings count as 0.5).

Status values: `PASSED`, `WARNING` (within 90% of limit, see `WARNING_THRESHOLD` in `freshness.py`), `FAILED`, `ERROR` (connector blew up). Change rules (`change_rules`) are currently stubbed to always-PASSED — they need historical value storage to implement properly.

Conventions baked into the runner that matter when adding checks:
- The **primary table** is `spec.sources[0]` — volume/null/range default to it unless a rule specifies otherwise.
- Default timestamp column is `"updated_at"`, default value column is `"amount"`. These are hardcoded defaults and the only way to override them today is via the `timestamp_column` / `value_column` params to `run_checks`.

### 4. `litmus/connectors/` — warehouse abstraction

`base.BaseConnector` is the ABC every warehouse must implement: `connect`, `execute_query`, `get_table_freshness`, `get_row_count`, `get_null_rate`, `get_column_sum`, `close`. Implementations: `duckdb.py` (zero-config default), `postgres.py`, `snowflake.py`, `bigquery.py`. Optional deps are gated via `[postgres]` / `[snowflake]` / `[bigquery]` / `[all]` extras in `pyproject.toml`.

Connectors are constructed by `config.settings.get_connector(cfg)` based on `warehouse.type`. Credentials are **read from env vars** `LITMUS_WAREHOUSE_USER` / `LITMUS_WAREHOUSE_PASSWORD` (via `WarehouseConfig.user` / `.password` properties) — never put them in `litmus.yml`.

### 5. `litmus/reporters/` and `litmus/generators/`

- `reporters/` — `console.py` (Rich-based, the default), `html_reporter.py`, `json_reporter.py`, `markdown_reporter.py`. All consume `list[tuple[MetricSpec, CheckSuite]]`.
- `generators/plain_english.py` — powers `litmus explain` (business-friendly docs from a spec).
- `generators/sql_generator.py` — lowers a `MetricSpec` to SQL.
- `generators/dbt_importer.py` — reads `manifest.json`, extracts the dbt semantic-layer `metrics` section (falls back to `nodes` of type `model`), and emits `.metric` files with `TODO` markers for business context.

### CLI wiring (`litmus/cli.py`)

Single-file Click app with subcommands `init`, `check`, `parse`, `explain`, `import-dbt`, `report`. Heavy imports (connectors, reporters, generators) are done **lazily inside each command** to keep `litmus --help` fast — preserve that pattern when adding subcommands.

Exit code contract: `litmus check` exits `1` if **any** suite has `failed > 0` or `errors > 0`; warnings alone don't fail the run.

## Tests

- `tests/conftest.py` provides the shared fixtures: `test_db` (in-memory DuckDB seeded with an `orders` table — schema is documented in the fixture docstring), `sample_metric_text`, `sample_metric_file`.
- Layout mirrors the source tree: `tests/test_parser/`, `tests/test_checks/`, `tests/test_generators/`, `tests/test_reporters/`, plus top-level `test_cli.py`.
- Prefer using the `test_db` fixture over mocking the connector — checks are I/O-bound on real SQL and mocks hide bugs.

## Conventions

- `ruff` with `target-version = "py310"`, `line-length = 100`, rulesets `E, F, I, N, W, UP` (pyproject.toml). `from __future__ import annotations` is used throughout.
- `mypy` is run but `--ignore-missing-imports` in CI — don't rely on strict typing of third-party libs.
- Warehouse credentials via env vars only (see above).
- When adding a new trust rule: touch `lexer.py`, `ast_nodes.py`, `parser.py` (`_parse_trust_rule`), `spec/metric_spec.py`, `checks/runner.py`, a new `checks/<rule>.py`, and at least one reporter + `generators/plain_english.py` so `explain` stays in sync.
