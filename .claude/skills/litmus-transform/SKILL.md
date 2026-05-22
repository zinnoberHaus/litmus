---
name: litmus-transform
description: Scaffold a new SQL transform that produces a mart table, with data tests attached. Use after litmus-ingest has loaded raw data. Output goes to transforms/<table>.sql + tests/<table>_*.sql.
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

4. **Write data tests** to `tests/<mart-table-name>_*.sql`. A data test is a plain SQL query that **must return zero rows to pass** — any row it returns is a failing record. Write one file per check:
   ```sql
   -- tests/mart_daily_revenue_freshness.sql
   -- fails if the table hasn't been refreshed in the last 24 hours
   SELECT 1 WHERE (
       SELECT MAX(updated_at) FROM mart_daily_revenue
   ) < CURRENT_TIMESTAMP - INTERVAL '24 hours';
   ```
   ```sql
   -- tests/mart_daily_revenue_no_null_day.sql
   -- fails for every row with a null primary key
   SELECT day FROM mart_daily_revenue WHERE day IS NULL;
   ```
   ```sql
   -- tests/mart_daily_revenue_value_range.sql
   -- fails for every row whose revenue is out of band
   SELECT day, revenue FROM mart_daily_revenue
   WHERE revenue < 0 OR revenue > 10000000;  -- TODO: tighten after 1 week
   ```
   ```sql
   -- tests/mart_daily_revenue_unique_day.sql
   -- fails for every duplicated primary key
   SELECT day FROM mart_daily_revenue GROUP BY day HAVING COUNT(*) > 1;
   ```

5. **Run the transform** — `litmus transform <name>`. Confirm row count + a sample row.
6. **Run `litmus test`** — confirm every test for the new table returns zero rows.
7. **Hand off to `code-reviewer`.** They gate on: idempotent, data tests exist, `updated_at` present, no `SELECT *`.
8. **Tell `analyst`** that `mart_<name>` is available, in case they want to build a dashboard.

## Conventions

- Mart tables always named `mart_<noun>` (`mart_daily_revenue`, `mart_customer_ltv`).
- Always include `updated_at` (freshness tests need it).
- Always idempotent.
- Window: don't compute over all-time if you can avoid it. Most marts only need the last 90 days.
- Comments at the top: what is this table, where does it come from, how often is it refreshed.

## Failure modes

- **Source raw table missing** — escalate to `/litmus-ingest` first.
- **A data test fails on first run** — investigate before merging. Don't loosen the thresholds to make it pass.
- **Transform takes > 5 minutes** — escalate to `data-architect`; you're probably joining wrong or missing an index / partition.
