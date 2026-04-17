#!/usr/bin/env bash
# 1. Generate the Excel workbook (requires openpyxl).
# 2. Read it into DuckDB via the spatial extension (which bundles st_read).
# Uses the Python duckdb module (shipped with litmus) so the storage
# format matches the one litmus reads with.

set -euo pipefail
cd "$(dirname "$0")"

rm -f budget.duckdb

python generate_workbook.py

python - <<'PY'
import duckdb
conn = duckdb.connect("budget.duckdb")
conn.execute("INSTALL spatial")
conn.execute("LOAD spatial")
conn.execute(
    """
    CREATE TABLE budget AS
      SELECT
        dept,
        line_item,
        CAST(budgeted AS DOUBLE) AS budgeted,
        CAST(spent AS DOUBLE)    AS spent,
        -- Litmus's Value range check defaults to a column named `amount`.
        -- Expose `spent` under that name too so the Trust block works
        -- without manually specifying a value column.
        CAST(spent AS DOUBLE)    AS amount,
        CAST(as_of AS DATE)      AS as_of,
        -- Cast to TIMESTAMP (no time zone) so DuckDB's Python bindings
        -- don't try to convert TIMESTAMPTZ via pytz (which isn't a
        -- guaranteed runtime dep).
        CAST(CURRENT_TIMESTAMP AS TIMESTAMP) AS updated_at
      FROM st_read('budget.xlsx', layer='Budget')
    """
)
count = conn.execute("SELECT COUNT(*) FROM budget").fetchone()[0]
print(f"Loaded {count} budget rows")
PY

echo "Ready. Run: litmus check budget.metric"
