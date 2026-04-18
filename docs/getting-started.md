# Getting Started

Litmus is the trust-and-approval layer for business metrics — one underlying spec, three audiences. Pick the path that matches you.

| I am a… | Start here |
|---|---|
| **Engineer** who writes dbt models, SQL, or `.metric` files | [Engineer path](#engineer-path) |
| **PM, analyst, or business owner** who just wants the number | [PM path](#pm-path) |
| **Anyone else** who sees a Litmus badge somewhere | [Viewer path](#viewer-path) |

---

## Engineer path

You write the metric contract. The CLI runs trust checks locally and in CI; the dbt package runs them inside `dbt run`; the hosted catalog stores revisions and renders the badge.

### 1. Install

```bash
pip install litmus-data
```

Warehouse-specific extras (DuckDB + SQLite are built in):

```bash
pip install 'litmus-data[postgres]'    # PostgreSQL
pip install 'litmus-data[snowflake]'   # Snowflake
pip install 'litmus-data[bigquery]'    # BigQuery
pip install 'litmus-data[all]'         # all of the above
```

### 2. Scaffold a project

```bash
litmus init
```

This creates:

- `litmus.yml` — warehouse connection + defaults
- `metrics/` — one `.metric` file per metric
- `metrics/example.metric` — a starter metric against seeded demo data
- `.env.example` — credential template (copy to `.env`, then `source .env`)

### 3. Configure your warehouse

Edit `litmus.yml`:

```yaml
warehouse:
  type: duckdb       # zero-config default
  database: "demo.duckdb"
```

For production warehouses:

```yaml
warehouse:
  type: snowflake
  account: your-account.snowflakecomputing.com
  database: analytics
  schema: public
```

Credentials come from environment variables — never from `litmus.yml`:

```bash
export LITMUS_WAREHOUSE_USER=your_user
export LITMUS_WAREHOUSE_PASSWORD=your_password
```

### 4. Write your first metric contract

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

Prefer YAML? Write `metrics/revenue.yaml` instead — same `MetricSpec`, same CLI. See the [YAML alternative](spec-language.md#yaml-alternative) section in the spec language reference. _(YAML parser ships in v0.3.)_

### 5. Run trust checks

```bash
litmus check metrics/revenue.metric   # single file
litmus check metrics/                 # whole directory
```

Exit code is non-zero if any check fails or errors (warnings alone don't fail).

### 6. Run it inside dbt (v0.3)

> _Shipping in v0.3 as `dbt_packages/litmus/` — alongside this release. See `docs/install/dbt.md` for the full walkthrough once it lands._

If you already run dbt, install Litmus as a dbt package instead of wiring a separate CLI job. Trust verdicts materialise to two warehouse tables (`{schema}_litmus.litmus_runs` and `litmus_check_results`) on every `dbt run`.

```yaml
# packages.yml
packages:
  - package: litmus-data/litmus
    version: [">=0.3.0", "<0.4.0"]
```

```bash
dbt deps
dbt run --select litmus
```

Same `.metric` files. Same trust rules. No separate history store — your warehouse becomes the source of truth. The Python CLI's new `--backend warehouse` flag reads/writes those same tables; `--backend auto` (the default) detects the dbt project and does the right thing.

### 7. Run it on every PR

```yaml
# .github/workflows/litmus-check.yml
name: Litmus trust check
on:
  pull_request:
    paths: ["metrics/**/*.metric", "metrics/**/*.yml", "litmus.yml"]

jobs:
  litmus:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: zinnoberHaus/litmus@v0
        with:
          path: metrics/
```

The action is defined in [`action.yml`](../action.yml) at the repo root.

### 8. Push results to a hosted catalog (optional)

```bash
pip install 'litmus-data[server]'
alembic -c litmus_api/migrations/alembic.ini upgrade head
uvicorn litmus_api.main:app
```

Then from CI:

```bash
litmus check metrics/ --push --endpoint https://litmus.example.com --api-key $LITMUS_API_KEY
```

The catalog stores every run, renders the SVG trust badge, and (with the `[ai]` extras) powers "Why did this fail?" explanations on failed runs.

### CLI reference

| Command | Description |
|---------|-------------|
| `litmus init` | Initialize a new project |
| `litmus check <path>` | Run trust checks on a file or directory |
| `litmus parse <file>` | Show the parsed `MetricSpec` |
| `litmus explain <file>` | Plain-English explanation (non-engineer friendly) |
| `litmus report <dir>` | HTML / Markdown / JSON report |
| `litmus import-dbt <manifest>` | Seed `.metric` files from a dbt manifest |
| `litmus export --to dbt <path>` | Emit dbt `schema.yml` + singular tests |
| `litmus reconcile <slug>` | Compare warehouse vs Looker / Tableau values |
| `litmus share <path>` | Single-file HTML card for Slack / Notion |

### Common options

| Option | Description |
|--------|-------------|
| `--config, -c` | Path to `litmus.yml` |
| `--verbose, -v` | Show detailed output |
| `--format, -f` | Output format (`console`, `json`, `html`, `markdown`) |
| `--output, -o` | Write output to a file |
| `--backend` | _(v0.3)_ `sqlite`, `warehouse`, or `auto` — where to persist run history |
| `--version` | Show version |

---

## PM path

> _The PM surface ships in v0.3. Setup walkthrough: `docs/install/slack.md` (lands alongside the release)._

You don't read SQL, don't write YAML, and don't want to learn git. Litmus gives you two Slack-native surfaces.

### Ask a question

In any Slack channel:

```
/ask what was revenue last month?
```

Litmus resolves the question to a catalog metric, runs the query against the warehouse, and posts a card with:

- The value (`$4.22M`)
- The time window (`March 2026`)
- The trust status (green / yellow / red with a one-line why)
- A link to the metric detail page

No SQL, no YAML, no git. If the question is ambiguous, Litmus responds with a 1-click disambiguator listing the top candidate metrics.

Privacy: the AI model that interprets your question sees metric names, descriptions, trust rules, and recent run aggregates — never raw warehouse rows or generated SQL. Full disclosure in `docs/ai-ask.md`.

### Approve a metric definition

When an engineer edits a `.metric` file that you own, Litmus posts a Slack message with:

- A diff of what changed (plain English, not code)
- `Approve` / `Reject` buttons

Your approval is stamped onto the metric revision and visible on the detail page. Every badge rendered after approval carries the "signed off" indicator. Sign-off is opt-in per metric — engineers declare `signoff_required: true` in the spec header.

---

## Viewer path

You see a Litmus badge in someone's Notion page, Slack thread, README, or deck. Here's how to read it.

### What the colours mean

| Colour | Meaning |
|---|---|
| **Green** | All trust checks passed on the latest run. You can quote the number. |
| **Yellow** | At least one check is in the warning band. The number is probably fine, but read the panel before citing it in a board deck. |
| **Red** | At least one check failed or errored. Do not quote this number until a data engineer has investigated. |
| **Grey** | No recent run. The metric exists but hasn't been checked lately — the value shown may be stale. |

### Click the badge

Every Litmus badge is a live link back to the metric's detail page on the catalog server that serves it. Clicking the badge shows:

- The plain-English contract (what this metric means, who owns it, what the trust rules are)
- The latest run's individual check results (why it's green or why it's not)
- The revision history (who changed the definition and when)
- Any Slack sign-off status

### Embed a badge yourself

If you run Litmus and want to embed a badge somewhere, see [`docs/badges.md`](badges.md) — dedicated guides for Notion, Slack, Confluence, README, and GitHub Pages. _(Ships in v0.3.)_

---

## Next steps

- Read the [Spec Language Reference](spec-language.md) for the full `.metric` and YAML syntax.
- See [`examples/metrics/`](../examples/metrics) for real-world metric contracts.
- Run `litmus explain <file>` to generate a stakeholder-friendly version of any spec.
- Import from dbt with `litmus import-dbt <manifest.json>`.
