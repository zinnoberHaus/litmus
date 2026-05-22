---
name: litmus-sync-linear
description: Sync agent-detected work to the Linear project — open issues for failing data tests and TODO comments, close issues whose underlying work has shipped, and surface the open queue for human triage. Delegates to ops-pilot.
---

# /litmus-sync-linear

Sync the engineering queue to Linear.

## How to invoke

```
/litmus-sync-linear
/litmus-sync-linear --triage   # open issues only, don't close anything
/litmus-sync-linear --close-resolved  # close issues whose check is now PASSED
```

## Workflow you execute

This skill delegates to the **`ops-pilot`** agent — it's the only agent allowed to write to Linear.

### Open new issues for

1. **Data-test failures** — any `tests/*.sql` test that has FAILED 3+ consecutive runs gets a Linear issue with:
   - Title: `[data-test] <table> failed: <test name>`
   - Body: last 5 run results, the test file, and the rows it returned
   - Label: `data-test`
   - Assignee: leave blank for human triage

2. **TODO comments in transforms** — grep `transforms/*.sql` and `tests/*.sql` for `TODO:`. Each unique TODO becomes an issue if it doesn't already exist (dedupe by file + line).

3. **Reviewer BLOCKER findings older than 24h** — if `code-reviewer` posted a `BLOCKED` review and the author hasn't pushed a fix in 24h, escalate as a Linear issue.

### Close existing issues for

1. **Data-test failures** whose test has PASSED for 3+ runs.
2. **TODO comments** whose underlying line no longer exists or no longer contains a TODO.
3. **Reviewer BLOCKERs** that were addressed (PR merged).

### Workflow

1. Read `.litmus/state.json` for the Linear project ID.
2. Gather current state: data-test history (`litmus test --json`), TODO grep, open reviews.
3. Delegate to `ops-pilot`: "for each item in <payload>, create / update / close the corresponding Linear issue. Use label <...>, project <id>."
4. `ops-pilot` calls the Linear MCP tools (`mcp__claude_ai_Linear__save_issue`, `list_issues`, etc.) with dedup by title.
5. Reply with a one-line summary:
   > "Linear synced. Opened 2 issues (data-test failures on `mart_x`). Closed 1 issue (TODO resolved in `transforms/y.sql`). 5 issues open."

## Conventions

- **Never assign** — let humans triage. Auto-assignment leads to ghost-assigned tickets nobody owns.
- **Always link back** — issue body must include the file path + line, or the test file + table name.
- **Idempotent** — dedupe by title; updating an existing issue beats creating a duplicate.
- **Only open issues for real failures** — a data test triggers an issue only when it has actually failed (returned rows). Don't open issues for passing tests.

## Failure modes

- **`LINEAR_API_KEY` not set** — fail loudly with the exact env var name.
- **Linear project not initialised** — run `/litmus-init` first (it creates the project).
- **Issue title would exceed Linear's limit** — truncate to 200 chars, put full title in body.
