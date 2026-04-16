# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-04-16

Initial public release.

### Added

- BDD-style `.metric` DSL with `Metric` / `Description` / `Owner` / `Tags` /
  `Source` headers, `Given` filter conditions, `When we calculate` /
  `Then` computation steps, `The result is ...` output, and an optional
  `Trust:` block — all parsed by a hand-rolled lexer + recursive-descent
  parser that lowers to a typed `MetricSpec` dataclass.
- Nine built-in trust check types: **freshness**, **null rate**, **volume**
  (row count drop), **range** (value bounds), **change** (period-over-period
  anomaly), **duplicate rate**, **schema drift**, **distribution shift**,
  and a **custom SQL** check. Results include `PASSED` / `WARNING` /
  `FAILED` / `ERROR` statuses and a per-metric trust score.
- SQLite-backed history store (`~/.litmus/history.db` by default, overridable
  via `LITMUS_HISTORY_DB` or `--history-db`) so change-based rules can
  compare against prior runs.
- Warehouse connectors behind a single `BaseConnector` ABC: **DuckDB**
  (default, zero-config), **SQLite**, **PostgreSQL** (`[postgres]` extra),
  **Snowflake** (`[snowflake]` extra), and **BigQuery** (`[bigquery]` extra).
  Credentials are read from `LITMUS_WAREHOUSE_USER` /
  `LITMUS_WAREHOUSE_PASSWORD` env vars only.
- `litmus` CLI with subcommands: `init`, `check`, `parse`, `explain`,
  `import-dbt`, `export`, `share`, and `report`.
- Reporters: Rich-powered console (default), JSON (versioned schema),
  HTML, and Markdown.
- Generators: `plain_english` (powers `litmus explain`), `sql_generator`
  (lowers a `MetricSpec` to SQL), `dbt_importer` (reads dbt
  `manifest.json` into `.metric` files), `dbt_exporter` adapter, and a
  shareable self-contained HTML artefact via `litmus share`.
- GitHub Action (`action.yml`) — composite action that runs `litmus check`
  on pull requests and emits `report-json`, `trust-score`, and
  `summary-markdown` outputs for PR comments.
- Example metrics in `examples/` and documentation in `docs/` (spec
  language, JSON schema, getting started).

[Unreleased]: https://github.com/zinnoberHaus/litmus/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/zinnoberHaus/litmus/releases/tag/v0.1.0
