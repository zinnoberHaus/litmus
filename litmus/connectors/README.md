# `litmus/connectors/` — Warehouse adapters

One abstract base class, one concrete connector per supported warehouse. The trust-check engine (`litmus/checks/`) talks only to `BaseConnector`, never to a specific warehouse driver.

## The contract

`base.BaseConnector` (ABC) requires:

| Method | Returns | Purpose |
|--------|---------|---------|
| `connect()` | `None` | Open connection |
| `execute_query(sql)` | `list[dict]` | Raw SQL passthrough |
| `get_table_freshness(table, ts_col=None)` | `datetime \| None` | `MAX(ts_col)` — used by freshness check |
| `get_row_count(table, conditions=None)` | `int` | `COUNT(*)` with optional `WHERE` |
| `get_null_rate(table, column)` | `float` (0.0–100.0) | Percentage of NULLs |
| `get_column_sum(table, column)` | `float \| None` | `SUM(column)` |
| `close()` | `None` | Close connection |

Plus `__enter__` / `__exit__` for context-manager use.

**Every new method on `BaseConnector` must be implemented on all concrete connectors in the same change.** A missing impl is a CI-passing runtime crash.

## Concrete connectors

| File | Warehouse | Extras | Notes |
|------|-----------|--------|-------|
| `duckdb.py` | DuckDB | included | Zero-config default. `:memory:` works out of the box. |
| `sqlite.py` | SQLite | included (stdlib) | For local app DBs, Datasette files, fixtures. Uses `sqlite3` from the Python stdlib — no extra install. |
| `postgres.py` | PostgreSQL | `[postgres]` → `psycopg2-binary` | `TIMESTAMP WITHOUT TIME ZONE`; be explicit about UTC. |
| `snowflake.py` | Snowflake | `[snowflake]` → `snowflake-connector-python` | Identifiers case-insensitive unless quoted. `account/warehouse/role` in yml. |
| `bigquery.py` | BigQuery | `[bigquery]` → `google-cloud-bigquery` | Tables are `project.dataset.table`. Auth via `GOOGLE_APPLICATION_CREDENTIALS`. |

Connectors are constructed by `../config/settings.py::get_connector(cfg)` based on `warehouse.type`. The third-party drivers are **lazy-imported inside that function** — `import litmus` must not fail when optional extras aren't installed.

## Credentials

- **Never from `litmus.yml`.** Only from env vars: `LITMUS_WAREHOUSE_USER`, `LITMUS_WAREHOUSE_PASSWORD`.
- Exposed via `WarehouseConfig.user` / `.password` properties in `../config/settings.py`.
- BigQuery uses service-account auth (`GOOGLE_APPLICATION_CREDENTIALS` env var — standard GCP pattern).
- Non-secret dialect config (`account`, `warehouse`, `role`, `schema`) lives in `litmus.yml`.

## Adding a new warehouse

Owned by the **litmus-connector** agent:

1. Create `connectors/<name>.py` extending `BaseConnector`.
2. Implement all abstract methods. Keep SQL ANSI where possible; document dialect quirks in comments.
3. Add an extras entry in `../../pyproject.toml` — keep the core install small.
4. Add a branch in `config/settings.py::get_connector` with a **lazy import**.
5. Update the Supported Warehouses table in the repo `README.md` and `docs/getting-started.md`.
6. Add `tests/test_connectors/test_<name>.py` — OK to skip if credentials are unavailable.

## Dialect quick-reference

| Operation | DuckDB | Postgres | Snowflake | BigQuery |
|-----------|--------|----------|-----------|----------|
| Null-safe division | `NULLIF(x, 0)` | `NULLIF(x, 0)` | `IFNULL` preferred | `SAFE_DIVIDE(a, b)` |
| Current timestamp | `CURRENT_TIMESTAMP` | `NOW()` / `CURRENT_TIMESTAMP` | `CURRENT_TIMESTAMP` (TZ-aware) | `CURRENT_TIMESTAMP()` |
| Identifier quoting | `"col"` | `"col"` | `"col"` (case-sensitive) | `` `col` `` |
| Table qualifier | `schema.table` | `schema.table` | `db.schema.table` | `project.dataset.table` |

## Design rules

- **Thin connectors, smart contracts.** Logic lives in `BaseConnector` method shapes; per-warehouse files stay mostly mechanical.
- **Primitive return types.** `float`, `int`, `datetime`, `list[dict]`. No warehouse-specific row objects escape.
- **Lazy-import third-party drivers.** Branch inside `get_connector`, not at module top.
- **Fail to a clear error.** A missing column or table should raise something the check engine can turn into a clean `ERROR` result.
