---
name: litmus-ingest
description: Register a new data source — CSV file, Postgres table, REST API, Stripe object, Google Sheet. Writes a pipelines/<source>.yaml ingest spec, runs the first load, and confirms the raw table landed in the warehouse with the right schema.
---

# /litmus-ingest

Add a new data source to a Litmus project.

## How to invoke

```
/litmus-ingest <source-name>
/litmus-ingest stripe-charges
/litmus-ingest customers --from=csv:./data/customers.csv
/litmus-ingest orders --from=postgres://...
```

If invoked without `--from=`, you'll ask the user where the data is coming from.

## Workflow you execute

1. **Identify the source type** — CSV, Postgres, REST, Stripe, Google Sheets, or "other" (escalate to `data-architect` if "other").
2. **Get the schema** — for CSV, sniff the columns. For Postgres, query `information_schema`. For REST/Stripe, ask the user for a sample payload or use the SDK's typed response.
3. **Pick the target table name** — `raw_<source_name>`. Confirm with the user if there's a naming collision.
4. **Write the ingest spec** to `pipelines/<source-name>.yaml`:
   ```yaml
   source:
     type: csv | postgres | rest | stripe | sheets
     # source-specific config; secrets via env var names, not values
   target:
     table: raw_<name>
     mode: append | replace | merge
     primary_key: <col>      # if mode=merge
   schedule: daily | hourly | manual
   columns:
     - name: <col>
       type: <duckdb-type>
   ```
5. **Run the first load** — `litmus ingest <source-name>`. Confirm row count > 0.
6. **Verify `_loaded_at` is present** on the raw table (the ingest framework adds it; sanity-check).
7. **Hand off to `data-architect`** — "raw table `raw_<name>` is loaded with N rows. Should we model this into a mart table, and if so, with what shape?" Don't write the mart yourself; that's `pipeline-builder`'s job once architecture is decided.

## Conventions

- Secrets in the YAML are env-var **names**, never values: `password: ${STRIPE_API_KEY}` not `password: sk_live_...`.
- Always include `_loaded_at` (ingest framework handles this).
- `mode: append` is the default. Use `merge` only if there's a clear primary key.
- For REST APIs with pagination, default to fetching the last 7 days on each run; full backfill is a one-time `--backfill` flag.

## Failure modes

- **Source unreachable** — fail fast with the exact env var or connection string that's wrong.
- **Schema sniff ambiguous** (e.g. CSV with mixed types) — ask the user.
- **Target table exists with different schema** — refuse to overwrite. Ask user to rename or migrate.
