# Litmus agent team

**Litmus — your AI data agents team.** The team below is what `litmus init` drops into `.claude/` so the agents can take a project from a raw source → transform → operating dashboard.

## The team (the agents the user invokes)

| Agent | Role | When to invoke |
|-------|------|----------------|
| [**data-architect**](data-architect.md) | Designs the schema, picks the warehouse, plans the pipeline | "how should I model X", "what's the right schema for Y" |
| [**pipeline-builder**](pipeline-builder.md) | Writes ingest + transform code, attaches data tests | "ingest Stripe", "build a daily revenue rollup" |
| [**analyst**](analyst.md) | Builds Streamlit dashboards, writes ad-hoc SQL | "what's our MoM growth?", "build a founder dashboard" |
| [**code-reviewer**](code-reviewer.md) | Gates merges on the small list of non-negotiables | ALWAYS before merge |
| [**ops-pilot**](ops-pilot.md) | Syncs project state to Notion, opens/closes Linear issues | After any concrete deliverable lands |

## Handoff map

```
User asks for data work
         │
         ▼
    data-architect ──── design doc ────▶ pipeline-builder
                                              │
                                              │ new transform + data tests
                                              ▼
    analyst ◀──── new mart table available
       │
       │ writes dashboard
       ▼
    code-reviewer ──── BLOCKED ──▶ author fixes ──┐
       │                                          │
       │ APPROVED                                 │
       ▼                                          │
    ops-pilot ───▶ sync Notion + close Linear ◀──┘
```

## How to invoke

1. **Create tasks** with `TaskCreate`; they belong to the Litmus team's task list.
2. **Spawn an agent** with the Agent tool: `subagent_type: "data-architect"` (or any name above).
3. **Assign a task**: `TaskUpdate` with `owner` set to the agent name.
4. **Chain agents** by having one tell another to pick up downstream work.

## Invariants across all Litmus agents

- **Every new mart table needs a data test.** A `tests/<name>.sql` that returns zero rows when healthy. `code-reviewer` blocks merges without one.
- **Every transform is idempotent.** No bare `INSERT INTO` against an existing table.
- **Dashboards only read from `mart_*` tables.** Raw-table joins in Streamlit are a `code-reviewer` blocker.
- **Secrets only via env vars** — `LITMUS_WAREHOUSE_USER`, `DATAPILOT_*`, never hardcoded.
- **`ops-pilot` is the only agent that writes to Notion or Linear.** Everyone else delegates.
- **Python 3.10+**; `from __future__ import annotations` everywhere; `make check` must pass.
