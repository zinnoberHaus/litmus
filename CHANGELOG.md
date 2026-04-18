# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.0] - 2026-04-18

The three-audience release. Litmus now serves engineers (canonical metric
contracts), PMs (AI-answered questions + Slack sign-off), and viewers
(embeddable trust badges) from a single source of truth.

### Added

- **dbt package** (`dbt_packages/litmus/`) — Elementary-style integration.
  An `on-run-end` macro materialises trust verdicts into
  `{schema}_litmus.litmus_runs` / `litmus_check_results` / `litmus_history`
  in the warehouse. The Python CLI auto-detects a dbt project and reads /
  writes those same tables via a new `WarehouseHistoryStore` — drop-in
  replacement for the SQLite `HistoryStore`. Override with
  `litmus check --backend {sqlite,warehouse,auto}` and
  `--history-schema <schema>`. Adapter dispatch covers DuckDB, Postgres,
  Snowflake, and BigQuery. Full guide in `docs/dbt-package.md`.
- **YAML alternative to `.metric`** — both `.metric` (Gherkin DSL) and
  `.yaml` / `.yml` files now lower to the same `MetricSpec`. Round-trip
  parity is CI-enforced. See `examples/metrics/revenue.yaml` and the new
  "YAML alternative" section in `docs/spec-language.md`.
- **AI Q&A bot** (`litmus_api/ai/ask.py`, `[ai]` extras) — answers PM
  questions like "what was revenue last month?" by resolving
  `{metric_slug, time_window, filters}` via Claude Sonnet 4.6 forced
  tool-use, templating SQL server-side from the stored `MetricSpec`, and
  returning a natural-language answer with a trust clause. Two surfaces:
  `POST /api/v1/ask` (for the UI and CLI) and an `app_mention` Slack
  handler. **Privacy bright line**: Claude never generates SQL or sees
  warehouse rows — only catalog metadata + the question. Documented in
  `docs/ai-ask.md`.
- **Slack sign-off workflow** (`litmus_api/slack/`) — webhook-only MVP
  (full Slack App distribution deferred to v0.4). Routes under
  `/api/v1/slack/{events,commands,interactions,signoff/request}` with
  HMAC-SHA256 request verification and a 5-minute replay window.
  `MetricRevision` now carries `signoff_required`, `signoff_status`,
  `signoff_by`, `signoff_at`, `signoff_reason`, `slack_message_ts`, and
  `slack_channel_id` (Alembic `0006_slack_signoff`). Fires on upsert when
  `signoff_required=True` or `LITMUS_SLACK_SIGNOFF_ALL=true` — Slack
  failures never break the catalog write. Env vars documented in
  `docs/slack.md`.
- **Run explanations** (`litmus_api/ai/explain.py`, `[ai]` extras,
  Alembic `0003_run_explanations`) — `POST /api/v1/runs/{id}/explain`
  (CLI: `litmus explain-run <id> --endpoint ...`) asks Claude for a
  one-paragraph hypothesis + suggested action when a run fails or errors.
  Upserted so repeat reads are free. Full doc in `docs/ai-explanations.md`.
- **Three-audience UI** (`ui/`) — single `/` landing scrolls through the
  Engineers / PMs / Viewers pitch with a live badge demo, and dedicated
  `/install`, `/ask`, `/badge` pages. Catalog moved to `/metrics`; metric
  detail now carries a reusable `<AskPanel>` sidebar at `lg+`. Badge
  gallery shows four trust states, three sizes, and copy-paste snippets
  for GitHub / Notion / Slack / Confluence / email. Install hub is
  dbt-first.
- **Badge distribution polish** — size variants (`small` / `medium` /
  `large`), custom `?label=` / `?color=` / `?style=`, a backlink wrapper
  (`<a xlink:href>` + "Powered by Litmus" tooltip) on every embed, and a
  new `GET /embed/<token>.html` unfurl page emitting OpenGraph + Twitter
  card tags for Slack. Platform-specific setup in `docs/badges.md`;
  copy-paste snippets in `examples/badges/`.
- **GitHub webhook ingestion** — `POST /webhooks/github` (HMAC-verified
  against `LITMUS_GITHUB_WEBHOOK_SECRET`) upserts `.metric` / `.yaml`
  files on `push` events for public repos. Shares `_perform_upsert` with
  the HTTP route, so `litmus check --push` and `git push` land identically.
  Setup in `docs/github-webhook.md`.
- **dbt lineage** — `POST/GET /api/v1/metrics/{id}/lineage` store + render
  a source/model/metric subgraph imported from a dbt `manifest.json`.
  `litmus import-dbt --push` now walks up to 3 hops upstream and POSTs
  the graph. The UI falls back to a 2-node stub when nothing has been
  imported yet.
- **BI reconciliation** (`litmus_api/bi/`, `[bi]` extras) — thin Looker +
  Tableau connectors. `BIMapping` pins a catalog metric to its BI
  equivalent; `Reconciliation` stores each delta (pass / warn / fail
  bucketed). Setup in `docs/bi-connectors.md`.
- **Alembic migrations** — schema is now managed by
  `alembic -c litmus_api/migrations/alembic.ini upgrade head`, not
  `create_all`. Set `LITMUS_AUTO_MIGRATE=true` to auto-apply on app
  startup in dev. A test locks in that `create_all` and `upgrade head`
  produce identical schemas.

### Changed

- **Positioning** — README, `CLAUDE.md`, and all top-level docs now lead
  with "Canonical metric contracts for engineers, AI-answered questions
  for PMs, embeddable trust badges for everyone." Getting-started doc has
  a three-audience entry table.
- **CLI help strings** — one-liners updated for `check`, `explain`,
  `explain-run`, and `report` to reflect the v0.3 pitch.
- **`MetricSpec` boundary** — downstream code (checks, reporters,
  generators) continues to consume `MetricSpec` only. Both parsers
  (`.metric` and YAML) emit the same shape.
- **JSON reporter schema** — unchanged (`schemas/v1/check-suite.schema.json`).
  Schema-version flag on `litmus check --schema-version v1` is stable.

### Packaging

- New optional extras: `[ai]` (Anthropic SDK, gated behind
  `LITMUS_ANTHROPIC_API_KEY`), `[bi]` (Looker + Tableau SDKs).
  `[server]` keeps the slim FastAPI install — AI and BI are opt-in so
  operators who don't need them don't pay the install cost. `[all]`
  pulls every extra.
- Minimum Python remains **3.10+**. `litmus` CLI entry point and
  `litmus-data` PyPI package name are unchanged.

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

[Unreleased]: https://github.com/zinnoberHaus/litmus/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/zinnoberHaus/litmus/compare/v0.1.0...v0.3.0
[0.1.0]: https://github.com/zinnoberHaus/litmus/releases/tag/v0.1.0
