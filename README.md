<p align="center"><img src="docs/assets/logo.png" alt="Litmus" width="160"></p>

<p align="center"><em>AI-agent-driven data engineering for teams without a data team.</em></p>

<p align="center">
  <a href="https://pypi.org/project/litmus-data/"><img src="https://img.shields.io/pypi/v/litmus-data.svg" alt="PyPI version"></a>
  <a href="https://pypi.org/project/litmus-data/"><img src="https://img.shields.io/pypi/pyversions/litmus-data.svg" alt="Python versions"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-Apache%202.0-green.svg" alt="License: Apache 2.0"></a>
  <a href="https://github.com/zinnoberHaus/litmus/actions/workflows/ci.yml"><img src="https://github.com/zinnoberHaus/litmus/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
</p>

---

## What is Litmus?

Litmus is a CLI tool that gives you an **AI data team in a directory**. Install it once globally, run `litmus` in any folder, and a five-agent team — architect, builder, analyst, reviewer, ops — handles your pipelines, transforms, quality checks, dashboards, and Notion/Linear updates.

**Who it's for:** 2–30 person companies that need data work (ETL, analytics, dashboards) but can't justify hiring a data engineer. Engineers do the install; the agents do the work.

## Install + go

```bash
# One-line install (pick one):
pipx install litmus-data
uv tool install litmus-data

# Run in any directory:
cd ~/my-project
litmus
```

That's it. `litmus` with no arguments drops you into an interactive bootstrap — picks a warehouse (DuckDB by default), loads sample data if you want it, and hands you off to your agent team.

Already have a repo? **`litmus init .`** incorporates the team into it non-interactively — the agent team (`.claude/`), the Notion + Linear MCP wiring (`.mcp.json`), `AGENTS.md`, and a metrics scaffold land alongside your existing code. It's idempotent and never clobbers files you already have. The interactive `litmus` and `litmus init` lay down the exact same team.

```
┌─────────────────────────────────────────────────┐
│ Litmus v0.4.0 — agent-driven data engineering   │
└─────────────────────────────────────────────────┘

  Project        not initialized (run option 1)
  Integrations   ✗ Notion (NOTION_API_KEY) · ✗ Linear (LINEAR_API_KEY) · ✓ Claude Code

This directory isn't a Litmus project yet. Let's set one up.
? Create the project skeleton? [Y/n]
? Load the sample e-commerce dataset (~150 rows)? [Y/n]
  ✓ project directories created
  ✓ sample data copied
  ✓ pipelines + transforms run
  ✓ wrote .litmus/state.json

What next?
  1. Open in Claude Code (talk to your agent team)
  2. Open the Streamlit dashboard
  3. Run trust checks on metrics/
  4. Re-run all pipelines + transforms
  5. Show project doctor
  q. Quit
```

## Then: ask your agent team for real work

Pick option 1 and you land in Claude Code. Talk to the team:

```
@data-architect I want a daily revenue dashboard for the founder
```

The architect proposes a schema. If you approve, `pipeline-builder` writes the transforms (with Litmus trust contracts attached), `analyst` builds the Streamlit page, `code-reviewer` gates the merge, and `ops-pilot` syncs the new dashboard to your Notion playbook and updates your Linear board.

Full agent docs: [`AGENTS.md`](AGENTS.md). Operator's guide: [`PLAYBOOK.md`](PLAYBOOK.md).

## The team

| Agent | Role |
|-------|------|
| **[data-architect](.claude/agents/data-architect.md)** | Schema design, warehouse choice, pipeline plan |
| **[pipeline-builder](.claude/agents/pipeline-builder.md)** | Ingest + transform code, Litmus trust contracts |
| **[analyst](.claude/agents/analyst.md)** | Streamlit dashboards, ad-hoc SQL |
| **[code-reviewer](.claude/agents/code-reviewer.md)** | Gates merges on the non-negotiables |
| **[ops-pilot](.claude/agents/ops-pilot.md)** | Notion + Linear sync |

Six slash-command skills wrap the common workflows: `/litmus-init`, `/litmus-ingest`, `/litmus-transform`, `/litmus-dashboard`, `/litmus-sync-notion`, `/litmus-sync-linear`. See [`.claude/skills/`](.claude/skills/).

## Notion + Linear integration

Out of the box. `.mcp.json` wires both MCP servers; drop your tokens into `.env` and the `ops-pilot` agent will:

