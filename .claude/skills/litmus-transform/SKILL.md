---
name: litmus-transform
description: Scaffold a new SQL transform that produces a mart table, with a Litmus trust contract attached. Use after litmus-ingest has loaded raw data. Output goes to transforms/<table>.sql + metrics/<table>.metric.
---

# /litmus-transform

Build a new transform from raw → mart.

## How to invoke

```
/litmus-transform <mart-table-name>
/litmus-transform mart_daily_revenue
/litmus-transform mart_customer_ltv --from raw_orders,raw_customers
```

## Workflow you execute

1. **Confirm the business question.** A transform exists because someone needs the output. Ask: who reads `mart_<name>`, in what dashboard or query?
2. **Identify the source tables.** Should be `raw_*` or other `mart_*` (not `_internal` tables). If the user wants to read from raw and you smell a join that will recur, materialise it as a separate mart.
3. **Write the transform** to `transforms/<mart-table-name>.sql`:
   ```sql
   -- mart_daily_revenue: daily total revenue + order count
   -- Source: raw_orders. Refresh: daily.

   CREATE OR REPLACE TABLE mart_daily_revenue AS
   SELECT
       DATE_TRUNC('day', order_at) AS day,
       COUNT(*) AS order_count,
       SUM(amount) AS revenue,
       CURRENT_TIMESTAMP AS updated_at
   FROM raw_orders
   WHERE order_at >= CURRENT_DATE - INTERVAL '90 days'
   GROUP BY 1;
   ```
   Requirements: idempotent (`CREATE OR REPLACE` or `INSERT OR REPLACE`), `updated_at` column, no `SELECT *`.

4. **Write the Litmus `.metric` contract** to `metrics/<mart-table-name>.metric`:
   ```
   metric: <Mart Daily Revenue>
     description: Daily revenue + order count for the last 90 days
     owner: pipeline-builder

   source:
     table: mart_daily_revenue

   given:
     refreshed daily from raw_orders

   when:
     summed by day

   then:
     present as a revenue trend

   Trust:
     Freshness must be less than 24 hours
     Null rate on day must be less than 1%
     Row count must not drop more than 30% day over day
     Value must be between 0 and 10000000   # TODO: tighten after 1 week
     Duplicate rate on day must be 0%
   ```

5. **Run the transform** — `litmus transform <name>`. Confirm row count + a sample row.
6. **Run `litmus check metrics/<name>.metric`** — confirm trust contract passes.
7. **Hand off to `code-reviewer`.** They gate on: idempotent, `.metric` exists, `updated_at` present, no `SELECT *`.
8. **Tell `analyst`** that `mart_<name>` is available, in case they want to build a dashboard.

## Conventions

- Mart tables always named `mart_<noun>` (`mart_daily_revenue`, `mart_customer_ltv`).
- Always include `updated_at` (Litmus freshness needs it).
- Always idempotent.
- Window: don't compute over all-time if you can avoid it. Most marts only need the last 90 days.
- Comments at the top: what is this table, where does it come from, how often is it refreshed.

## Failure modes

- **Source raw table missing** — escalate to `/litmus-ingest` first.
- **Trust contract fails on first run** — investigate before merging. Don't loosen the thresholds to make it pass.
- **Transform takes > 5 minutes** — escalate to `data-architect`; you're probably joining wrong or missing an index / partition.
