# Litmus agent team

Litmus ships with a five-agent team in `.claude/agents/`. They are the people on your data team — you talk to them in Claude Code, they do the work.

| Agent | What they do | When to invoke |
|-------|--------------|----------------|
| **[data-architect](.claude/agents/data-architect.md)** | Designs schemas, picks the warehouse, plans the pipeline | "how should I model X", "what schema do I need for Y" |
| **[pipeline-builder](.claude/agents/pipeline-builder.md)** | Writes ingest + transform code, adds data tests | "ingest Stripe", "build a daily revenue rollup" |
| **[analyst](.claude/agents/analyst.md)** | Builds Streamlit dashboards, answers ad-hoc questions | "what's our MoM growth?", "build a founder dashboard" |
| **[code-reviewer](.claude/agents/code-reviewer.md)** | Gates merges on the non-negotiables (trust contracts, idempotency, secrets) | Always, before merge |
| **[ops-pilot](.claude/agents/ops-pilot.md)** | Syncs project state to Notion, opens/closes Linear issues | After any concrete deliverable |

## How they work together

```
You: "I need a daily revenue dashboard for the founder"
  │
  ▼
data-architect ──── designs schema + picks tables ────▶ pipeline-builder
                                                          │
                                                          │ writes transform + tests
                                                          ▼
analyst ◀──── new mart_daily_revenue table is ready
   │
   │ builds Streamlit dashboard
   ▼
code-reviewer ──── BLOCKED? ──▶ author fixes ──┐
   │                                            │
   │ APPROVED                                   │
   ▼                                            │
ops-pilot ───▶ updates Notion + opens Linear  ◀┘
```

Every step is logged to `.litmus/activity.log`. The Notion playbook page shows the latest state. Linear holds the open queue.

## How to get to your agent team

The easiest path: run `litmus` in your project directory and pick **option 1 — Open in Claude Code**. The TUI hands off to `claude` and you can immediately address agents:

```
@data-architect — I want to add a churn metric. What schema do I need?
@pipeline-builder — ingest the Stripe charges API into the warehouse
@analyst — what's our MoM revenue growth?
@code-reviewer — review the diff on this branch
@ops-pilot — sync the Notion playbook
```

If you already have Claude Code open in the directory, just mention agents directly — no need to go through the Litmus TUI.

You can also spawn agents programmatically via the `Agent` tool:

```python
Agent(
    description="Design a churn metric",
    subagent_type="data-architect",
    prompt="I want to track customer churn. We have raw_subscriptions...",
)
```

## Slash commands (skills)

The `.claude/skills/` directory ships six slash commands that wrap common multi-step workflows. They orchestrate one or more agents and the warehouse:

- **`/litmus-init`** — bootstrap a fresh project (warehouse, sample data, Notion page, Linear project)
- **`/litmus-ingest`** — register a new data source (CSV, Postgres, REST, Stripe, Sheets)
- **`/litmus-transform`** — scaffold a new mart table + Litmus contract
- **`/litmus-dashboard`** — scaffold a Streamlit dashboard
- **`/litmus-sync-notion`** — push current state to Notion
- **`/litmus-sync-linear`** — sync the issue queue to Linear

## Invariants

Across the whole team:

1. **Every mart table has a data test.** A plain SQL file in `tests/` that must return zero rows; `code-reviewer` flags a mart table that ships without one.
2. **Every transform is idempotent.** Re-running today produces the same result.
3. **Dashboards read only from `mart_*` tables.** Raw-table queries in Streamlit are a blocker.
4. **Secrets only via env vars.** Never hardcoded in YAML, SQL, or Python.
5. **`ops-pilot` is the only writer to Notion + Linear.** Other agents delegate.

These constraints come from the failure modes of agent-generated data work. They are tight on purpose. Loosen them only with a load-bearing reason and a `code-reviewer` `WARN` rather than a silent drop.
