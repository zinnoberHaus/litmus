<p align="center"><img src="docs/assets/logo.png" alt="Litmus" width="160"></p>

<p align="center"><em>Canonical metric contracts for engineers, AI-answered questions for PMs, embeddable trust badges for everyone.</em></p>

<p align="center">
  <a href="https://pypi.org/project/litmus-data/"><img src="https://img.shields.io/pypi/v/litmus-data.svg" alt="PyPI version"></a>
  <a href="https://pypi.org/project/litmus-data/"><img src="https://img.shields.io/pypi/pyversions/litmus-data.svg" alt="Python versions"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-Apache%202.0-green.svg" alt="License: Apache 2.0"></a>
  <a href="https://github.com/zinnoberHaus/litmus/actions/workflows/ci.yml"><img src="https://github.com/zinnoberHaus/litmus/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://pepy.tech/project/litmus-data"><img src="https://static.pepy.tech/badge/litmus-data" alt="Downloads"></a>
</p>

---

## What is Litmus?

Litmus is the **trust-and-approval layer for business metrics**. One underlying spec — three audiences:

| | Engineers | PMs | Everyone |
|---|---|---|---|
| **Surface** | `.metric` / YAML, dbt package, CLI, GitHub Action | Slack sign-off, `/ask <question>` | Live trust badge SVG |
| **Lives in** | Your repo + CI | Slack | Notion, Confluence, README, GitHub Pages |
| **They say** | "My tests pass." | "Revenue is $4.2M — and it's green." | "The badge says green. I believe the number." |

Engineers define canonical metric contracts. PMs ask questions and approve definitions in Slack. Everyone sees a live trust badge wherever metrics are referenced. Same underlying `MetricSpec`, three cleanly separated surfaces.

> **v0.3 note.** The engineer surface (CLI + `.metric` DSL + hosted catalog + badge) ships today. The **dbt package**, the **Slack sign-off + `/ask` bot**, and the **three-audience UI** are shipping alongside v0.3 — this README marks which sections describe "today" vs "v0.3 in flight". Nothing described here is vapourware; everything has an issue and a reviewer.

## The problem

Your CEO asks: *"What was our revenue last month?"*

The data analyst says $4.2M. Finance says $3.8M. Engineering says $4.5M.

Three teams, three numbers, zero trust — because metric definitions live in SQL files, dbt models, and spreadsheet formulas that business users can't read or approve. Nobody agrees on what "revenue" means, and nobody knows if the underlying data is trustworthy.

## The solution

Litmus lets you define metrics as **contracts** that every stakeholder can read — engineers version them in git, PMs approve them in Slack, everyone sees a live trust badge. The contract is a `.metric` file (or a YAML file; both parse to the same spec). The badge updates on every run.

## Install

```bash
pip install litmus-data
litmus init           # scaffold litmus.yml + metrics/ folder
litmus check metrics/ # run trust checks
```

## Write a metric

`metrics/revenue.metric`:

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

