# Warehouses: Running Litmus against any data source

Four copy-paste walkthroughs showing how to point Litmus at common data formats. Each one is fully self-contained — `cd` in, run `./setup.sh`, run `litmus check`, done.

| Directory | Best for | Seed step |
|-----------|----------|-----------|
| [`csv/`](csv/) | You have a CSV export and no database | `duckdb` loads the CSV into a table |
| [`excel/`](excel/) | You have a spreadsheet from Finance | `duckdb` (spatial extension) reads the `.xlsx` |
| [`sqlite/`](sqlite/) | You have a local app DB or a Datasette-style file | `duckdb` attaches the `.sqlite` via `sqlite_scanner` |
| [`duckdb/`](duckdb/) | You already use DuckDB for analytics | Point directly at the `.duckdb` file |

## Why these all use DuckDB under the hood

Until a native SQLite / CSV / Excel connector ships, Litmus talks to DuckDB, and DuckDB happily reads every format above. That means you can try Litmus on **any tabular file you have, today**, without standing up a warehouse.

Once your trust checks are passing, swapping the `warehouse.type` in `litmus.yml` from `duckdb` to `snowflake` / `postgres` / `bigquery` is a one-line change.

## The "I just want to try it on my own file" flow

1. Pick the directory that matches your file type.
2. Replace the sample data with yours (same filename, or edit the setup script).
3. Edit `*.metric` — change the table name in `Source:` and the column names in the `Given` / `When` blocks.
4. Run `./setup.sh && litmus check *.metric`.

If the trust check fails, that's signal — your data has a real problem, or your threshold is wrong for your domain. Either way, Litmus surfaced it.
