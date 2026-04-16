# Metric Alignment Demo — "3 Teams, 3 Numbers"

A fully runnable walkthrough of Litmus's core use case: getting every team in your company to agree on what a metric means.

**The scenario:** It's April 2, 2026. The CEO asks "what was our revenue in March?" Engineering says **$4.4M**. Analytics says **$3.8M**. Finance says **$2.75M**. Each team has a SQL query. Each team thinks they're right. Nobody trusts the number.

This directory shows the problem, the fix, and how Litmus keeps it fixed.

---

## Contents

```
alignment/
├── README.md                          ← you are here
├── seed.sql                            ← orders + refunds sample data (8 orders, 2 refunds)
├── litmus.yml                          ← config pointing at the demo DB
├── run_demo.sh                         ← one-shot end-to-end walkthrough
├── queries/
│   ├── engineering.sql                 ← "not cancelled, gross, calendar month"   → $4,400,000
│   ├── analytics.sql                   ← "completed, rolling 30d, net"             → $3,800,000
│   ├── finance.sql                     ← "invoiced + paid, USD only, net"          → $2,750,000
│   └── aligned.sql                     ← the cross-functional contract             → $3,250,000
└── metrics/
    └── monthly_revenue.metric          ← the contract, in plain English
```

## Running it

```bash
# From the repo root, install in dev mode
make dev

# Then
cd examples/alignment
./run_demo.sh
```

The script:

1. Seeds a DuckDB file with realistic orders + refunds data.
2. Runs each team's query — three different numbers.
3. Runs the aligned query — one canonical number.
4. Runs `litmus explain` to show what a non-engineer reads.
5. Runs `litmus check` to validate the underlying data.

No DuckDB CLI? Run the equivalent in Python:

```python
import duckdb
conn = duckdb.connect("alignment_demo.duckdb")
conn.execute(open("seed.sql").read())

for team in ["engineering", "analytics", "finance", "aligned"]:
    sql = open(f"queries/{team}.sql").read()
    if team == "analytics":
        sql = sql.replace("CURRENT_DATE", "DATE '2026-04-02'")
    print(f"{team:12s} {conn.execute(sql).fetchone()[0]}")
```

---

## Why the numbers diverge

Every disagreement is a **definitional choice** nobody wrote down:

| Question | Engineering | Analytics | Finance |
|----------|-------------|-----------|---------|
| Which statuses count? | not `cancelled` | `completed` only | `completed` + invoiced + paid |
| What period? | March 2026 calendar month | Rolling last 30 days | March 2026 calendar month |
| Currency handling? | Fall back to `amount_local` if `amount` (USD) missing | Fall back to `amount_local` if `amount` (USD) missing | USD only — drop rows where `amount` is NULL |
| Gross or net of refunds? | Gross | Net | Net |
| Pending orders? | **Included** | Excluded | Excluded |

None of these choices is "wrong" on its own. The problem is **they were never explicitly decided**. Each team picked what seemed reasonable and shipped a dashboard.

**The aligned definition** (`metrics/monthly_revenue.metric`) makes a single explicit choice for each question:

- Status = `completed` (exclude pending and cancelled).
- Calendar month (exclude rolling windows).
- USD only — rows without conversion are a data quality issue, not silent inclusions.
- Net of refunds.

Approved by all three teams on 2026-04-02. Written down. Review-able. Version-controlled.

---

## The `.metric` file as a contract

Open [`metrics/monthly_revenue.metric`](metrics/monthly_revenue.metric). Read it top to bottom. You don't need to write SQL to understand it — and that's the point:

```gherkin
Given all records from the orders table
  And status is "completed"
  And amount is present (USD converted)
  And order_date is within the current calendar month

When we calculate
  Then sum the amount column across qualifying orders
  And subtract the sum of refund_amount from the refunds table for the same orders
  And round to 2 decimal places
```

Your CFO can read that. Your data analyst can read that. Your CEO can read that. And because it sits in version control, you can track every time the definition changes, who approved it, and when.

## How to change a metric (the aligned-but-flexible workflow)

Scenario: Finance argues next quarter that "revenue" should exclude chargebacks, not just refunds. Here's the workflow:

1. **Open a PR** editing `metrics/monthly_revenue.metric` — add `And the order has no chargeback` to the `Given` block.
2. **Reviewers sign off** (finance, analytics, engineering leads).
3. **Update `queries/aligned.sql`** in the same PR to implement the new filter.
4. **CI runs `litmus check`** on the new definition to confirm the trust rules still pass.
5. **Merge.** The definition *and* the SQL update atomically — nobody ships a dashboard that drifts from the contract again.

That's metric alignment as a workflow, not a one-time meeting.

---

## What Litmus does and doesn't do

**Litmus does:**
- Store metric definitions in a readable, reviewable, version-controllable format.
- Generate plain-English docs for non-technical stakeholders (`litmus explain`).
- Run automated trust checks on the underlying data (freshness, null rates, volume, ranges).
- Fail CI when data quality degrades below the thresholds in the `Trust:` block.

**Litmus does not (yet):**
- Execute the metric calculation itself — that still lives in your SQL, dbt model, or BI tool.
- Replace dbt. It complements dbt: dbt transforms data, Litmus validates trust and documents intent.

The alignment value comes from making the definition explicit and lowering the cost of reviewing it, not from owning the query layer.

---

## About the intentional red in Step 5

When you run the demo, `litmus check` reports **6 passed, 1 failed, trust score 6/7 🔴**. The failing check is:

```
❌ Null rate on amount: 12.5% (threshold: < 5.0%) — FAILED
```

This is not a broken demo — it's the point. The seed data includes `O-005`, a EUR order whose USD conversion hasn't been recorded yet (`amount IS NULL`). The aligned spec says USD conversion is required; the trust check catches it.

Two ways to resolve:

1. **Fix the data.** Edit `seed.sql` and give `O-005` a non-NULL `amount`. Re-run — everything greens out.
2. **Loosen the threshold.** Change `must be less than 5%` to `must be less than 15%` in the `.metric` file. Re-run — check passes, but you've now explicitly said "up to 15% missing USD conversions is acceptable," which is a decision you can review later.

That's the point of the `Trust:` block: make the threshold explicit, visible in diffs, and reviewable.

## Next steps

- **Change the definition.** Edit `metrics/monthly_revenue.metric`, re-run `./run_demo.sh`, see the explain output update.
- **Break the data.** Open `seed.sql` and add a row with `status = 'completed'` but `amount = NULL`. Re-run the demo. Watch the null-rate failure get worse.
- **Fix the data.** Add a USD conversion to O-005 in `seed.sql`. Re-run — the red turns green.
- **Try your own metric.** Copy `monthly_revenue.metric` to `monthly_active_users.metric`, rewrite the `Given`/`When` blocks, and run it. The DSL reference is in [`../../docs/spec-language.md`](../../docs/spec-language.md).
