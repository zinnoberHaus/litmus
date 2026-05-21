---
name: litmus-init
description: Bootstrap a Litmus project in the current repo — incorporate the agent team, load sample data, scaffold the Notion playbook page, create the Linear project. Idempotent — re-running updates rather than duplicates.
---

# /litmus-init

Bootstrap a Litmus project end-to-end, in whatever repo you're standing in. No clone, no `make` — the CLI ships the whole team inside the wheel.

## What it does

1. **Incorporate the agent team** — runs `litmus init .`, which lays down `.claude/agents/`, `.claude/skills/`, `.mcp.json`, `AGENTS.md`, a `litmus.yml`, and a starter `metrics/` contract, then writes `.litmus/state.json`. Idempotent: existing files are kept.
2. **Pick the warehouse** — defaults to local DuckDB. If `LITMUS_WAREHOUSE_URL` is set in `.env`, uses that instead.
3. **Load the sample dataset (optional)** — `litmus demo` loads the bundled sample ontology so there's something to look at.
4. **Create the Notion playbook page** — uses `ops-pilot` + the Notion MCP server to create a page from `PLAYBOOK.md`. Records the page ID in `.litmus/state.json`.
5. **Create the Linear project** — uses `ops-pilot` + the Linear MCP server to create a project named after the repo. Records the project ID.
6. **Print next steps** — Notion link, Linear link, Streamlit URL, and the first prompt to ask the team.

## How to invoke

```
/litmus-init                    # use defaults
/litmus-init --no-sample        # skip loading the sample dataset
/litmus-init --warehouse=postgres://...   # use a non-default warehouse
```

## Workflow you (the agent) execute

1. Read `.litmus/state.json` if it exists — if `initialized: true`, ask whether to re-init or just sync. Default to sync.
2. Check env vars: `NOTION_API_KEY`, `LINEAR_API_KEY`. If either is missing, warn and skip that integration but continue.
3. Run `litmus init .` to incorporate the agent team + metrics scaffold into the current repo (idempotent — pass `--force` only if the user wants existing files overwritten).
4. Unless `--no-sample`, run `litmus demo` to load the bundled sample pipeline.
5. Delegate to `ops-pilot`: "create the Notion playbook page from `PLAYBOOK.md`, create the Linear project, return both IDs."
6. Write the IDs to `.litmus/state.json`.
7. Print a summary with all three links + the suggested first prompt:
   > "Litmus is ready. Try asking: `@data-architect I want a daily dashboard of <X> for <stakeholder>` and the team will design + build it."

## Failure modes

- **Already initialised** — `litmus init` is idempotent; existing files are kept. Ask before overwriting with `--force`.
- **Notion / Linear key missing** — note the env var name in the output, continue without that integration.
- **Sample dataset already loaded** — skip (idempotent).
