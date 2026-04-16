#!/usr/bin/env bash
# Create a persistent DuckDB file and load the seed data.

set -euo pipefail
cd "$(dirname "$0")"

rm -f analytics.duckdb
duckdb analytics.duckdb < seed.sql

echo "Ready. Run: litmus check signups.metric"
