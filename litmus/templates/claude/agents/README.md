# Litmus agent team

Litmus ships with two agent teams: the **user-facing Litmus team** (top level) and the **Litmus sub-team** that owns the trust engine internals (`_internal/`).

## Litmus team (the one the user invokes)

| Agent | Role | When to invoke |
|-------|------|----------------|
| [**data-architect**](data-architect.md) | Designs the schema, picks the warehouse, plans the pipeline | "how should I model X", "what's the right schema for Y" |
| [**pipeline-builder**](pipeline-builder.md) | Writes ingest + transform code, attaches Litmus trust contracts | "ingest Stripe", "build a daily revenue rollup" |
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
                                              │ new transform + .metric file
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

## Litmus sub-team (`_internal/`)

These four agents own the trust engine that Litmus depends on. Invoke only when modifying `litmus/parser/`, `litmus/checks/`, `litmus/connectors/`, or `litmus/cli.py` — not for user-facing data work.

| Agent | Owns |
|-------|------|
| [`litmus-architect`](_internal/litmus-architect.md) | `litmus/parser/`, `litmus/spec/` — the `.metric` DSL |
| [`litmus-inspector`](_internal/litmus-inspector.md) | `litmus/checks/` — trust-check runtime |
| [`litmus-connector`](_internal/litmus-connector.md) | `litmus/connectors/` — warehouse adapters |
| [`litmus-advocate`](_internal/litmus-advocate.md) | `litmus/cli.py`, reporters, dbt importer, examples |

## How to invoke

1. **Create tasks** with `TaskCreate`; they belong to the Litmus team's task list.
2. **Spawn an agent** with the Agent tool: `subagent_type: "data-architect"` (or any name above).
3. **Assign a task**: `TaskUpdate` with `owner` set to the agent name.
4. **Chain agents** by having one tell another to pick up downstream work.

## Invariants across all Litmus agents

- **Every new mart table needs a Litmus `.metric` contract.** `code-reviewer` blocks merges without one.
- **Every transform is idempotent.** No bare `INSERT INTO` against an existing table.
- **Dashboards only read from `mart_*` tables.** Raw-table joins in Streamlit are a `code-reviewer` blocker.
- **Secrets only via env vars** — `LITMUS_WAREHOUSE_USER`, `DATAPILOT_*`, never hardcoded.
- **`ops-pilot` is the only agent that writes to Notion or Linear.** Everyone else delegates.
- **Python 3.10+**; `from __future__ import annotations` everywhere; `make check` must pass.