Prefer YAML? A peer file at `metrics/revenue.yaml` parses to the same `MetricSpec`. Full YAML syntax is specified in [`docs/spec-language.md`](docs/spec-language.md#yaml-alternative). DSL ↔ YAML round-trip parity is CI-enforced. _(YAML parser ships in v0.3.)_

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

## How engineers use Litmus

### CLI

| Command | What it does |
|---------|--------------|
| `litmus init` | Scaffold `litmus.yml` and a starter `metrics/example.metric`. |
| `litmus check <path>` | Parse every `.metric` / `.yml` under `<path>` and run its trust rules against the warehouse. Exits non-zero on failure. Add `--push` to ingest results into a hosted catalog. |
| `litmus parse <file>` | Dump the parsed `MetricSpec` — useful when debugging spec changes. |
| `litmus explain <file>` | Render a plain-English description from a spec (non-engineer friendly). |
| `litmus explain-run <run-id>` | Ask Claude for a hypothesis + suggested action on a failed run (requires the `[ai]` extras and an Anthropic API key on the server). |
| `litmus import-dbt <manifest.json>` | Seed `.metric` files from an existing dbt `manifest.json`. Add `--push` to also ingest lineage into the catalog. |
| `litmus export --to dbt <path>` | Emit dbt `schema.yml` plus singular tests from a `.metric` file, so Litmus rules run inside a dbt project. |
| `litmus reconcile <slug>` | Compare the latest warehouse value to Looker / Tableau for the same metric and flag drift. Requires the `[bi]` extras. |
| `litmus share <path>` | Render a self-contained HTML card (with check results) you can paste into Slack or Notion. |
| `litmus report <dir>` | Produce an HTML, Markdown, or JSON report across a whole metrics folder. |

Run `litmus <cmd> --help` for the full flag list.

### Trust checks

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

Change / distribution / volume rules compare against a history store. By default this is SQLite at `~/.litmus/history.db`; teams running the dbt package persist history to the warehouse instead (see "Run it inside dbt" below).

### Supported warehouses

| Warehouse | Status | Install |
|-----------|--------|---------|
| DuckDB | Built-in, zero config | included |
| SQLite | Built-in | included |
| PostgreSQL | Supported | `pip install 'litmus-data[postgres]'` |
| Snowflake | Supported | `pip install 'litmus-data[snowflake]'` |
| BigQuery | Supported | `pip install 'litmus-data[bigquery]'` |
| All of the above | | `pip install 'litmus-data[all]'` |

Warehouse credentials are read from the `LITMUS_WAREHOUSE_USER` and `LITMUS_WAREHOUSE_PASSWORD` environment variables — never from `litmus.yml`.

### Run it on every PR

Drop this into `.github/workflows/litmus-check.yml`:

```yaml
name: Litmus trust check
on:
  pull_request:
    paths: ["metrics/**/*.metric", "metrics/**/*.yml", "litmus.yml"]

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

### Run it inside dbt

> _Shipping in v0.3. See `dbt_packages/litmus/` (landing alongside this release) and [`docs/getting-started.md`](docs/getting-started.md) for the install walkthrough._

For teams that already run dbt, Litmus ships as a **dbt package** that follows the [Elementary](https://github.com/elementary-data/elementary) pattern: an `on-run-end` hook runs your trust rules and materialises results to two warehouse tables (`{schema}_litmus.litmus_runs` and `litmus_check_results`). No separate CLI job, no separate history store — your dbt run writes both the models and their trust verdicts in the same transaction.

```yaml
# packages.yml
packages:
  - package: litmus-data/litmus
    version: [">=0.3.0", "<0.4.0"]
```

```bash
dbt deps
dbt run --select litmus    # writes litmus_runs + litmus_check_results
```

The Python CLI auto-detects a dbt project in the cwd and reads/writes the same warehouse tables, so `litmus check` and `dbt run --select litmus` are interchangeable. Pass `--backend {sqlite,warehouse,auto}` to override the detection — `auto` is the default.

## How PMs use Litmus

> _Shipping in v0.3. See `docs/install/slack.md` (landing alongside this release) for the setup walkthrough._

PMs don't read SQL, don't write YAML, and don't want to learn git. v0.3 gives them two Slack-native surfaces:

- **Sign-off on metric revisions.** When an engineer edits a `.metric` file and opens a PR (or pushes to the catalog directly), the PM who owns the metric gets a Slack message with a diff and `Approve` / `Reject` buttons. Approval is recorded on the metric revision; the audit trail is visible in the UI. Sign-off is opt-in per metric via a `signoff_required: true` flag in the spec header.
- **`/ask <question>` in any channel.** Type `/ask what was revenue last month?` — Litmus resolves the question to a catalog metric, runs the SQL against your warehouse, and posts an answer card with the value, time window, and the current trust status. No SQL, no YAML, no git. Privacy: Claude sees metric metadata and trust rules only, never raw warehouse rows. Full disclosure in `docs/ai-ask.md` (ships in v0.3).

Both surfaces use webhook-based Slack integration in v0.3 — you paste a webhook URL into the Litmus server config and create two slash commands in your workspace. A full Slack App with OAuth and Marketplace listing is deferred to v0.4.

## How everyone reads a Litmus badge

The trust badge is a small SVG (green / yellow / red / grey pill) served from the Litmus catalog:

```markdown
![](https://your-litmus-server.example.com/embed/<token>/badge.svg)
```

| Colour | Meaning |
|---|---|
| Green | All trust checks passed on the latest run. |
| Yellow | At least one check is in the warning band. |
| Red | At least one check failed or errored. |
| Grey | No recent run — the metric exists but hasn't been checked lately. |

Drop the URL into Notion, Slack, Confluence, a deck, a README. Every rendered badge wraps in an `<a xlink:href>` pointing at the metric detail page — so anyone can click through and see why it's green (or why it's not). Size variants (`?size=small|medium|large`) and shields.io-style customisation (`?label=`, `?color=`, `?style=for-the-badge`) let you match whatever surface you're embedding into. Platform-by-platform embedding guide: [`docs/badges.md`](docs/badges.md).

## Hosted catalog (`litmus_api/`)

The CLI is enough on its own. But teams that want a shared metric catalog, run history, embeddable trust badges, and AI-powered failure explanations can run the server:

```bash
pip install 'litmus-data[server]'
alembic -c litmus_api/migrations/alembic.ini upgrade head
uvicorn litmus_api.main:app
```

- `litmus check metrics/ --push --endpoint https://... --api-key $LITMUS_API_KEY` sends results to the catalog after every local or CI run.
- `GET /embed/<token>/badge.svg` renders a trust pill (green / yellow / red / grey) that never 404s — safe to drop into Notion, Slack, GitHub READMEs. `?size=small|medium|large` and shields.io-style `?label=`/`?color=`/`?style=` params are supported; see [`docs/badges.md`](docs/badges.md).
- `GET /embed/<token>.html` is the OpenGraph share card — paste the metric URL in Slack and the live badge unfurls as the preview image.
- `GET /api/v1/metrics/{id}/revisions` returns the full spec-edit history so you can correlate a trust regression to the commit that changed the definition.
- Turn on AI explanations with `pip install 'litmus-data[ai]'` and `export LITMUS_ANTHROPIC_API_KEY=...`; the UI then surfaces a "Why did this fail?" button on failed runs.

A Next.js UI (`ui/`) ships alongside the API with a catalog, per-metric detail pages (lineage + reconciliation + trust history), and a proxy for the embed route. Both are containerised via `deploy/docker-compose.yml`.

### GitHub integration

If you're running a Litmus catalog server, point a GitHub webhook at `POST <your-server>/webhooks/github` and every push that touches a `.metric` file will upsert it into the catalog automatically — no CI job required.

```
Payload URL:   https://litmus.example.com/webhooks/github
Content type:  application/json
Secret:        <a random string you also set as LITMUS_GITHUB_WEBHOOK_SECRET on the server>
Events:        Just the push event
```

The webhook only fetches from public repos (it uses `raw.githubusercontent.com`). Full setup walkthrough: [`docs/github-webhook.md`](docs/github-webhook.md).

### BI reconciliation

Same metric, three tools, three numbers — until now. Install `pip install 'litmus-data[bi]'`, attach a Looker or Tableau identifier to any catalog metric (`POST /api/v1/metrics/{id}/bi-mappings`), and `litmus reconcile <metric>` will fetch every BI-tool value, compare it to the latest warehouse run, and flag drift as pass (<2%), warn (<10%), or fail. The UI's reconciliation panel always renders — the warehouse row is synthesized from the latest run even before any mappings exist. Setup + connector identifier formats: [`docs/bi-connectors.md`](docs/bi-connectors.md).

## How it fits with dbt and semantic layers

Litmus is a **trust / contract layer**, not a replacement for your transformation or semantic tools. dbt and Cube / LookML / MetricFlow answer *"how is this metric computed?"* — Litmus answers *"is the metric currently trustworthy, and did the business sign off on its definition?"* `litmus import-dbt` seeds specs from an existing dbt project, `litmus export --to dbt` emits dbt singular tests, and the `litmus` dbt package (v0.3) runs your trust rules inside `dbt run`. The two stacks are designed to sit side by side.

## Documentation

- [Getting Started](docs/getting-started.md) — engineer, PM, and viewer onboarding paths
- [Spec Language Reference](docs/spec-language.md) — `.metric` DSL + the YAML alternative
- [JSON Report Schema](docs/json-schema.md)
- [Architecture overview](docs/ARCHITECTURE.md) · [Dagster-of-trust model](docs/DAGSTER_MODEL.md)
- [GitHub webhook setup](docs/github-webhook.md) · [BI reconciliation setup](docs/bi-connectors.md) · [AI explanations](docs/ai-explanations.md)
- Example specs — [SaaS](docs/examples/saas-metrics), [e-commerce](docs/examples/ecommerce-metrics), and [`examples/metrics/`](examples/metrics)
- [Changelog](CHANGELOG.md)
- [Contributing](CONTRIBUTING.md)
- [Code of Conduct](CODE_OF_CONDUCT.md)

## License

Apache 2.0 — see [LICENSE](LICENSE).
