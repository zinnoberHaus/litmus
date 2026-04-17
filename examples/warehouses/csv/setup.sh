#!/usr/bin/env bash
# Seed a DuckDB file from the CSV so Litmus can query it.
# Uses the Python duckdb module (shipped with litmus) so the file's
# storage format is guaranteed to match the version litmus reads with.

set -euo pipefail
cd "$(dirname "$0")"

rm -f sales.duckdb

python - <<'PY'
import duckdb
conn = duckdb.connect("sales.duckdb")
# Override updated_at with the current timestamp so the Freshness check
# reflects seed recency (the CSV ships with fixed dates for reproducibility,
# but that would make every check stale after a day).
conn.execute(
    """
    CREATE TABLE sales AS
      SELECT
        order_id,
        status,
        amount,
        order_date,
        CURRENT_TIMESTAMP AS updated_at
      FROM read_csv_auto('sales.csv')
    """
)
count = conn.execute("SELECT COUNT(*) FROM sales").fetchone()[0]
print(f"Loaded {count} rows")
PY

echo "Ready. Run: litmus check sales.metric"
