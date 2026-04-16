"""SQLite connector — zero-install adoption for local app DBs, Datasette files, and fixtures."""

from __future__ import annotations

import sqlite3
from datetime import datetime

from litmus.connectors.base import BaseConnector


class SQLiteConnector(BaseConnector):
    """Connect to a SQLite file or in-memory database.

    SQLite is stdlib in Python 3, so this connector has no optional extras.
    """

    def __init__(self, database: str = ":memory:", connection: sqlite3.Connection | None = None):
        self._database = database
        self._conn = connection

    def connect(self) -> None:
        if self._conn is None:
            self._conn = sqlite3.connect(self._database)
            self._conn.row_factory = sqlite3.Row

    def _ensure_connected(self) -> sqlite3.Connection:
        if self._conn is None:
            self.connect()
        assert self._conn is not None
        return self._conn

    def execute_query(self, sql: str) -> list[dict]:
        conn = self._ensure_connected()
        cur = conn.execute(sql)
        rows = cur.fetchall()
        return [dict(row) for row in rows]

    def get_table_freshness(
        self, table: str, timestamp_column: str | None = None
    ) -> datetime | None:
        col = timestamp_column or "updated_at"
        rows = self.execute_query(f"SELECT MAX({col}) as max_ts FROM {table}")
        if not rows or rows[0]["max_ts"] is None:
            return None
        val = rows[0]["max_ts"]
        if isinstance(val, datetime):
            return val
        try:
            return datetime.fromisoformat(str(val))
        except ValueError:
            return None

    def get_row_count(self, table: str, conditions: list[str] | None = None) -> int:
        sql = f"SELECT COUNT(*) as cnt FROM {table}"
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        rows = self.execute_query(sql)
        return int(rows[0]["cnt"])

    def get_null_rate(self, table: str, column: str) -> float:
        rows = self.execute_query(
            f"SELECT COUNT(*) as total, "
            f"SUM(CASE WHEN {column} IS NULL THEN 1 ELSE 0 END) as nulls "
            f"FROM {table}"
        )
        total = rows[0]["total"]
        if total == 0:
            return 0.0
        nulls = rows[0]["nulls"] or 0
        return (nulls / total) * 100.0

    def get_column_sum(self, table: str, column: str) -> float | None:
        rows = self.execute_query(f"SELECT SUM({column}) as total FROM {table}")
        val = rows[0]["total"]
        return float(val) if val is not None else None

    def get_columns(self, table: str) -> list[str]:
        # PRAGMA table_info works on any SQLite version; safer than relying on
        # a SELECT * LIMIT 0 round-trip.
        conn = self._ensure_connected()
        cur = conn.execute(f"PRAGMA table_info({table})")
        return [row["name"] for row in cur.fetchall()]

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
