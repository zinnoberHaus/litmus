# litmus-data / litmus — dbt package

> Canonical metric contracts with built-in trust checks, materialised into
> your warehouse as part of `dbt run`.

This is the dbt-side surface of [Litmus](https://github.com/zinnoberHaus/litmus).
The Python CLI (`pip install litmus-data`) defines metrics in a portable DSL
(or YAML) and runs trust checks against the warehouse; this package makes the
check history *part of your dbt DAG* so your team queries the same trust
tables the CLI writes.

## Install

Add to your `packages.yml`:

```yaml
packages:
  - package: litmus-data/litmus
    version: [">=0.3.0", "<0.4.0"]
```

Then:

```bash
dbt deps
dbt run --select litmus
```

That creates three tables in your target schema:

| Table                     | Purpose                                                                 |
|---------------------------|-------------------------------------------------------------------------|
| `litmus_runs`             | One row per metric per run. Score, status, value sum, row count.        |
| `litmus_check_results`    | One row per trust rule per run. Rule JSON, actual value, threshold.     |
| `litmus_history`          | Fingerprints + per-column means for stateful rules (change, drift).     |

## Run trust checks

Two modes — pick one:

### Mode A — dbt run + CLI (recommended)

```bash
dbt run                                     # builds your models
litmus check metrics/ --backend warehouse   # runs trust rules, writes to the tables above
```

The CLI auto-detects the dbt project (it sees `dbt_project.yml` walking up
from cwd) and flips to `--backend warehouse` without a flag. The blueprint's
Decision 2 calls this "auto".

### Mode B — dbt-only, Python-shelled

If you don't want a second CLI invocation, add an `on-run-end` hook that
shells out to `litmus check`:

```yaml
# dbt_project.yml
on-run-end:
  - "{{ litmus.run_trust_checks() }}"
  - "{{ run_query('!litmus check metrics/ --backend warehouse') }}"
```

The second line relies on your dbt runner having `litmus` on PATH.

## Configure schema location

By default the tables land in your target schema. For Elementary-style
separation:

```yaml
# dbt_project.yml
models:
  litmus:
    +schema: litmus           # writes to `{target.schema}_litmus`
```

## Supported warehouses

| Adapter              | Tested in v0.3 | Notes                                      |
|----------------------|----------------|--------------------------------------------|
| `dbt-duckdb`         | yes            | Default local dev path. No extras needed.  |
| `dbt-postgres`       | yes            | Uses `DECIMAL`/`VARCHAR(n)`/`TIMESTAMP`.   |
| `dbt-snowflake`      | compatible     | `NUMBER(38,0)` for BIGINT, `TIMESTAMP_NTZ`.|
| `dbt-bigquery`       | compatible     | `STRING`/`INT64`/`NUMERIC` types.          |

Type dispatch lives under `macros/adapters/*.sql` — one file per adapter,
adding a new warehouse is a weekend job.

## How it hooks into the Python CLI

```
 ┌────────────┐     ┌─────────────────────────────────────┐
 │  dbt run   │ ──▶ │ on-run-end: litmus.run_trust_checks │
 └────────────┘     │   creates litmus_runs / _results /  │
                    │   _history tables                   │
                    └─────────────────────────────────────┘
                                   │
                                   ▼
 ┌───────────────────────────────────────────────────────┐
 │  litmus check metrics/ --backend warehouse             │
 │    WarehouseHistoryStore writes rows to litmus_history │
 │    (and, when --push is set, to litmus_runs/_results)  │
 └───────────────────────────────────────────────────────┘
                                   │
                                   ▼
 ┌───────────────────────────────────────────────────────┐
 │  Queries, BI, Slack /ask, the hosted UI — all read    │
 │  from the same three tables.                          │
 └───────────────────────────────────────────────────────┘
```

`WarehouseHistoryStore` lives in `litmus.checks.history.WarehouseHistoryStore`
on the Python side. Same interface as the SQLite default store; swapping is a
single `--backend` flag.

## What this package does NOT do

- **Does not replace `dbt test`.** `not_null`, `unique`, `accepted_values`
  stay where they are. Litmus trust rules are declarative checks on metric
  outputs (freshness, volume drop, change-over-change), not column assertions.
- **Does not run Python inside dbt.** The dbt-only Mode B above shells out
  via `run_query('!litmus ...')`, which is the Elementary pattern. Pure-SQL
  macros fire only the DDL + dbt-run marker.
- **Does not define metrics.** `.metric` / `.yml` files live next to your dbt
  project, and the Python CLI parses them. The dbt side only persists
  results.

## Uninstall

```bash
rm -rf dbt_packages/litmus
# Optionally drop the tables:
#   DROP TABLE litmus_runs;
#   DROP TABLE litmus_check_results;
#   DROP TABLE litmus_history;
```

## Docs

- Full installation guide: [`docs/dbt-package.md`](../../docs/dbt-package.md)
  in the Litmus repo.
- Python CLI: `pip install litmus-data && litmus --help`.
- Source: <https://github.com/zinnoberHaus/litmus>.

## License

Apache-2.0, matching the Python package.
