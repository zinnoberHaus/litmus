#!/usr/bin/env bash
# Seed the SQLite database. Litmus's native SQLite connector reads it directly.

set -euo pipefail
cd "$(dirname "$0")"

rm -f app.sqlite
sqlite3 app.sqlite < seed.sql

echo "Ready. Run: litmus check orders.metric"
