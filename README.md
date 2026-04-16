<p align="center"><img src="docs/assets/logo.png" alt="Litmus" width="160"></p>

<p align="center"><em>BDD-style metric definitions with built-in data trust checks.</em></p>

<p align="center">
  <a href="https://pypi.org/project/litmus-data/"><img src="https://img.shields.io/pypi/v/litmus-data.svg" alt="PyPI version"></a>
  <a href="https://pypi.org/project/litmus-data/"><img src="https://img.shields.io/pypi/pyversions/litmus-data.svg" alt="Python versions"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-Apache%202.0-green.svg" alt="License: Apache 2.0"></a>
  <a href="https://github.com/zinnoberHaus/litmus/actions/workflows/ci.yml"><img src="https://github.com/zinnoberHaus/litmus/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://pepy.tech/project/litmus-data"><img src="https://static.pepy.tech/badge/litmus-data" alt="Downloads"></a>
</p>

---

## Install

```bash
pip install litmus-data
litmus init           # scaffold litmus.yml + metrics/ folder
litmus check metrics/ # run trust checks
```

## The problem

Your CEO asks: *"What was our revenue last month?"*

The data analyst says $4.2M. Finance says $3.8M. Engineering says $4.5M.

Three teams, three numbers, zero trust — because metric definitions live in SQL files, dbt models, and spreadsheet formulas that business users can't read or approve. Nobody agrees on what "revenue" means, and nobody knows if the underlying data is trustworthy.

## The solution

Litmus lets you define metrics in plain English that business stakeholders can review and sign off on, then validates the data continuously. A `.metric` file is a Gherkin-inspired contract — `Given` / `When` / `Then` for the business logic, plus a `Trust:` block with executable data-quality rules.

## Quickstart

Write `metrics/revenue.metric`:

```gherkin
Metric: Monthly Revenue
Description: Total revenue from completed orders in the current calendar month
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
  Freshness must be less than 6 hours
  Null rate on amount must be less than 1%
  Row count must not drop more than 20% day over day
  Value must be between 100000 and 50000000
  Value must not change more than 30% month over month
```

Run the checks:

```
$ litmus check metrics/revenue.metric

Monthly Revenue
   Owner: finance-team

   Trust Checks:
   PASS  Freshness: 2 hours (threshold: < 6 hours)
   PASS  Null rate on amount: 0.3% (threshold: < 1%)
   WARN  Row count: -18% day-over-day (threshold: < 20%)
   PASS  Value: $4,200,000 (range: $100,000 – $50,000,000)
   PASS  Change month-over-month: +12% (threshold: < 30%)

   Trust Score: 4.5 / 5
```

Generate a stakeholder-friendly explanation:

```bash
litmus explain metrics/revenue.metric
```

## What you get

| Command | What it does |
|---------|--------------|
| `litmus init` | Scaffold `litmus.yml` and a starter `metrics/example.metric`. |
| `litmus check <path>` | Parse every `.metric` under `<path>` and run its trust rules against the warehouse. Exits non-zero on failure. |
| `litmus parse <file>` | Dump the parsed `MetricSpec` — useful when debugging DSL changes. |
| `litmus explain <file>` | Render a plain-English description from a spec (non-engineer friendly). |
| `litmus import-dbt <manifest.json>` | Seed `.metric` files from an existing dbt `manifest.json`. |
| `litmus export --to dbt <path>` | Emit dbt `schema.yml` plus singular tests from a `.metric` file, so Litmus rules run inside a dbt project. |
| `litmus share <path>` | Render a self-contained HTML card (with check results) you can paste into Slack or Notion. |
| `litmus report <dir>` | Produce an HTML, Markdown, or JSON report across a whole metrics folder. |

Run `litmus <cmd> --help` for the full flag list.

## Trust checks

Nine built-in check types, all declarable inside the `Trust:` block:

- **Freshness** — maximum age of the most recent row (`Freshness must be less than 6 hours`).
- **Null rate** — share of nulls in a column (`Null rate on amount must be less than 1%`).
- **Volume** — row-count drop vs the previous period (`Row count must not drop more than 20% day over day`).
- **Range** — inclusive bounds on the metric's value (`Value must be between 100000 and 50000000`).
- **Change** — period-over-period movement on the value (`Value must not change more than 30% month over month`).
- **Duplicate rate** — uniqueness guard on a column (`Duplicate rate on invoice_id must be 0%`).
- **Schema drift** — fail if the source table's columns change (`Schema must not drift`).
- **Distribution shift** — flag when a column's distribution moves beyond a threshold (`Mean of net_amount must not change more than 25% month over month`).
- **Custom SQL** — pluggable hook in `litmus/checks/custom.py` for rules the DSL doesn't express yet.

Change / distribution / volume rules compare against a SQLite history store (`~/.litmus/history.db` by default, overridable via `LITMUS_HISTORY_DB` or `--history-db`).

## Supported warehouses

| Warehouse | Status | Install |
|-----------|--------|---------|
| DuckDB | Built-in, zero config | included |
| SQLite | Built-in | included |
| PostgreSQL | Supported | `pip install 'litmus-data[postgres]'` |
| Snowflake | Supported | `pip install 'litmus-data[snowflake]'` |
| BigQuery | Supported | `pip install 'litmus-data[bigquery]'` |
| All of the above | | `pip install 'litmus-data[all]'` |

Warehouse credentials are read from the `LITMUS_WAREHOUSE_USER` and `LITMUS_WAREHOUSE_PASSWORD` environment variables — never from `litmus.yml`.

## Run it on every PR

Drop this into `.github/workflows/litmus-check.yml`:

```yaml
name: Litmus trust check
on:
  pull_request:
    paths: ["metrics/**/*.metric", "litmus.yml"]

permissions:
  pull-requests: write
  contents: read

jobs:
  litmus:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - id: litmus
        uses: zinnoberHaus/litmus@v0
        with:
          path: metrics/
      - if: always() && github.event.pull_request
        uses: marocchino/sticky-pull-request-comment@v2
        with:
          header: litmus
          message: ${{ steps.litmus.outputs.summary-markdown }}
```

The composite action is defined in [`action.yml`](action.yml). Inputs: `path` (required), `config`, `extras` (e.g. `postgres,snowflake`), `fail-on-warning`, `litmus-version`. Outputs: `report-json`, `trust-score`, `summary-markdown`. An annotated copy of this workflow lives at [`.github/workflows/litmus-check.example.yml`](.github/workflows/litmus-check.example.yml).

## How it fits with dbt and semantic layers

Litmus is a **trust / contract layer**, not a replacement for your transformation or semantic tools. dbt and Cube / LookML / MetricFlow answer *"how is this metric computed?"* — Litmus answers *"is the metric currently trustworthy, and did the business sign off on its definition?"* `litmus import-dbt` seeds specs from an existing dbt project, and `litmus export --to dbt` emits dbt singular tests so the same rules can run inside a dbt CI pipeline. The two stacks are designed to sit side by side.

## Documentation

- [Getting Started](docs/getting-started.md)
- [Spec Language Reference](docs/spec-language.md)
- [JSON Report Schema](docs/json-schema.md)
- Example specs — [SaaS](docs/examples/saas-metrics), [e-commerce](docs/examples/ecommerce-metrics), and [`examples/metrics/`](examples/metrics)
- [Changelog](CHANGELOG.md)
- [Contributing](CONTRIBUTING.md)
- [Code of Conduct](CODE_OF_CONDUCT.md)

## License

Apache 2.0 — see [LICENSE](LICENSE).
