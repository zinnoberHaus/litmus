# Spec Language Reference

Litmus metric contracts come in two equal-peer surfaces: a **`.metric` DSL** (Gherkin-shaped, plain English, the memorable one) and a **YAML alternative** (for engineers coming from dbt / Cube / MetricFlow, and for LLMs/codegen tools that emit YAML reliably). Both parse to the same `MetricSpec` — downstream code can't tell which one you wrote, and round-trip parity is CI-enforced. Pick the shape that fits your team.

This reference covers the DSL first. The [YAML alternative](#yaml-alternative) section at the end shows the exact same metric in YAML and explains when to reach for each.

Every `.metric` file follows the same structure:

```
Header → Source → Given → When → Result → Trust
```

## File Structure

### Header Block

Every `.metric` file starts with a header:

```gherkin
Metric: Monthly Revenue
Description: Total revenue from completed orders in the current calendar month
Owner: finance-team
Tags: finance, board-reporting, certified
```

| Field | Required | Description |
|-------|----------|-------------|
| `Metric:` | Yes | The metric name |
| `Description:` | No | Human-readable description |
| `Owner:` | No | Team or person responsible |
| `Tags:` | No | Comma-separated labels |

### Source Block

Declare which tables this metric reads from:

```gherkin
Source: orders
```

Multiple sources:

```gherkin
Source: subscriptions, subscription_events
```

### Given Block

Define the conditions and filters — **what data goes into this metric**.

```gherkin
Given all records from orders table
  And status is "completed"
  And order_date is within current calendar month
  And currency is converted to "USD"
```

- Starts with `Given`
- Additional conditions use `And` (indented)
- Write in plain English — these are for humans first, machines second

### When Block

Define the calculation — **how the metric is computed**.

```gherkin
When we calculate
  Then sum the amount column
  And subtract refunds
  And round to 2 decimal places
```

- Always starts with `When we calculate`
- First operation uses `Then`
- Additional operations use `And`

### Result Line

Name the output:

```gherkin
The result is "Monthly Revenue"
```

### Trust Block

Define automated data quality checks:

```gherkin
Trust:
  Freshness must be less than 6 hours
  Null rate on amount must be less than 1%
  Null rate on order_id must be 0%
  Row count must not drop more than 20% day over day
  Value must be between 100000 and 50000000
  Value must not change more than 30% month over month
```

## Trust Rules Reference

### Freshness

Check that data has been updated recently.

```
Freshness must be less than <number> <hours|minutes|days>
```

Examples:
- `Freshness must be less than 6 hours`
- `Freshness must be less than 30 minutes`
- `Freshness must be less than 1 day`

### Null Rate

Check that a column doesn't have too many missing values.

```
Null rate on <column> must be less than <number>%
Null rate on <column> must be <number>%
```

Examples:
- `Null rate on amount must be less than 1%`
- `Null rate on order_id must be 0%`

### Row Count (Volume)

Check that row count hasn't dropped unexpectedly.

```
Row count must not drop more than <number>% <period>
Row count of <table> must not drop more than <number>% <period>
```

Where `<period>` is: `day over day`, `week over week`, or `month over month`.

Examples:
- `Row count must not drop more than 20% day over day`
- `Row count of subscriptions must not drop more than 10% day over day`

### Value Range

Check that the metric value is within expected bounds.

```
Value must be between <min> and <max>
```

Examples:
- `Value must be between 100000 and 50000000`
- `Value must be between 0 and 100`
- `Value must be between 0.5% and 20%`

### Value Change

Check that the metric hasn't changed too dramatically.

```
Value must not change more than <number>% <period>
```

Examples:
- `Value must not change more than 30% month over month`
- `Value must not change more than 10% week over week`

## Comments

Lines starting with `#` are comments and ignored by the parser:

```gherkin
# This metric was last reviewed on 2024-01-15
Metric: Monthly Revenue
```

## Complete Example

```gherkin
Metric: Net Revenue Retention (NRR)
Description: Revenue retained from existing customers including expansions and contractions
Owner: finance-team
Tags: finance, investor-reporting, certified

Source: subscriptions, invoices

Given all customers who were active 12 months ago
  And they had a paid subscription
  And they are not on a free plan

When we calculate
  Then take their current monthly revenue
  And divide by their monthly revenue 12 months ago
  And multiply by 100 for percentage

The result is "Net Revenue Retention"

Trust:
  Freshness must be less than 24 hours
  Null rate on customer_id must be 0%
  Null rate on revenue must be less than 0.5%
  Value must be between 50 and 200
  Value must not change more than 10% month over month
```

## YAML alternative

> _The YAML parser ships in v0.3. The CLI dispatches on file extension (`*.metric` → DSL parser, `*.yml` / `*.yaml` → YAML parser) and both produce the same `MetricSpec`._

Every `.metric` contract has a direct YAML equivalent. The YAML surface exists for three reasons:

1. **dbt / Cube / MetricFlow muscle memory.** Engineers coming from those tools already think in YAML.
2. **LLM + codegen reliability.** Models emit YAML more reliably than a bespoke DSL.
3. **dbt hub / MCP story.** YAML is the lingua franca for tool interoperability.

The DSL stays first-class — PMs read it during Slack sign-off, and the memorable shape is how Litmus is pitched. YAML is additive, never primary. **Features land on both surfaces in the same PR**; neither can learn a field the other lacks.

### When to use which

| Use the `.metric` DSL when… | Use YAML when… |
|---|---|
| PMs review the spec (Slack sign-off, docs) | A codegen / LLM tool emits it |
| You want the full Gherkin narrative | You're porting from a dbt `schema.yml` mental model |
| You like reading your contracts out loud | You need machine-editable headers (ownership, tags) |

### Shape

The YAML shape mirrors the DSL section-for-section. File extension: `.yml` or `.yaml`. The top-level is a single metric:

```yaml
# metrics/monthly_revenue.yaml
metric: Monthly Revenue
description: Total revenue from completed orders in the current calendar month
owner: finance-team
tags: [finance, reporting]

# Optional — opt in to the v0.3 Slack sign-off flow.
signoff_required: false

sources:
  - orders

given:
  - all records from orders table
  - status is "completed"
  - order_date is within current calendar month

when:
  - sum the amount column

result: Monthly Revenue

trust:
  - freshness: { max: 6 hours }
  - null_rate: { column: amount, max: 1% }
  - volume:    { max_drop: 20%, period: day over day }
  - range:     { min: 100000, max: 50000000 }
  - change:    { max: 30%, period: month over month }
```

### Section-by-section equivalents

| DSL line | YAML key |
|---|---|
| `Metric: <name>` | `metric: <name>` |
| `Description: <text>` | `description: <text>` |
| `Owner: <team>` | `owner: <team>` |
| `Tags: <a, b, c>` | `tags: [a, b, c]` |
| `Source: <t1, t2>` | `sources: [t1, t2]` |
| `Given ... And ...` | `given: [item1, item2]` — each list entry is one clause, verbatim |
| `When we calculate / Then ... / And ...` | `when: [op1, op2]` — each list entry is one operation |
| `The result is "<name>"` | `result: <name>` |
| `Trust:` block | `trust: [rule1, rule2]` — see trust rule table below |

### Trust rule shapes

Each entry in the `trust:` list is a one-key mapping; the key names the rule type, the value is the rule's config. The DSL sentence and the YAML mapping compile to the same `TrustRule`.

| DSL | YAML |
|---|---|
| `Freshness must be less than 6 hours` | `- freshness: { max: 6 hours }` |
| `Null rate on amount must be less than 1%` | `- null_rate: { column: amount, max: 1% }` |
| `Null rate on order_id must be 0%` | `- null_rate: { column: order_id, max: 0% }` |
| `Row count must not drop more than 20% day over day` | `- volume: { max_drop: 20%, period: day over day }` |
| `Row count of subscriptions must not drop more than 10% day over day` | `- volume: { table: subscriptions, max_drop: 10%, period: day over day }` |
| `Value must be between 100000 and 50000000` | `- range: { min: 100000, max: 50000000 }` |
| `Value must not change more than 30% month over month` | `- change: { max: 30%, period: month over month }` |
| `Duplicate rate on invoice_id must be 0%` | `- duplicate_rate: { column: invoice_id, max: 0% }` |
| `Schema must not drift` | `- schema_drift: {}` |
| `Mean of net_amount must not change more than 25% month over month` | `- distribution_shift: { column: net_amount, max: 25%, period: month over month }` |

### Parity and round-trip guarantee

A parametrised test in `tests/test_parser/` iterates every example under `examples/` and asserts:

1. `parse_metric_file("x.metric")` and `parse_metric_file("x.yaml")` produce **byte-identical** `MetricSpec` dataclasses.
2. Serialising the `MetricSpec` back out via both emitters yields files that themselves re-parse to the same spec.

If you add a new DSL rule, add the YAML shape in the same PR — CI will fail otherwise. See `REFACTOR_BLUEPRINT.md` §2.1 for the full parity rule.

### Example

The YAML twin of [`examples/metrics/revenue.metric`](../examples/metrics/revenue.metric) lives at [`examples/metrics/revenue.yaml`](../examples/metrics/revenue.yaml). Both parse to the same spec; `litmus check examples/metrics/` picks up both files automatically.

