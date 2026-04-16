# Examples

Runnable `.metric` files that demonstrate the Litmus DSL. Every example targets a distinct pattern — if you're looking for the closest analog to your own metric, start by matching the pattern rather than the domain.

**New here?** Start with [`alignment/`](alignment/README.md) — a complete end-to-end walkthrough of Litmus's core use case (the "3 teams, 3 numbers" problem) with seed data, four SQL queries, the aligned `.metric` file, and a runnable demo script.

## Index

| File | Pattern | Illustrates |
|------|---------|-------------|
| `metrics/revenue.metric` | Simple sum with range check | Monthly sum, currency conversion, multi-source (orders + invoices). |
| `metrics/mrr.metric` | Recurring-revenue computation | Subscription aggregation, longer freshness window. |
| `metrics/churn.metric` | Rate from two counts | Cohort filtering, bounded percentage range. |
| `metrics/dau.metric` | Count-distinct with strict null rate | Event source, 0% null on identity column, 1-hour freshness. |
| `metrics/conversion_rate.metric` | Funnel conversion as % | Division + ratio in `When`, multi-event source, percentage bounds. |
| `metrics/aov.metric` | Ratio (sum / count) | Division in `When`, currency filter, moderate range bounds. |
| `metrics/support_sla.metric` | Time-based operational SLA | Duration arithmetic, percentile aggregation, tight freshness. |
| `metrics/cart_abandonment.metric` | "Lower is better" percentage | Inverse-sense range (40–85% is healthy), week-over-week stability. |

## Running them

The bundled `litmus.yml` uses DuckDB in-memory, so nothing else is needed:

```bash
litmus check examples/metrics/revenue.metric    # single metric
litmus check examples/metrics/                  # all metrics in the dir
litmus explain examples/metrics/dau.metric      # plain-English doc
litmus parse examples/metrics/aov.metric        # debug: show parsed MetricSpec
```

If you want the checks to hit real data rather than empty tables, seed DuckDB first:

```bash
duckdb examples.db < examples/sample_data/seed.sql
# then point litmus.yml at examples.db instead of :memory:
```

## Writing your own

Start by **copying the closest pattern above** and edit in place — don't write from scratch. The DSL is forgiving about the free-text parts (`Given` / `When` / `Description`) but strict about section order: `Header → Source → Given → When → Result → Trust?`.

See [`docs/spec-language.md`](../docs/spec-language.md) for the full reference.

## Checklist for a good example metric

- [ ] `Description` is one sentence a business user would understand.
- [ ] `Given` clauses read in plain English — no SQL fragments.
- [ ] `When we calculate` has the actual math, step by step.
- [ ] `Trust` block uses **every** rule type the metric needs — freshness, null rate on identity columns, volume, range, change-over-period.
- [ ] Range bounds reflect *your* real data, not lazy defaults. A range of `0 to 10^9` is useless; a tight range catches bugs.
