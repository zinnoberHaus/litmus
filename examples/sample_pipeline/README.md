# Sample pipeline — e-commerce mini-stack

A working end-to-end Litmus demo. ~3,000 lines of synthetic data; one
transform per business question; one Litmus contract per mart table; one
Streamlit dashboard.

## Layout

```
data/                     raw CSVs (orders, customers, web_events)
pipelines/                ingest specs (CSV → raw_* tables)
transforms/               SQL transforms (raw_* → mart_*)
metrics/                  Litmus trust contracts for each mart table
dashboards/founder_weekly.py    Streamlit dashboard
```

## Run it

From the repo root, after `make setup`:

```bash
litmus demo                # copies sample, runs ingest + transforms + checks
litmus dashboard           # opens Streamlit at http://localhost:8501
```

## What it shows

- A two-source pipeline (`customers` + `orders` joined into `mart_customer_ltv`).
- A daily-rollup pipeline (`raw_orders` → `mart_daily_revenue`).
- Litmus trust contracts running against the mart tables — freshness, null
  rate, row count, range, duplicates.
- A Streamlit dashboard that surfaces revenue trend + top customers, with
  a freshness header and trust banner pinned at the top.

## What to do next

After the demo is running:

1. Open this repo in Claude Code.
2. Ask the agent team for new data work, e.g.:
   - `@data-architect I want to add a churn metric — what schema do I need?`
   - `@pipeline-builder build a monthly active customers transform`
   - `@analyst what's our MoM revenue growth?`
3. The team designs, builds, attaches trust contracts, and updates the
   Notion playbook automatically.

See [`PLAYBOOK.md`](../../PLAYBOOK.md) for the operator's guide.
