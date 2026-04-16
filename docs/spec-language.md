# Spec Language Reference

Litmus uses `.metric` files to define metrics in a plain-English, BDD-style syntax. Every metric file follows the same structure:

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
