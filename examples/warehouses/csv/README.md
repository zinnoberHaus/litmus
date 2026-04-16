# CSV example

Run Litmus against a plain CSV file — no database, no setup beyond DuckDB.

## Run it

```bash
./setup.sh              # loads sales.csv into sales.duckdb
litmus check sales.metric
```

## What's here

| File | Purpose |
|------|---------|
| `sales.csv` | 15 rows of fake April 2026 sales data. |
| `sales.metric` | The metric contract (plain-English + trust rules). |
| `litmus.yml` | Points Litmus at `sales.duckdb`. |
| `setup.sh` | One-shot: loads the CSV into a DuckDB table. |

## Adapting it to your CSV

1. Replace `sales.csv` with your file (same filename keeps things simple).
2. Open `sales.metric` — change the column names in the `Given` / `When` blocks.
3. Update the `Trust:` thresholds to match your domain.
4. Re-run `./setup.sh && litmus check sales.metric`.

DuckDB's `read_csv_auto` infers types. If yours has unusual date formats or delimiters, edit the `CREATE TABLE` line in `setup.sh` — see [DuckDB docs](https://duckdb.org/docs/data/csv/overview).
