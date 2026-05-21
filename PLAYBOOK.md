# Litmus — operator's playbook

> **This is the page that gets synced to Notion when you run `/litmus-init`.**
> It's written for the human operator — usually the founder, COO, or
> generalist engineer — who set Litmus up and now needs to actually use it.

## What Litmus is

Litmus is your data team in a CLI. Five AI agents handle the work that
a junior data engineer + analyst + ops person would do at a bigger company:
they ingest data, model it, run quality checks, build dashboards, and keep
this Notion page + your Linear board up to date.

You install it once globally:

```bash
pipx install litmus-data
```

Then run `litmus` in any directory. The TUI bootstraps the project, then
hands you off to Claude Code where you talk to the agents. They write code,
you review (or have `code-reviewer` review for you), and the work ships.

## Daily flow (5 minutes)

In the morning:

1. Open this Notion page. Glance at:
   - **Trust scorecard** — green means yesterday's data is good.
   - **Recent activity** — what the agents did overnight.
   - **Open issues** — anything flagged for human triage.
2. If anything is red, open Linear and pick up the issue (or ask the team in Claude Code: `@ops-pilot what's the open issue about?`).
3. If you have a new data question, ask in Claude Code — see the recipes below.

## The recipes

### "I want a new dashboard"

```
@data-architect I want a dashboard for the founder that shows weekly revenue,
top customers, and conversion rate. What tables do I need?
```

The architect proposes a schema. If you say yes, the builder writes the
transforms, the analyst builds the Streamlit page, and ops-pilot updates this
page with the URL. Total time: usually 10–20 minutes of agent work.

### "I want to ingest a new data source"

```
@pipeline-builder pull Stripe charges into the warehouse, daily
```

Builder writes the ingest spec, runs the first load, and confirms the table
is populated. If Stripe credentials aren't set up, builder will tell you
exactly which env var to add to `.env`.

### "Why is this number wrong?"

```
@analyst the founder dashboard shows $42k revenue but Stripe says $58k. Why?
```

The analyst will trace the gap — usually it's a `status` filter, a date-range
mismatch, or a refund handling issue. They'll fix the query (or escalate to
pipeline-builder if the underlying table needs fixing) and re-deploy the
dashboard.

### "What's our X?"

```
@analyst what's our MoM revenue growth?
```

For one-off questions, the analyst writes SQL against the mart tables and
replies with the answer + a one-line interpretation. They'll ask "should
this become a dashboard?" If yes, the recipe above kicks in.

### "Something's broken — open a bug"

```
@ops-pilot the dashboard at /founder_weekly is loading blank. Open a Linear
issue for the analyst to investigate.
```

ops-pilot creates the issue with the right labels and project, links it back
to the dashboard file, and posts the issue URL.

## What the agents WILL NOT do

- **Make business decisions.** They can compute numbers; they won't tell you what to do with them.
- **Skip the trust contracts.** Every mart table gets a `.metric` file. The reviewer rejects PRs without one — this is what keeps your dashboards from showing wrong numbers silently.
- **Touch Notion or Linear without going through ops-pilot.** Keeps the integration surface consistent.
- **Operate without the trust engine.** If trust checks are broken, the whole team pauses until they're fixed.

## Where things live

| Thing | Where |
|-------|-------|
| Raw CSVs / source data | `data/raw/` |
| Ingest specs | `pipelines/*.yaml` |
| SQL transforms | `transforms/*.sql` |
| Trust contracts | `metrics/*.metric` |
| Dashboards (Streamlit) | `dashboards/*.py` |
| Project state | `.litmus/state.json` |
| This page (synced) | Notion → Litmus playbook |
| Open issues | Linear → your project |

## When to bring in a real human

Litmus is for the zero-to-one tier. You should bring in a real data
engineer or analytics engineer when:

- Your warehouse stops fitting on DuckDB (>10 GB working set).
- You need cross-org governance (RBAC, audit logs, PII tagging).
- The agent team is producing the same kind of work over and over and you'd
  rather have it owned by a person who can think strategically about it.
- You're building data products for external customers, not just internal dashboards.

When you do, Litmus's outputs (mart tables, trust contracts, dashboards) all
migrate cleanly into a real stack (dbt + Snowflake + Mode/Hex). Nothing you
build here is throwaway.

## Operator FAQ

**Where do I read the agent definitions?**
`.claude/agents/` — five markdown files, each defines one agent's identity,
mission, and rules.

**Can I change what the agents do?**
Yes — edit the markdown. Each agent's behavior is the file. Be careful with
the invariants (see [`AGENTS.md`](AGENTS.md)) — they exist because we tested
without them and things broke.

**How do I add a new agent?**
Drop a new markdown file in `.claude/agents/` with the right frontmatter
(`name:` and `description:`). The Claude Code harness picks it up
automatically. Update [`AGENTS.md`](AGENTS.md) so the team is documented.

**How do I disable Notion or Linear?**
Leave the API key blank in `.env`. ops-pilot will skip those integrations
with a one-line warning per sync, not silently no-op.

**How do I run the agents on a schedule?**
For now, use cron + Claude Code's headless mode. Phase 3 of the roadmap
(see [`REFACTOR_VISION.md`](REFACTOR_VISION.md)) adds a built-in scheduler.

**Is the trust engine still standalone?**
Yes. If you only want the `.metric` DSL + trust checks (no agent team, no
ingest/transforms), `litmus init` + `litmus check` work exactly as they did
in Litmus 0.3. The agent stuff is purely additive.
