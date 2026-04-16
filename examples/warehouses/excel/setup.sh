#!/usr/bin/env bash
# 1. Generate the Excel workbook (requires openpyxl).
# 2. Read it into DuckDB via the spatial extension (which bundles st_read).

set -euo pipefail
cd "$(dirname "$0")"

rm -f budget.duckdb

python generate_workbook.py

duckdb budget.duckdb <<'SQL'
INSTALL spatial;
LOAD spatial;
CREATE TABLE budget AS
  SELECT
    dept,
    line_item,
    CAST(budgeted AS DOUBLE) AS budgeted,
    CAST(spent AS DOUBLE)    AS spent,
    CAST(as_of AS DATE)      AS as_of,
    CURRENT_TIMESTAMP        AS updated_at
  FROM st_read('budget.xlsx', layer='Budget');
SELECT 'Loaded ' || COUNT(*) || ' budget rows' AS status FROM budget;
SQL

echo "Ready. Run: litmus check budget.metric"
