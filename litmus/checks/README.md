# `litmus/checks/` — Trust-check engine

Runs the `TrustSpec` in a `MetricSpec` against a warehouse via `BaseConnector` and produces `CheckResult` verdicts.

## Flow

```
MetricSpec (with TrustSpec)   BaseConnector (warehouse)
           │                            │
           └──────────┬─────────────────┘
                      ▼
              run_checks() in runner.py
                      │
        ┌─────────────┼─────────────┬──────────────┐
        ▼             ▼             ▼              ▼
  freshness.py   null_rate.py   volume.py      range.py
        │             │             │              │
        └─────────────┴──── CheckResult ───────────┘
                              │
                              ▼
                         CheckSuite
```

## Files

| File | Role |
|------|------|
| `runner.py` | `CheckStatus`, `CheckResult`, `CheckSuite`, `run_checks()`. Dispatches to per-rule modules. |
| `freshness.py` | `Freshness must be less than N hours`. Warns at 90% of limit. |
| `null_rate.py` | `Null rate on <col> must be less than N%`. |
| `volume.py` | `Row count must not drop more than N% day over day`. |
| `range.py` | `Value must be between <min> and <max>` — runs against the primary source + default value column. |
| `change.py` | `Value must not change more than N% period over period` — compares current `SUM(value_column)` against the history store. |
| `duplicate_rate.py` | `Duplicate rate on <col> must be less than N%`. Stateless — uses `COUNT(*) - COUNT(DISTINCT col)`. |
| `schema_drift.py` | `Schema must not drift` — records the current column list into the history store each run; FAILED if the set changes. Case- and order-insensitive. |
| `distribution_shift.py` | `Mean of <col> must not change more than N% <period> over <period>` — stores per-column means in history; compares current `AVG(col)` against the prior snapshot. |
| `history.py` | SQLite-backed store of past metric values. Default path `~/.litmus/history.db`, override via `LITMUS_HISTORY_DB` env var. |
| `custom.py` | Extension point for user-defined checks. |

## History store

`HistoryStore` records one row per (metric × run) with columns `metric_name, value_sum, row_count, recorded_at, run_id, commit_sha, schema_fingerprint, column_means_json`. Created automatically on first write; `ALTER TABLE ADD COLUMN` migrations run on every connect so older DBs upgrade in place.

- `schema_fingerprint` — sorted, case-folded, comma-joined column list. Consulted by `schema_drift.py`.
- `column_means_json` — JSON `{column: AVG(column)}`. Consulted by `distribution_shift.py` to compare current mean against history, keyed by column.

- **Writes:** every successful `run_checks()` call appends a row (unless the caller passed `history=None` or the CLI user passed `--no-history`).
- **Reads:** `change.py` asks the store for the most recent record at least `rule.period` old (day/week/month/quarter/year) and compares current value to it.
- **Location:** defaults to `~/.litmus/history.db`. Overrides: `--history-db <path>` on the CLI or `LITMUS_HISTORY_DB` env var.
- **Purging:** `HistoryStore.purge(metric_name=None)` wipes all rows (or a specific metric). There's no CLI for this yet — flagged as a small advocate follow-up.
- **CI behavior:** when `GITHUB_RUN_ID` / `GITHUB_SHA` are in the environment, the runner records them alongside the row. Makes "which PR regressed the metric" trivial to query.

## Status semantics (stable contract)

| Status | Meaning | Trust score weight |
|--------|---------|--------------------|
| `PASSED` | Value within limit | 1.0 |
| `WARNING` | Within 90% of the limit (`WARNING_THRESHOLD`) | 0.5 |
| `FAILED` | Value violates the limit | 0.0 |
| `ERROR` | Check couldn't run (connector error, missing column, empty table) | 0.0 |

**ERROR is not FAILED.** Users need to know the difference between "your data is bad" and "our check is broken."

CLI exit-code contract (`cli.py::check`): exit 1 iff any suite has `failed > 0 or errors > 0`. Warnings alone don't fail the run.

## Runner defaults (known debt)

- Primary table = `spec.sources[0]`. Multi-table metrics silently ignore the rest for volume/null/range.
- `timestamp_column` defaults to `"updated_at"`, `value_column` defaults to `"amount"`. The proper fix is making these explicit fields on `MetricSpec` — coordinate with the **litmus-architect** agent before changing.
- `change_rules` are live as of 2026-04 (SQLite history store in `history.py`). They compare `SUM(value_column)` on the primary source; this is a proxy, not the actual metric math (that lives in user SQL). Acceptable for most value-drift detection; revisit when the generator in `litmus/generators/sql_generator.py` is complete enough to run the real calc.

## Adding a new check type

Owned by the **litmus-inspector** agent. Only start after the **litmus-architect** has landed the DSL change:

1. Create `checks/<rule>.py` exporting `check_<rule>(connector, table, rule, …) -> CheckResult`.
2. Add a branch in `run_checks()`.
3. If the check needs new warehouse capability, request a method on `BaseConnector` from the **litmus-connector** agent — do not query the connector's internals directly.
4. Return a `CheckResult` with both `actual_value` and `threshold` populated.
5. Test with `test_db` fixture from `tests/conftest.py`. Prefer real SQL over mocks.

## Design rules

- No warehouse-specific SQL here. Everything goes through `BaseConnector`.
- Always populate `actual_value` and `threshold` — reporters rely on them.
- Fail loud: empty table, missing column, NULL timestamp → `ERROR`, not silent `PASSED`.
- `message` strings are human-readable — reporters pass them straight through.
