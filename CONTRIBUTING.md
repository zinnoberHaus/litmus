# Contributing to Litmus

Thanks for taking the time to improve Litmus. This guide covers the dev setup, the project layout, and the rules we keep PRs to.

## Dev environment

Litmus targets **Python 3.10+** and uses a standard editable install.

```bash
git clone https://github.com/zinnoberHaus/litmus.git
cd litmus
make dev          # pip install -e ".[dev]"
```

`make dev` installs the runtime deps plus `pytest`, `pytest-cov`, `ruff`, and `mypy`. Warehouse extras (`[postgres]`, `[snowflake]`, `[bigquery]`, `[all]`) are opt-in — you only need them if you're working on that connector.

Warehouse credentials, when you need them, live in environment variables only:

```bash
export LITMUS_WAREHOUSE_USER=...
export LITMUS_WAREHOUSE_PASSWORD=...
```

Never commit credentials into `litmus.yml`.

## Running tests

```bash
make test                              # pytest tests/ -v --tb=short
make test-cov                          # adds --cov=litmus --cov-report=term-missing

pytest tests/test_parser/test_parser.py           # single file
pytest tests/test_parser/test_parser.py::test_X   # single test
pytest -k "freshness"                             # by keyword
```

The shared `test_db` fixture in `tests/conftest.py` spins up an in-memory DuckDB with an `orders` table. Prefer it over mocking the connector — checks are I/O bound and mocks hide real bugs.

## Linting and formatting

```bash
make lint      # ruff check + mypy on litmus/
make format    # ruff format + ruff check --fix
```

Before pushing:

```bash
make check     # lint + test — CI runs the same thing
```

CI (`.github/workflows/ci.yml`) runs lint, pytest-with-coverage, and mypy on Python 3.10 / 3.11 / 3.12, then builds the package. If it fails locally, it will fail in CI.

## Project layout

The codebase is a four-stage pipeline. Each stage maps to one top-level subpackage under `litmus/`:

```
.metric file  ->  parser/  ->  spec/MetricSpec  ->  checks/runner  ->  reporters/
                                                          |
                                                          v
                                                     connectors/  (warehouse I/O)
```

- **`litmus/parser/`** — hand-rolled lexer + recursive-descent parser. Lowers text to AST, then to `MetricSpec`.
- **`litmus/spec/`** — `MetricSpec` and `TrustSpec` dataclasses. The boundary everything downstream consumes.
- **`litmus/checks/`** — `runner.run_checks()` plus one module per rule type.
- **`litmus/connectors/`** — `BaseConnector` ABC + DuckDB / SQLite / Postgres / Snowflake / BigQuery implementations.
- **`litmus/reporters/`** — console (default), HTML, Markdown, JSON.
- **`litmus/generators/`** — `plain_english` (powers `litmus explain`), `sql_generator`, `dbt_importer`, `dbt_exporter`, `share_html`.
- **`litmus/cli.py`** — single Click app. Heavy imports are deferred inside each subcommand to keep `--help` fast; preserve that pattern.

## Adding a new Trust rule

Every new rule touches roughly the same seven files:

1. `litmus/parser/lexer.py` — add a `TokenType` and a regex in `_LINE_PATTERNS` (order matters: put more specific patterns first).
2. `litmus/parser/ast_nodes.py` — add the AST node.
3. `litmus/parser/parser.py` — wire it into `_parse_trust_rule`.
4. `litmus/spec/metric_spec.py` — add the dataclass on `TrustSpec`.
5. `litmus/checks/<rule>.py` — the actual check, returning a `CheckResult`.
6. `litmus/checks/runner.py` — dispatch from `run_checks`.
7. `litmus/generators/plain_english.py` — so `litmus explain` still matches the DSL.

Add tests under the mirroring `tests/` directory (for example `tests/test_checks/test_<rule>.py`) and update at least the console reporter if the output shape is new.

## Pull requests

- **One feature per PR.** Keep diffs focused; split refactors from behaviour changes.
- **Tests are required** for any parser, check, or connector change. Use real fixtures over mocks where you can.
- **Update `CHANGELOG.md`** under `## [Unreleased]` with a short user-facing line describing the change.
- **Pass `make check` locally** before pushing.
- **Docstrings** — public functions and new DSL surface need at least a short docstring.
- **Don't invent features in the README.** If you add a subcommand or rule, update `README.md` and `docs/` in the same PR.

## Reporting bugs and requesting features

Use the issue templates under `.github/ISSUE_TEMPLATE/` — they keep triage fast. When filing a bug, include the Litmus version (`litmus --version`), the warehouse type, and the smallest `.metric` file that reproduces the problem.

## Code of conduct

By participating, you agree to abide by the [Contributor Covenant](CODE_OF_CONDUCT.md).
