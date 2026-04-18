# dbt + Litmus — tiny example

A minimal dbt project (DuckDB, single model) that installs the Litmus dbt
package from the sibling checkout. Exists so we can exercise
`dbt deps && dbt run` against the package without publishing to Hub.

## What lives here

```
examples/dbt-package-example/
├── dbt_project.yml       dbt project — fires litmus.run_trust_checks on-run-end
├── profiles.yml          DuckDB profile (warehouse.duckdb alongside)
├── packages.yml          local-path install of ../../dbt_packages/litmus
├── litmus.yml            points the Python CLI at the same DuckDB
├── models/
│   └── orders.sql        tiny demo fact table
└── metrics/
    └── example_revenue.metric    .metric spec that checks orders
```

## Run it

Requires `dbt-duckdb` and `litmus-data`:

```bash
pip install dbt-duckdb litmus-data
cd examples/dbt-package-example

# dbt side — creates warehouse.duckdb, materialises orders, fires on-run-end
DBT_PROFILES_DIR=$(pwd) dbt deps
DBT_PROFILES_DIR=$(pwd) dbt run

# litmus side — runs trust rules, writes into litmus_history
litmus check metrics/ --backend warehouse
```

After both commands, `warehouse.duckdb` contains:

- `orders`                 your model
- `litmus_runs`            run metadata (dbt + CLI markers)
- `litmus_check_results`   per-rule results
- `litmus_history`         change-rule / drift baselines

Inspect with DuckDB directly:

```bash
duckdb warehouse.duckdb "SELECT triggered_by, COUNT(*) FROM litmus_runs GROUP BY 1"
```

## What to break next

- Add `Null rate on status must be less than 0%` to `metrics/example_revenue.metric`
  and re-run — Litmus should flag the pending order.
- Add more `.metric` files — Litmus picks them up automatically.
- Change the `on-run-end` hook to chain `!litmus check ...` so trust checks
  run inside `dbt run` instead of as a follow-up.
