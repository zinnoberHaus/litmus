# Getting Started

## Installation

```bash
pip install litmus-data
```

For warehouse-specific connectors:

```bash
# PostgreSQL
pip install 'litmus-data[postgres]'

# Snowflake
pip install 'litmus-data[snowflake]'

# BigQuery
pip install 'litmus-data[bigquery]'

# All connectors
pip install 'litmus-data[all]'
```

## Quick Start

### 1. Initialize a Project

```bash
litmus init
```

This creates:
- `litmus.yml` — configuration file
- `metrics/` — directory for your `.metric` files
- `metrics/example.metric` — a sample metric to start with

### 2. Configure Your Warehouse

Edit `litmus.yml`:

```yaml
warehouse:
  type: duckdb       # Start with DuckDB for testing
  database: ":memory:"
```

For production warehouses:

```yaml
warehouse:
  type: snowflake
  account: your-account.snowflakecomputing.com
  database: analytics
  schema: public
```

Set credentials via environment variables:

```bash
export LITMUS_WAREHOUSE_USER=your_user
export LITMUS_WAREHOUSE_PASSWORD=your_password
```

### 3. Write Your First Metric

Create `metrics/revenue.metric`:

```gherkin
Metric: Monthly Revenue
Description: Total revenue from completed orders this month
Owner: finance-team
Tags: finance, reporting

Source: orders

Given all records from orders table
  And status is "completed"
  And order_date is within current calendar month

When we calculate
  Then sum the amount column

The result is "Monthly Revenue"

Trust:
  Freshness must be less than 24 hours
  Null rate on amount must be less than 5%
  Row count must not drop more than 25% day over day
  Value must be between 0 and 10000000
```

### 4. Run Trust Checks

```bash
litmus check metrics/revenue.metric
```

### 5. Check All Metrics

```bash
litmus check metrics/
```

### 6. Generate a Report

```bash
litmus report metrics/ --format html --output trust-report.html
```

## Next Steps

- Read the [Spec Language Reference](spec-language.md) for the full `.metric` syntax
- See [examples/](examples/) for real-world metric definitions
- Use `litmus explain <file>` to generate business-friendly documentation
- Import from dbt with `litmus import-dbt <manifest.json>`

## CLI Reference

| Command | Description |
|---------|-------------|
| `litmus init` | Initialize a new project |
| `litmus check <path>` | Run trust checks on a file or directory |
| `litmus parse <file>` | Show parsed metric structure |
| `litmus explain <file>` | Generate plain-English explanation |
| `litmus report <dir>` | Generate HTML/Markdown/JSON report |
| `litmus import-dbt <manifest>` | Import metrics from dbt |

### Common Options

| Option | Description |
|--------|-------------|
| `--config, -c` | Path to litmus.yml |
| `--verbose, -v` | Show detailed output |
| `--format, -f` | Output format (console, json, html, markdown) |
| `--output, -o` | Write output to a file |
| `--version` | Show version |
