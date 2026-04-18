"""Warehouse-backed history store — the shared-team backend for stateful checks.

Mirrors :class:`litmus.checks.history.HistoryStore` one-for-one (same method
names, same return types, same semantics) but persists to warehouse tables
via the existing :class:`litmus.connectors.base.BaseConnector` layer.

Why a second backend instead of swapping SQLite for warehouse everywhere?
Solo engineers shouldn't need a warehouse round-trip to run ``litmus check``
on a laptop — that's what the SQLite store is for. Teams with a shared dbt
project already have a warehouse and don't want to ship history files around
on a USB stick. Users pick via ``litmus check --backend {sqlite,warehouse,auto}``.

Schema — the canonical v0.3 warehouse tables — is defined in
``litmus/connectors/base.BaseConnector.create_history_tables``. We deliberately
use a narrow "runs" table here (one row per metric per run) rather than the
fuller ``litmus_runs`` + ``litmus_check_results`` pair the dbt package
materialises: check-level rows belong to the dbt side of the fence where
users inspect them in their BI tool, while the Python runner only needs
last-N-runs aggregates to answer change/drift questions.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from litmus.connectors.base import BaseConnector

from litmus.checks.history import _PERIOD_DAYS, HistoryRecord

DEFAULT_HISTORY_TABLE = "litmus_history"


def _sql_quote(value: str | None) -> str:
    """SQL-literal quote a string (or NULL) for inline DDL/DML.

    The history store never interpolates user data — only runner-generated
    values like metric name, commit SHA, and JSON blobs — but we still
    escape single quotes to keep a stray apostrophe in a metric name from
    derailing an INSERT. Parameterised queries aren't uniformly available
    across our connectors (BigQuery needs a different parameter style),
    so we centralise quoting here instead.
    """
    if value is None:
        return "NULL"
    escaped = value.replace("'", "''")
    return f"'{escaped}'"


def _sql_num(value: float | int | None) -> str:
    if value is None:
        return "NULL"
    return str(value)


class WarehouseHistoryStore:
    """Persist run history to warehouse tables through a :class:`BaseConnector`.

    Typical use::

        from litmus.connectors.duckdb import DuckDBConnector
        from litmus.checks.history import WarehouseHistoryStore

        connector = DuckDBConnector(database="warehouse.duckdb")
        connector.connect()
        store = WarehouseHistoryStore(connector=connector)
        store.connect()  # creates litmus_history table if missing
        store.record("Monthly Revenue", value_sum=3_250_000.0, row_count=9)
        prior = store.previous_record("Monthly Revenue", period="month")

    The store does NOT take ownership of the connector's lifecycle — callers
    open and close the connector themselves. ``store.connect()`` only runs
    the DDL that ensures the history table exists.
    """

    def __init__(
        self,
        connector: BaseConnector,
        *,
        schema: str | None = None,
        table: str = DEFAULT_HISTORY_TABLE,
    ):
        self._connector = connector
        self._schema = schema
        self._table = table
        self._ready = False

    # ------------------------------------------------------------------ lifecycle
    @property
    def qualified_table(self) -> str:
        if self._schema:
            return f"{self._schema}.{self._table}"
        return self._table

    def connect(self) -> None:
        """Ensure the warehouse table exists. Idempotent."""
        if self._ready:
            return
        # The connector's ``create_history_tables`` knows the right DDL dialect.
        self._connector.create_history_tables(
            schema=self._schema, history_table=self._table
        )
        self._ready = True

    def close(self) -> None:
        """No-op — the caller owns the connector lifecycle."""
        self._ready = False

    def __enter__(self) -> WarehouseHistoryStore:
        self.connect()
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ------------------------------------------------------------------ writes
    def record(
        self,
        metric_name: str,
        value_sum: float | None,
        row_count: int | None,
        run_id: str | None = None,
        commit_sha: str | None = None,
        recorded_at: datetime | None = None,
        schema_fingerprint: str | None = None,
        column_means: dict[str, float | None] | None = None,
    ) -> None:
        if not self._ready:
            self.connect()
        ts = (recorded_at or datetime.now(timezone.utc)).isoformat()
        means_json = json.dumps(column_means) if column_means else None
        sql = (
            f"INSERT INTO {self.qualified_table} "
            "(metric_name, value_sum, row_count, recorded_at, run_id, commit_sha, "
            "schema_fingerprint, column_means_json) VALUES ("
            f"{_sql_quote(metric_name)}, "
            f"{_sql_num(value_sum)}, "
            f"{_sql_num(row_count)}, "
            f"{_sql_quote(ts)}, "
            f"{_sql_quote(run_id)}, "
            f"{_sql_quote(commit_sha)}, "
            f"{_sql_quote(schema_fingerprint)}, "
            f"{_sql_quote(means_json)})"
        )
        self._connector.execute_query(sql)

    def purge(self, metric_name: str | None = None) -> int:
        """Remove history rows. Returns the number of deleted rows.

        Unlike the SQLite store we can't rely on ``cursor.rowcount`` across
        dialects, so we COUNT(*) first, then DELETE.
        """
        if not self._ready:
            self.connect()
        if metric_name is None:
            rows = self._connector.execute_query(
                f"SELECT COUNT(*) AS cnt FROM {self.qualified_table}"
            )
            self._connector.execute_query(f"DELETE FROM {self.qualified_table}")
        else:
            rows = self._connector.execute_query(
                f"SELECT COUNT(*) AS cnt FROM {self.qualified_table} "
                f"WHERE metric_name = {_sql_quote(metric_name)}"
            )
            self._connector.execute_query(
                f"DELETE FROM {self.qualified_table} "
                f"WHERE metric_name = {_sql_quote(metric_name)}"
            )
        if not rows:
            return 0
        row = rows[0]
        cnt = row.get("cnt") or row.get("CNT") or 0
        return int(cnt)

    # ------------------------------------------------------------------ reads
    def previous_record(
        self,
        metric_name: str,
        period: str,
        *,
        now: datetime | None = None,
    ) -> HistoryRecord | None:
        if not self._ready:
            self.connect()
        days = _PERIOD_DAYS.get(period)
        if days is None:
            raise ValueError(
                f"Unknown period: {period!r}. Expected one of {sorted(_PERIOD_DAYS)}."
            )
        cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=days)

        rows = self._connector.execute_query(
            "SELECT metric_name, value_sum, row_count, recorded_at, run_id, commit_sha, "
            "schema_fingerprint, column_means_json "
            f"FROM {self.qualified_table} "
            f"WHERE metric_name = {_sql_quote(metric_name)} "
            f"AND recorded_at <= {_sql_quote(cutoff.isoformat())} "
            "ORDER BY recorded_at DESC LIMIT 1"
        )
        return _row_to_record(rows[0]) if rows else None

    def last_record(self, metric_name: str) -> HistoryRecord | None:
        if not self._ready:
            self.connect()
        rows = self._connector.execute_query(
            "SELECT metric_name, value_sum, row_count, recorded_at, run_id, commit_sha, "
            "schema_fingerprint, column_means_json "
            f"FROM {self.qualified_table} "
            f"WHERE metric_name = {_sql_quote(metric_name)} "
            "ORDER BY recorded_at DESC LIMIT 1"
        )
        return _row_to_record(rows[0]) if rows else None

    def all_records(self, metric_name: str) -> list[HistoryRecord]:
        if not self._ready:
            self.connect()
        rows = self._connector.execute_query(
            "SELECT metric_name, value_sum, row_count, recorded_at, run_id, commit_sha, "
            "schema_fingerprint, column_means_json "
            f"FROM {self.qualified_table} "
            f"WHERE metric_name = {_sql_quote(metric_name)} "
            "ORDER BY recorded_at ASC"
        )
        return [_row_to_record(r) for r in rows]


def _get(row: dict, key: str):
    """Warehouse drivers disagree on result-key casing (Snowflake upper-cases).

    Look up either case rather than branching per dialect.
    """
    if key in row:
        return row[key]
    return row.get(key.upper())


def _row_to_record(row: dict) -> HistoryRecord:
    raw_ts = _get(row, "recorded_at")
    if isinstance(raw_ts, datetime):
        recorded_at = raw_ts
    else:
        recorded_at = datetime.fromisoformat(str(raw_ts))
    means_raw = _get(row, "column_means_json")
    value_sum = _get(row, "value_sum")
    row_count = _get(row, "row_count")
    return HistoryRecord(
        metric_name=_get(row, "metric_name"),
        value_sum=float(value_sum) if value_sum is not None else None,
        row_count=int(row_count) if row_count is not None else None,
        recorded_at=recorded_at,
        run_id=_get(row, "run_id"),
        commit_sha=_get(row, "commit_sha"),
        schema_fingerprint=_get(row, "schema_fingerprint"),
        column_means=json.loads(means_raw) if means_raw else {},
    )
