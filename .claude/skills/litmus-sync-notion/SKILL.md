---
name: litmus-sync-notion
description: Push current project state to the Notion playbook page — trust scorecard, pipeline status, dashboard URLs, recent activity. Idempotent. Run daily on a cron or manually after a big change. Add --weekly for the weekly rollup with wins / issues / next priorities.
---

# /litmus-sync-notion

Sync project state to Notion.

## How to invoke

```
/litmus-sync-notion           # daily sync
/litmus-sync-notion --weekly  # weekly rollup as a sub-page
/litmus-sync-notion --dry-run # show what would change, don't write
```

## Workflow you execute

This skill delegates to the **`ops-pilot`** agent — it's the only agent allowed to write to Notion.

1. Read `.litmus/state.json` to get the Notion page ID. If missing, run `/litmus-init` first.
2. Gather current state:
   - Litmus check results for every `mart_*` table (run `litmus check metrics/` → parse JSON).
   - List of pipelines (`pipelines/*.yaml`) with last-run timestamps.
   - List of dashboards (`dashboards/*.py`) with their Streamlit URLs from `.litmus/state.json`.
   - Open Linear issues count (via Linear MCP server).
   - Last 5 agent-team actions from `.litmus/activity.log`.
3. Delegate to `ops-pilot`: "update the Notion page at <id>, refresh the sections: Data sources, Pipelines, Dashboards, Trust scorecard, Open issues, Recent activity. Here's the payload: <...>"
4. `ops-pilot` performs idempotent block updates — finds existing blocks by heading, replaces their content.
5. Reply with a one-line summary of what changed:
   > "Notion synced. Trust score 94% (-1%). 2 dashboards. 3 open Linear issues (+1)."

## Weekly variant (`--weekly`)

Adds a sub-page under the project page titled "Week of <YYYY-MM-DD>" with:
- Top 3 wins (new pipelines / dashboards shipped, trust improvements)
- Top 3 issues (failed checks, blocked PRs, missed freshness)
- Top 3 priorities for next week (suggested by `data-architect` based on open requests)

Posts a summary to Slack if `LITMUS_SLACK_WEBHOOK_URL` is set.

## Dry-run variant (`--dry-run`)

Renders the would-be update as markdown and shows it without writing to Notion.

## Failure modes

- **`NOTION_API_KEY` not set** — fail loudly with the exact env var name. Don't silently no-op.
- **Notion page deleted by user** — detect 404, ask the user whether to recreate from `PLAYBOOK.md` or update `.litmus/state.json` with a new page ID.
- **Notion MCP server not available** — point user to `docs/notion-setup.md`.
