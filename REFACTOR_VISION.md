# Litmus — refactor vision (May 2026)

## What we're becoming

This repo is being repositioned from **Litmus** (a metric trust-check tool) into **Litmus** (the same name, broader product): an open-source, **AI-agent-driven data engineering platform** for teams that don't have, and don't want to spin up, a full data team.

**The user we're building for:**
- 2–30 person companies that suddenly have data questions ("what's our CAC trend?", "build me a dashboard for the founder", "set up an ETL from Stripe into our warehouse").
- They have engineering talent, maybe, but no dedicated data engineer / analytics engineer / BI hire.
- They don't want to evaluate Fivetran + dbt + Snowflake + Looker + Monte Carlo. They want a single tool they can install, point at their data, and have an AI team handle the rest.

**The promise:**
> "`pipx install litmus-data`. Run `litmus` in any directory. Describe what data work you need. The agents do it — pipelines, transforms, quality checks, dashboards — and write everything up in your Notion."

## What's not changing

The **trust engine stays** — DSL, parser, checks, connectors, FastAPI catalog, dbt package, badges, Slack sign-off, AI run explanations, BI reconciliation. All of that is now part of the same product: it's how Litmus guarantees the data its agents produce is trustworthy.

The four internal agents that own the trust engine (`litmus-architect`, `litmus-inspector`, `litmus-connector`, `litmus-advocate`) stay as the **sub-team** in `.claude/agents/_internal/`. They're for contributors modifying the trust engine; end users never see them.

## What's new

### 1. Install + go

```bash
pipx install litmus-data
cd ~/my-project
litmus
```

Bare `litmus` drops into an interactive TUI (see `litmus/tui.py`). It detects whether the project is initialised, offers to bootstrap (warehouse, sample data, Notion playbook, Linear project), then shows a menu of next actions including "open in Claude Code" for agent-driven work.

### 2. A user-facing agent team (`.claude/agents/`)

Five agents the **end user** invokes when they want data work done:

| Agent | Role | Primary verbs |
|-------|------|---------------|
| **data-architect** | Designs the schema, picks the warehouse, plans the pipeline | "model this", "what schema do I need for…" |
| **pipeline-builder** | Writes the ingest + transform code | "pull Stripe into orders table", "build a daily revenue rollup" |
| **analyst** | Builds dashboards, writes SQL, answers ad-hoc questions | "what's our MoM growth?", "build a founder dashboard" |
| **code-reviewer** | Reviews any PR before merge; gates trust violations | Always invoked before merge |
| **ops-pilot** | Wires Notion + Linear, runs the daily review | "open Linear issue for X", "sync to Notion" |

### 3. A skill system (`.claude/skills/`)

Slash commands for the workflow:

- `/litmus-init` — bootstrap a fresh project (warehouse, sample data, Notion page, Linear project)
- `/litmus-ingest` — register a new data source (CSV, Postgres, REST API, Stripe, Google Sheets)
- `/litmus-transform` — scaffold a new SQL transform with a trust contract attached
- `/litmus-dashboard` — scaffold a new Streamlit dashboard
- `/litmus-sync-notion` — push current state to Notion
- `/litmus-sync-linear` — sync the issue queue to Linear

### 4. Notion + Linear MCP wiring

`.mcp.json` at the repo root declares the Notion and Linear MCP servers so cloning the repo (or, when shipped, running `litmus init` in a directory) gives every contributor the integration out of the box. `.env.example` documents the required tokens.

- **Notion** = the **docs + operations** surface. Every project gets a Notion page with: project goal, data sources, pipelines, dashboards, current trust score, open issues.
- **Linear** = the **engineering** surface. Bugs, feature requests, and agent-detected issues land here as tickets.

### 5. Orchestration layer (folded into `litmus/`)

The thin orchestration on top of the trust engine — `litmus/pipelines/`, `litmus/dashboards/`, `litmus/integrations/`, `litmus/diagnostics.py`, `litmus/tui.py` — all live inside the same `litmus` package as the trust engine. One package, one `litmus` CLI, one PyPI release.

- `litmus/pipelines/runner.py` — YAML-driven ingest + SQL transform runner (~200 lines).
- `litmus/dashboards/__init__.py` — Streamlit helpers (freshness header, trust banner).
- `litmus/integrations/trust.py` — adapter that runs trust checks on mart tables.
- `litmus/integrations/notion.py` — `ProjectSnapshot` payload shape for the Notion MCP.
- `litmus/integrations/linear.py` — `IssueDraft` payload shape for the Linear MCP.
- `litmus/tui.py` — interactive bootstrap + menu (bare `litmus` invocation).
- `litmus/templates/sample_pipeline/` — the bundled sample (ships in the wheel).

### 6. Sample dataset bundled in the wheel

`litmus/templates/sample_pipeline/` ships inside the installed package:

```
litmus/templates/sample_pipeline/
  data/
    customers.csv (30 rows)
    orders.csv (70 rows)
    web_events.csv (40 rows)
  pipelines/    *.yaml (3 ingest specs)
  transforms/   *.sql (2 mart tables)
  metrics/      *.metric (2 trust contracts)
  dashboards/   founder_weekly.py
```

`examples/sample_pipeline/` mirrors this for repo-clone dev usage; both stay in sync (the canonical source is the package copy).

### 7. The Notion playbook

`PLAYBOOK.md` is the content that gets synced into Notion when a project is initialised. It's the **non-technical operator's guide**: "your Litmus is set up — here's how to ask it for things, here's where to find what it produced, here's how to read the trust badges."

## What we are explicitly NOT building

- A new orchestration framework. Thin YAML-over-Python runner. Outgrow it → graduate to Dagster / Airflow / Prefect.
- A new warehouse. DuckDB is the default; Postgres / Snowflake / BigQuery are supported via the existing connectors.
- A hosted SaaS. The catalog (`litmus_api/`) is still optional, opt-in. Local-only flow works end-to-end.
- A new BI tool. We scaffold Streamlit. Bring your own Tableau / Looker / Metabase / Evidence.

## Phased delivery

**Phase 1 (this refactor)** — the scaffolding and the demo. Five agents, six skills, Notion/Linear MCP wiring, orchestration layer inside `litmus/`, bundled sample pipeline, interactive TUI, pipx-friendly install, docs.

**Phase 2** — real integrations. Notion sync that actually creates and updates pages. Linear sync that opens and resolves issues. Stripe / Postgres / Google Sheets ingest connectors. A `litmus doctor` that goes deeper than env-var checks.

**Phase 3** — production polish. Schedule pipelines via cron, push trust failures to Slack, deploy dashboards to Streamlit Cloud / Vercel, multi-environment support (dev / prod warehouses), brew formula for one-line install.

## Backwards compatibility

All existing trust-engine CLI commands continue to work unchanged — `litmus init`, `litmus check`, `litmus parse`, `litmus explain`, `litmus import-dbt`, `litmus export`, `litmus report`, `litmus share`, `litmus reconcile`. New subcommands (`litmus demo`, `litmus ingest`, `litmus transform`, `litmus dashboard`, `litmus run`, `litmus doctor`) are additive. Bare `litmus` is new (interactive TUI) — previously `litmus` with no args printed help; now it does that under non-TTY use, and launches the TUI when run in a terminal.

PyPI package name `litmus-data` is unchanged. PyPI users on the old install will see the new TUI on next upgrade with no flag changes.
