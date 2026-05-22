# Litmus — refactor vision (v0.5, May 2026)

## What we're becoming

**Litmus is your AI data agents team.** Install it with pip, run `litmus init`
in any repo, walk through a short wizard, and you get a working data team — a
set of AI agents plus the scaffolding (ingestion, transformation,
visualization, testing) tailored to *your* data sources.

This supersedes the v0.4 vision. The biggest change: **the trust engine is
removed.** The `.metric` DSL, parser, checks runner, reporters, the hosted
catalog (`litmus_api/`), the dbt package, and SVG trust badges are all cut.
They were too tedious for the audience we now serve — people who just want to
*verify a source, transform it with business logic, and operate on the result*,
not author a formal data-contract language.

## Who we're for (broadened)

1. **Companies with no data team** — engineers exist, a dedicated data
   engineer / analytics engineer does not. (Unchanged from v0.4.)
2. **Product & business teams that don't want centralized data** — they don't
   need a warehouse-of-record or a BI org. They have a source (a Postgres
   replica, a Stripe account, a CSV export, a Sheet), some business logic, and
   a question. Litmus stands up just enough — verify the source, transform it,
   visualize/operate on it — without the heavyweight stack.

**The promise:**
> `pip install litmus-data`. Run `litmus init`. Pick your model, point at your
> data. Litmus generates your data team and the project around it. Then talk to
> the team (`litmus`) or drive it with commands (`litmus run`, `litmus test`,
> `litmus dashboard`).

## The setup flow (`litmus init`)

A guided wizard, in this order:

1. **Project name** — defaults to the current directory name.
2. **Pick an AI model** — a menu of well-known models (Claude Opus 4.7, Claude
   Sonnet 4.6, GPT-5, Gemini 2.5 Pro, or a local model). The choice sets the
   `provider`, the model `name`, and the `runtime` (how we actually call it —
   see "Agent runtime" below).
3. **Choose data inflow (multi-select)** — one or more of: sample dataset,
   DuckDB (local), Postgres, Snowflake, BigQuery, CSV files, REST API, Stripe,
   Google Sheets. Multiple selections are allowed and expected.
4. **Build the "Litmus house"** — a progress-bar phase that generates the
   project: folders + per-source config + agents + skills + a transformation,
   visualization, and testing framework. **Generated generically from the
   user's choices** — e.g. selecting Postgres + Stripe produces source configs,
   agent context, and skills that already know about those two sources.
5. **Done** — print the two ways to use the team.

## Generated project ("the Litmus house")

```
my-project/
├── litmus.yaml              # project config: name, model, sources
├── sources/<id>.yaml        # one data-inflow config per selected source
├── transforms/              # business-logic transforms (SQL / Python)
├── dashboards/              # visualization (Streamlit)
├── tests/                   # lightweight data tests (NOT a contract DSL)
├── .claude/
│   ├── agents/              # the team, tailored to the chosen sources
│   └── skills/              # workflow skills (ingest, transform, viz, test)
├── .mcp.json                # optional Notion / Linear wiring
├── AGENTS.md                # how to talk to the team
└── .litmus/state.json       # project state
```

The agents and skills are written from templates that are **parameterized by
the user's source selection**, so a fresh project isn't generic boilerplate —
it references the actual sources the user picked.

## Two ways to use the team (after setup)

1. **Interactive — `litmus`** (run with no subcommand inside the repo). Drops
   into a chat REPL where you talk to the team in natural language.
2. **Commands — dbt-style, but every command is fronted by the agents:**
   - `litmus init` — the setup wizard.
   - `litmus configure` — re-run/edit model + sources.
   - `litmus run` — ingest → transform (the pipeline).
   - `litmus test` — run the data tests (agent-assisted).
   - `litmus dashboard` — build/open the Streamlit visualizations.
   - `litmus agent "<task>"` — dispatch a one-off task to the team.

## Agent runtime — Python or TypeScript? (answering the open question)

**Python is sufficient. No TypeScript is required.** Three options, in order of
how we'll adopt them:

1. **Shell out to the Claude Code CLI** (`claude --print …`) — what the current
   TUI does. Zero SDK code; inherits the user's Claude Code auth, `.claude/agents`,
   and skills. This is the default and the fallback.
2. **Claude Agent SDK for Python** (`pip install claude-agent-sdk`) — a real
   in-process agent loop (streaming, tool use, subagents, MCP, skills) without
   depending on the `claude` binary. This is the "proper" embedded REPL and what
   we move the interactive `litmus` mode toward. Claude-only.
3. **Provider adapters** — for non-Claude models (GPT, Gemini, local), a thin
   `AgentRuntime` interface so the model menu in `init` is honest. v1 ships the
   Claude paths fully and stubs the others behind the same interface.

TypeScript's Agent SDK exists and has parity, but it would split the codebase
for no benefit — the CLI, the scaffolder, and the runtime are all Python.

## What's removed (the trust engine)

Deleted: `litmus/parser/`, `litmus/spec/`, `litmus/checks/`, `litmus/reporters/`,
`litmus/generators/`, `litmus/connectors/` (trust I/O), `litmus/config/`
(trust-only), `litmus/api_push.py`, `litmus/integrations/trust.py`, `litmus_api/`,
`dbt_packages/`, `schemas/`, and their tests. CLI subcommands `check`, `parse`,
`explain`, `explain-run`, `import-dbt`, `export`, `report`, `share`, `reconcile`
go with them. The `[server] [ai] [bi] [postgres] [snowflake] [bigquery]` extras
are pruned to what ingestion actually needs.

`tests/` is reduced to the agent layer: CLI, wizard, scaffolder, pipelines,
integrations.

## What stays / expands

`litmus/tui.py` (interactive REPL), `litmus/wizard.py` (new — the init flow +
scaffolder), `litmus/scaffold.py` (agent-team installer), `litmus/pipelines/`
(ingest + transform runner), `litmus/dashboards/` (Streamlit helpers),
`litmus/integrations/` (Notion / Linear), `litmus/diagnostics.py` (`litmus doctor`),
and `litmus/templates/` (now generic, source-parameterized).

## Phased delivery

- **Phase 1** — the new `litmus init` wizard + generic scaffolder (model menu,
  multi-select sources, progress bars, source-parameterized house).
- **Phase 2** — CLI surface: `litmus`, `configure`, `run`, `test`, `dashboard`,
  `agent`; interactive REPL polish.
- **Phase 3** — remove the trust engine + prune tests, extras, packaging.
- **Phase 4** — rebrand everything (README, CLAUDE.md, AGENTS.md, agents/skills
  templates) to "Your AI data agents team."
- **Phase 5** — provider adapters beyond Claude; richer source connectors
  (Postgres/Stripe/Sheets ingestion).

## Naming / compatibility

PyPI package stays `litmus-data`; CLI stays `litmus`. This is a breaking 0.5
release — the trust-engine CLI verbs are gone. Done on the
`refactor/ai-data-agents` branch; not merged to `main` until reviewed.
