# Excel example

The "Finance emails you a spreadsheet every Monday" scenario — run trust checks on an `.xlsx` file without moving the data anywhere.

## Run it

```bash
pip install openpyxl      # one-time, if you don't have it
./setup.sh                # generates budget.xlsx, loads into budget.duckdb
litmus check budget.metric
```

## How it works

Excel files are binary, so we don't check one in. `generate_workbook.py` writes a realistic `budget.xlsx` using `openpyxl`. Then `setup.sh` uses DuckDB's `spatial` extension (which ships `st_read`, a general-purpose reader that handles `.xlsx`) to pull the sheet into a DuckDB table.

## What's here

| File | Purpose |
|------|---------|
| `generate_workbook.py` | Builds `budget.xlsx` from fixture rows. |
| `budget.metric` | Metric contract. |
| `litmus.yml` | Points at `budget.duckdb`. |
| `setup.sh` | Regenerates the xlsx and loads it. |

## Adapting it

1. Drop your `budget.xlsx` (or any workbook) next to `setup.sh` — skip `generate_workbook.py`.
2. In `setup.sh`, edit the `layer=` argument in `st_read(...)` to match your sheet name.
3. Edit `budget.metric` columns to match the sheet.
4. Re-run.

## Gotcha: date columns

`st_read` returns dates as strings by default. The `setup.sh` uses `CAST(as_of AS DATE)` to normalize. If your sheet has a differently named date column (e.g., `Updated`), adjust the CREATE TABLE block.
