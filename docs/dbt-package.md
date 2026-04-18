# Installing the Litmus dbt package

> **Who this is for:** analytics engineers who already run dbt and want their
> metric trust history living next to their models in the warehouse.
> Parallels Elementary's install flow — dbt users don't have to learn a
> second CLI to get started.

Litmus ships in two complementary pieces:

1. **A Python package** (`pip install litmus-data`) — parses `.metric` files,
   runs trust checks, prints reports, pushes to the catalog.
2. **A dbt package** (`litmus-data/litmus`) — creates the warehouse tables
   trust results write into, and fires a marker on every `dbt run`.

Both agree on the same table shapes. You pick how results get in.

---

## 1. Install the dbt package

Add to `packages.yml`:

```yaml
packages:
  - package: litmus-data/litmus
    version: [">=0.3.0", "<0.4.0"]
```

Then:

```bash
dbt deps
```

If you're contributing to Litmus itself and don't want to route through dbt
Hub, use a local path:

```yaml
packages:
  - local: ../path/to/litmus/dbt_packages/litmus
```

See `examples/dbt-package-example/` for a working end-to-end setup.

## 2. Enable the on-run-end hook

In `dbt_project.yml`:

```yaml
on-run-end:
  - "{{ litmus.run_trust_checks() }}"
```

This hook:

- Creates `litmus_runs`, `litmus_check_results`, and `litmus_history` tables
  in the default schema if they don't exist (idempotent).
- Inserts one "dbt ran at T" row into `litmus_runs` with
  `triggered_by = 'dbt'`.
- Never re-runs the actual trust rules — that's the Python CLI's job (see
  step 4 below).

## 3. Run dbt

```bash
dbt run
```

You should see a log line:

```
[litmus] run_trust_checks complete — history tables ready
```

Confirm with:

```sql
SELECT * FROM litmus_runs ORDER BY started_at DESC LIMIT 5;
```

## 4. Run Python trust checks

With the tables now live, wire `litmus check` to write to them:

```bash
litmus check metrics/ --backend warehouse
```

Or let the CLI auto-detect the dbt project:

```bash
litmus check metrics/              # --backend auto (default)
```

The CLI walks up from `cwd` looking for a `dbt_project.yml`. When it finds
one, the default backend flips from `sqlite` (local history file) to
`warehouse`. Override explicitly if you need to:

| Flag                  | Behaviour                                                       |
|-----------------------|-----------------------------------------------------------------|
| `--backend auto`      | Auto-detect (default). dbt project → warehouse. Otherwise SQLite.|
| `--backend sqlite`    | Force local `~/.litmus/history.db`.                              |
| `--backend warehouse` | Force the `litmus_history` table. Requires warehouse creds.       |
| `--history-schema X`  | Override the schema the history table lives in.                  |
| `$LITMUS_BACKEND=warehouse` | Env-var equivalent of the flag.                              |
| `--no-history`        | Skip the history write entirely (disables change rules).         |

## 5. Verify

```sql
-- Runs — both dbt markers + Python CLI runs
SELECT triggered_by, status, COUNT(*)
FROM litmus_runs
GROUP BY 1, 2
ORDER BY 1, 2;

-- History — what the stateful checks compare against
SELECT metric_name, recorded_at, value_sum, row_count
FROM litmus_history
ORDER BY recorded_at DESC
LIMIT 10;
```

## Schema separation (Elementary-style)

By default everything lands in the dbt target schema. To keep Litmus tables
in a dedicated suffixed schema:

```yaml
# dbt_project.yml
models:
  litmus:
    +schema: litmus
```

The tables now materialise into `{target.schema}_litmus`. The Python CLI
follows the same convention via `--history-schema`:

```bash
litmus check metrics/ --backend warehouse --history-schema analytics_litmus
```

## Warehouse support

| Adapter           | Tested | Notes                                               |
|-------------------|--------|-----------------------------------------------------|
| `dbt-duckdb`      | yes    | Zero-config local dev. Matches the Python default.  |
| `dbt-postgres`    | yes    | Uses `DECIMAL`, `VARCHAR(n)`, `TIMESTAMP`.          |
| `dbt-snowflake`   | compat | `NUMBER(38,0)` for BIGINT, `TIMESTAMP_NTZ`.          |
| `dbt-bigquery`    | compat | `STRING`/`INT64`/`NUMERIC`; no VARCHAR lengths.     |

Adapter-specific type dispatch lives under
`dbt_packages/litmus/macros/adapters/*.sql` — if a new warehouse needs
support, add a file there and ship it with a matching Python connector.

## Troubleshooting

### `litmus check` writes to SQLite even though I installed the dbt package

`--backend auto` only flips to warehouse when it detects `dbt_project.yml`.
Run from inside your dbt project, or pass `--backend warehouse` explicitly.

### `litmus_history` doesn't exist when I run `litmus check --backend warehouse`

The Python side creates the table itself on first write — you don't need to
`dbt run` first. If the error mentions a permission problem, your warehouse
user needs `CREATE TABLE` on the schema.

### `dbt run` fails with "macro litmus.run_trust_checks not found"

You haven't run `dbt deps` since adding the package to `packages.yml`.

### I want to skip the dbt marker row

Don't enable the `on-run-end` hook. The Python CLI works without it — the
dbt marker is convenience, not a dependency.

## FAQ

**Does this replace `dbt test`?** No. `not_null`, `unique`, and
`accepted_values` stay where they are. Litmus trust rules are declarative
metric-output checks (freshness, volume drop, value range, period-over-period
change); they're orthogonal to column assertions.

**Do I have to run Python at all?** Yes, today. The v0.3 package creates
tables and fires a marker; the check-running logic lives in the Python CLI.
v0.4 explores a pure-SQL path for the stateless rules (freshness, row count,
null rate) so users can go dbt-only if they want.

**Can I query the tables from BI?** Yes — they're plain warehouse tables. Grant
SELECT to your BI role and build dashboards on top of `litmus_runs` +
`litmus_check_results`.

**How does this interact with `litmus share` / `litmus report`?** Those CLI
subcommands read the SQLite store today. v0.3 adds read paths through the
warehouse store; until then the recommendation is: use `litmus check` for
warehouse history, `litmus share` for one-off HTML dumps.

## Related docs

- Main repo: <https://github.com/zinnoberHaus/litmus>
- Getting started: [`docs/getting-started.md`](./getting-started.md)
- JSON report schema: [`docs/json-schema.md`](./json-schema.md)
- Architecture overview: [`docs/ARCHITECTURE.md`](./ARCHITECTURE.md)
