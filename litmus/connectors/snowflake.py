"""Snowflake connector."""

from __future__ import annotations

from datetime import datetime

from litmus.connectors.base import BaseConnector


class SnowflakeConnector(BaseConnector):
    """Connect to a Snowflake warehouse."""

    def __init__(
        self,
        account: str,
        user: str,
        password: str,
        database: str,
        schema: str = "PUBLIC",
        warehouse: str | None = None,
        role: str | None = None,
    ):
        self._params = {
            "account": account,
            "user": user,
            "password": password,
            "database": database,
            "schema": schema,
        }
        if warehouse:
            self._params["warehouse"] = warehouse
        if role:
            self._params["role"] = role
        self._schema = schema
        self._conn = None

    def connect(self) -> None:
        try:
            import snowflake.connector
        except ImportError:
            raise ImportError(
                "snowflake-connector-python is required for the Snowflake connector. "
                "Install it with: pip install 'litmus-data[snowflake]'"
            )
        self._conn = snowflake.connector.connect(**self._params)

    def _ensure_connected(self):
        if self._conn is None:
            self.connect()
        return self._conn

    def execute_query(self, sql: str) -> list[dict]:
        conn = self._ensure_connected()
        cur = conn.cursor()
        try:
            cur.execute(sql)
            columns = [desc[0] for desc in cur.description]
            return [dict(zip(columns, row)) for row in cur.fetchall()]
        finally:
            cur.close()

    def get_table_freshness(
        self, table: str, timestamp_column: str | None = None
    ) -> datetime | None:
        col = timestamp_column or "UPDATED_AT"
        qualified = f"{self._schema}.{table}" if self._schema else table
        rows = self.execute_query(f"SELECT MAX({col}) as MAX_TS FROM {qualified}")
        if rows and rows[0]["MAX_TS"] is not None:
            return rows[0]["MAX_TS"]
        return None

    def get_row_count(self, table: str, conditions: list[str] | None = None) -> int:
        qualified = f"{self._schema}.{table}" if self._schema else table
        sql = f"SELECT COUNT(*) as CNT FROM {qualified}"
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        rows = self.execute_query(sql)
        return int(rows[0]["CNT"])

    def get_null_rate(self, table: str, column: str) -> float:
        qualified = f"{self._schema}.{table}" if self._schema else table
        rows = self.execute_query(
            f"SELECT COUNT(*) as TOTAL, "
            f"COUNT(CASE WHEN {column} IS NULL THEN 1 END) as NULLS "
            f"FROM {qualified}"
        )
        total = rows[0]["TOTAL"]
        if total == 0:
            return 0.0
        return (rows[0]["NULLS"] / total) * 100.0

    def get_column_sum(self, table: str, column: str) -> float | None:
        qualified = f"{self._schema}.{table}" if self._schema else table
        rows = self.execute_query(f"SELECT SUM({column}) as TOTAL FROM {qualified}")
        val = rows[0]["TOTAL"]
        return float(val) if val is not None else None

    def get_columns(self, table: str) -> list[str]:
        schema = (self._schema or "PUBLIC").upper()
        rows = self.execute_query(
            "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
            f"WHERE TABLE_SCHEMA = '{schema}' AND TABLE_NAME = '{table.upper()}' "
            "ORDER BY ORDINAL_POSITION"
        )
        return [r["COLUMN_NAME"] for r in rows]

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
