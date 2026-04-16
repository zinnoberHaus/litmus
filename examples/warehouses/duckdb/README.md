# DuckDB example

The native path — Litmus's built-in connector talks to a persisted DuckDB file.

## Run it

```bash
./setup.sh                    # creates analytics.duckdb from seed.sql
litmus check signups.metric
```

## What's here

| File | Purpose |
|------|---------|
| `seed.sql` | Creates the `events` table and inserts 15 rows. |
| `signups.metric` | Metric contract for daily signups. |
| `litmus.yml` | Points at `analytics.duckdb`. |
| `setup.sh` | One-shot seeder. |

## Adapting it

This is the pattern you'd use for a real analytics sandbox. Replace `seed.sql` with your DDL + data loads (or let dbt build the tables into the same `.duckdb` file), then write `.metric` files alongside.

## Want in-memory instead?

Change `litmus.yml`'s `database: analytics.duckdb` to `database: ":memory:"` — but you'll need a setup step every run. Persisted files are the recommended default.