- Create a **Notion playbook page** for the project (from [`PLAYBOOK.md`](PLAYBOOK.md)).
- Update it daily with the trust scorecard, dashboard URLs, and recent activity.
- Open **Linear issues** when a trust check fails three runs in a row, when a transform has an unresolved TODO, or when a reviewer blocker is older than 24h.
- Close them when the underlying work is shipped.

Required env vars (see [`.env.example`](.env.example)):

```
NOTION_API_KEY=...    # https://notion.so/profile/integrations
LINEAR_API_KEY=...    # https://linear.app/settings/api
```

If either is blank, the corresponding integration is disabled with a one-line warning — no crash, no silent skip.

## The trust engine

Every mart table the agents produce ships with a Litmus `.metric` contract. The trust engine checks the warehouse for freshness, null rate, volume, range, duplicates, schema drift, and distribution shift — and refuses to mark a build green if any contract fails.

It's also a standalone product. If you only want trust checks for an existing data stack:

```bash
pipx install litmus-data
litmus init my-metrics    # scaffold litmus.yml + a starter .metric (and the agent team — ignore it if you don't need it)
litmus check metrics/
```

A short `.metric` example:

```gherkin
Metric: Daily Revenue
Description: Paid revenue per day from raw_orders
Source: mart_daily_revenue

Given the orders have status "paid"

When we calculate
  Then sum the amount column for that day

The result is "Daily Revenue"

Trust:
  Freshness must be less than 24 hours
  Null rate on revenue must be less than 1%
  Row count must not drop more than 50% day over day
  Value must be between 0 and 100000
  Duplicate rate on day must be 0%
```

The reviewer agent blocks any merge that ships a `mart_*` table without a `.metric` file alongside it.

## What Litmus is NOT

- **Not a new orchestrator.** YAML over a thin Python runner. Outgrow it → graduate to Dagster / Airflow / Prefect; your transforms + contracts migrate cleanly.
- **Not a new warehouse.** DuckDB is the default (zero-config, fits ~10 GB). Postgres / Snowflake / BigQuery work via the existing connectors.
- **Not a hosted SaaS.** The catalog (`litmus_api/`) is optional. The local flow is fully self-contained.
- **Not a new BI tool.** We scaffold Streamlit. Bring your own Tableau / Looker / Metabase / Evidence.

## CLI reference

```
litmus                          # interactive TUI (bootstrap + agent console)
litmus init [project-name|.]    # create a Litmus team here: agent team + .mcp.json + metrics scaffold
litmus demo                     # load + run the sample e-commerce pipeline
litmus ingest [pipeline-name]   # run an ingest from pipelines/*.yaml
litmus transform [name]         # run a SQL transform from transforms/*.sql
litmus check metrics/           # run trust checks
litmus dashboard                # open the Streamlit dashboards
litmus run                      # run everything (ingest → transform → trust)
litmus doctor                   # diagnose setup
litmus explain <metric>         # plain-English doc for a metric
litmus parse <metric>           # debug: dump parsed MetricSpec
litmus report <dir>             # generate HTML/JSON/Markdown reports
litmus share <dir>              # single-file HTML dashboard
litmus export <dir> dbt         # emit dbt tests/sources from .metric files
litmus import-dbt manifest.json # import dbt metrics as .metric files
```

## Project layout (after `litmus` bootstrap)

```
your-project/
├── data/
│   ├── raw/                  # raw CSVs / extracts
│   └── warehouse.duckdb      # the default warehouse
├── pipelines/*.yaml          # ingest specs (raw_* tables)
├── transforms/*.sql          # SQL transforms (mart_* tables)
├── metrics/*.metric          # Litmus trust contracts
├── dashboards/*.py           # Streamlit pages
├── .litmus/state.json        # project state (Notion page id, etc.)
├── .env                      # secrets (NOTION_API_KEY, etc.)
└── .claude/                  # agent team + skills (auto-created)
```

## Develop on Litmus itself

```bash
git clone https://github.com/zinnoberHaus/litmus
cd litmus
make dev       # editable install with [dev]
make check     # ruff + mypy + pytest
make demo      # sample pipeline end-to-end from the repo
```

CI: lint → pytest with coverage → mypy across Python 3.10/3.11/3.12.

See [`REFACTOR_VISION.md`](REFACTOR_VISION.md) for how Litmus evolved from trust-check tool to agent-driven platform.

## License

Apache 2.0 — see [`LICENSE`](LICENSE). Contributions welcome; please read [`CONTRIBUTING.md`](CONTRIBUTING.md) and [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md) first.
