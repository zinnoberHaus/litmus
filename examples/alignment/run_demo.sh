#!/usr/bin/env bash
# End-to-end walkthrough of the metric-alignment demo.
#
# Requirements:
#   - litmus-data installed (pip install -e . from the repo root)
#   - duckdb CLI (brew install duckdb) OR run the python snippet below instead
#
# What this script does:
#   1. Seeds a DuckDB file with realistic orders/refunds data.
#   2. Runs each team's conflicting SQL query — you'll see three different numbers.
#   3. Runs the aligned SQL query — one canonical number everyone signed off on.
#   4. Runs `litmus explain` on the .metric file to show the plain-English version.
#   5. Runs `litmus check` to validate data trust against the definition.

set -euo pipefail

cd "$(dirname "$0")"
DB=alignment_demo.duckdb
rm -f "$DB"

echo
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 1. Seeding DuckDB with orders + refunds"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
duckdb "$DB" < seed.sql
echo "  Seeded $(duckdb -noheader -list "$DB" -c 'SELECT COUNT(*) FROM orders') orders and $(duckdb -noheader -list "$DB" -c 'SELECT COUNT(*) FROM refunds') refunds."

# Helper: run a .sql file against the demo DB, return the first scalar.
run_scalar() {
    local label="$1" file="$2"
    local sql
    sql=$(<"$file")
    # Pin CURRENT_DATE for the rolling-30-day analytics query.
    sql=${sql//CURRENT_DATE/DATE \'2026-04-02\'}
    printf "  %-14s " "$label"
    printf '%s\n' "$sql" | duckdb -noheader -list "$DB"
}

echo
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 2. Three teams ask 'What was revenue last month?'"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
run_scalar "engineering" queries/engineering.sql
run_scalar "analytics"   queries/analytics.sql
run_scalar "finance"     queries/finance.sql

echo
echo "  Three teams. Three queries. Three numbers. Zero trust."

echo
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 3. The aligned definition (metrics/monthly_revenue.metric)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
run_scalar "aligned"     queries/aligned.sql

echo
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 4. 'litmus explain' — what business stakeholders read"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
litmus explain metrics/monthly_revenue.metric

echo
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 5. 'litmus check' — automated data-trust validation"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
litmus check metrics/monthly_revenue.metric -c litmus.yml || true

echo
echo "  Done. Change metrics/monthly_revenue.metric and re-run — the whole"
echo "  company reads the same definition."
echo
