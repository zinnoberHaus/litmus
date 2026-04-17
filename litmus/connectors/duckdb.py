"""DuckDB connector — zero-config local database for testing and demos."""

from __future__ import annotations

from datetime import datetime

import duckdb

from litmus.connectors.base import BaseConnector


class DuckDBConnector(BaseConnector):
    """Connect to a DuckDB database (file or in-memory)."""

    def __init__(
        self,
        database: str = ":memory:",
        connection: duckdb.DuckDBPyConnection | None = None,
    ):
        self._database = database
        self._conn = connection

    def connect(self) -> None:
        if self._conn is None:
            self._conn = duckdb.connect(self._database)

    def _ensure_connected(self) -> duckdb.DuckDBPyConnection:
        if self._conn is None:
            self.connect()
        assert self._conn is not None
        return self._conn

    def execute_query(self, sql: str) -> list[dict]:
        conn = self._ensure_connected()
        result = conn.execute(sql)
        columns = [desc[0] for desc in result.description]
        return [dict(zip(columns, row)) for row in result.fetchall()]

    def get_table_freshness(
        self, table: str, timestamp_column: str | None = None
    ) -> datetime | None:
        col = timestamp_column or "updated_at"
        rows = self.execute_query(f"SELECT MAX({col}) as max_ts FROM {table}")
        if rows and rows[0]["max_ts"] is not None:
            val = rows[0]["max_ts"]
            if isinstance(val, datetime):
                return val
            return datetime.fromisoformat(str(val))
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
            f"COUNT(CASE WHEN {column} IS NULL THEN 1 END) as nulls "
            f"FROM {table}"
        )
        total = rows[0]["total"]
        if total == 0:
            return 0.0
        return float(rows[0]["nulls"]) / float(total) * 100.0

    def get_column_sum(self, table: str, column: str) -> float | None:
        rows = self.execute_query(f"SELECT SUM({column}) as total FROM {table}")
        val = rows[0]["total"]
        return float(val) if val is not None else None

    def get_columns(self, table: str) -> list[str]:
        conn = self._ensure_connected()
        result = conn.execute(f"SELECT * FROM {table} LIMIT 0")
        return [desc[0] for desc in result.description]

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
