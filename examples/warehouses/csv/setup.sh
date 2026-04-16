#!/usr/bin/env bash
# Seed a DuckDB file from the CSV so Litmus can query it.
# DuckDB's read_csv_auto figures out column types for you.

set -euo pipefail
cd "$(dirname "$0")"

rm -f sales.duckdb

duckdb sales.duckdb <<'SQL'
CREATE TABLE sales AS SELECT * FROM read_csv_auto('sales.csv');
SELECT 'Loaded ' || COUNT(*) || ' rows' AS status FROM sales;
SQL

echo "Ready. Run: litmus check sales.metric"
