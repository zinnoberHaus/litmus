<p align="center"><img src="docs/assets/logo.png" alt="Litmus" width="160"></p>

<p align="center"><em>Your AI data agents team — in any repo.</em></p>

<p align="center">
  <a href="https://pypi.org/project/litmus-data/"><img src="https://img.shields.io/pypi/v/litmus-data.svg" alt="PyPI version"></a>
  <a href="https://pypi.org/project/litmus-data/"><img src="https://img.shields.io/pypi/pyversions/litmus-data.svg" alt="Python versions"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-Apache%202.0-green.svg" alt="License: Apache 2.0"></a>
</p>

---

## What is Litmus?

Litmus is a CLI that drops an **AI data team** into any repo. Install it, run `litmus init`, answer a few questions, and you get a working data project — ingestion, transforms, dashboards, and tests — plus a team of agents that do the actual work.

**Who it's for:**

- **Companies with no data team** — you have engineers, not a dedicated data engineer. The agents fill the gap.
- **Product & business teams that don't want centralized data** — no warehouse-of-record, no BI org. You have a source (a Postgres replica, a Stripe account, a CSV, a Sheet), some business logic, and a question. Litmus stands up *just enough*: **verify a source → transform it → operate on the result.**

## Install + set up

```bash
# Install once (pick one):
pipx install litmus-data
uv tool install litmus-data

# Set up a project in any directory:
cd ~/my-project
litmus init
```

`litmus init` is a guided wizard:

```
project name
  → pick an AI model        (Claude Opus / Sonnet / Haiku, GPT-5, Gemini, local)
  → choose data inflow      (sample data, DuckDB, Postgres, Snowflake, BigQuery,
                             CSV, REST, Stripe, Sheets — pick as many as you want)
  → build the "Litmus house" (progress bar)
```

It generates a project tailored to *your* choices:

```
my-project/
├── litmus.yaml          # project config: model + sources
├── sources/<id>.yaml    # one config per data source you picked
├── transforms/          # business-logic transforms (SQL/Python) + starter
├── dashboards/          # Streamlit visualizations + starter
├── tests/               # lightweight data tests (plain SQL) + starter
├── .claude/             # your agent team + workflow skills
├── .mcp.json            # optional Notion / Linear wiring
├── AGENTS.md            # how to talk to the team
└── .litmus/             # state + a project brief the agents read
```

Non-interactive (CI, scripts):

```bash
litmus init . --yes --model claude-sonnet --source postgres --source stripe
```

## Two ways to work with the team

**1. Talk to it — interactive.** Run `litmus` in the repo and chat with the team in natural language.

**2. Drive it — dbt-style commands, every one fronted by the agents:**

```
litmus init        set up a project (the wizard)
litmus configure   change the AI model or data sources
litmus run         ingest → transform
litmus test        run your data tests (each tests/*.sql must return zero rows)
litmus dashboard   build / open a visualization
litmus add <csv>   register a CSV source in one shot
litmus agent "…"   dispatch a one-off task to the team
litmus connect     wire up Notion / Linear / Anthropic / Slack
litmus doctor      diagnose setup
```

```bash
litmus agent "ingest customers.csv and build a daily signups table, then chart it"
```

## The team

Five agents live in `.claude/agents/` (full docs in [`AGENTS.md`](AGENTS.md)):

| Agent | Role |
|-------|------|
| **data-architect** | Schema design, source modeling, pipeline plan |
| **pipeline-builder** | Ingest + transform code |
| **analyst** | Streamlit dashboards, ad-hoc questions |
| **code-reviewer** | Reviews changes before they land |
| **ops-pilot** | Notion + Linear sync |

The interactive chat runs on the model you picked. Claude models work out of the box via Claude Code; GPT / Gemini / local are wired through provider adapters.

## What Litmus is NOT

- **Not a new orchestrator.** A thin YAML-over-Python runner. Outgrow it → graduate to Dagster / Airflow / Prefect.
- **Not a new warehouse.** DuckDB is the zero-config default; Postgres / Snowflake / BigQuery are supported sources.
- **Not a hosted SaaS.** Everything runs locally in your repo.
- **Not a BI tool.** We scaffold Streamlit. Bring your own Tableau / Looker / Metabase.

## Develop on Litmus itself

```bash
git clone https://github.com/zinnoberHaus/litmus
cd litmus
pip install -e ".[dev]"
make check          # ruff + mypy + pytest
```

## License

Apache 2.0 — see [`LICENSE`](LICENSE). Contributions welcome; see [`CONTRIBUTING.md`](CONTRIBUTING.md) and [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md).
