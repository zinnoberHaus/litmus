#!/usr/bin/env bash
# Create a persistent DuckDB file and load the seed data.
# Uses the Python duckdb module (shipped with litmus) so the storage
# format matches the one litmus reads with.

set -euo pipefail
cd "$(dirname "$0")"

rm -f analytics.duckdb

python - <<'PY'
import duckdb
sql = open("seed.sql").read()
conn = duckdb.connect("analytics.duckdb")
conn.execute(sql)
count = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
print(f"Loaded {count} events")
PY

echo "Ready. Run: litmus check signups.metric"
