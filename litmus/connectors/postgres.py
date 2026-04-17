"""PostgreSQL connector."""

from __future__ import annotations

from datetime import datetime

from litmus.connectors.base import BaseConnector


class PostgresConnector(BaseConnector):
    """Connect to a PostgreSQL database via psycopg2."""

    def __init__(
        self,
        host: str,
        port: int,
        database: str,
        user: str,
        password: str,
        schema: str = "public",
    ):
        self._dsn = {
            "host": host,
            "port": port,
            "dbname": database,
            "user": user,
            "password": password,
        }
        self._schema = schema
        self._conn = None

    def connect(self) -> None:
        try:
            import psycopg2
            import psycopg2.extras  # noqa: F401  (side-effect import)
        except ImportError:
            raise ImportError(
                "psycopg2 is required for the PostgreSQL connector. "
                "Install it with: pip install 'litmus-data[postgres]'"
            )
        try:
            self._conn = psycopg2.connect(**self._dsn)
        except psycopg2.OperationalError as exc:
            # psycopg2's OperationalError stringifies to a multi-line traceback
            # fragment. Compress to one line and surface the knobs the user
            # actually controls so they don't have to read a stack trace to
            # figure out what's wrong.
            host = self._dsn.get("host")
            port = self._dsn.get("port")
            raise ConnectionError(
                f"Could not connect to Postgres at {host}:{port}. "
                "Check host/port/database in litmus.yml and that "
                "LITMUS_WAREHOUSE_USER / LITMUS_WAREHOUSE_PASSWORD are set. "
                f"(underlying error: {str(exc).strip().splitlines()[-1]})"
            ) from exc

    def _ensure_connected(self):
        if self._conn is None:
            self.connect()
        return self._conn

    def execute_query(self, sql: str) -> list[dict]:
        import psycopg2.extras

        conn = self._ensure_connected()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql)
            return [dict(row) for row in cur.fetchall()]

    def get_table_freshness(
        self, table: str, timestamp_column: str | None = None
    ) -> datetime | None:
        col = timestamp_column or "updated_at"
        qualified = f"{self._schema}.{table}" if self._schema else table
        rows = self.execute_query(f"SELECT MAX({col}) as max_ts FROM {qualified}")
        if rows and rows[0]["max_ts"] is not None:
            ts = rows[0]["max_ts"]
            return ts if isinstance(ts, datetime) else datetime.fromisoformat(str(ts))
        return None

    def get_row_count(self, table: str, conditions: list[str] | None = None) -> int:
        qualified = f"{self._schema}.{table}" if self._schema else table
        sql = f"SELECT COUNT(*) as cnt FROM {qualified}"
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        rows = self.execute_query(sql)
        return int(rows[0]["cnt"])

    def get_null_rate(self, table: str, column: str) -> float:
        qualified = f"{self._schema}.{table}" if self._schema else table
        rows = self.execute_query(
            f"SELECT COUNT(*) as total, "
            f"COUNT(CASE WHEN {column} IS NULL THEN 1 END) as nulls "
            f"FROM {qualified}"
        )
        total = rows[0]["total"]
        if total == 0:
            return 0.0
        return float(rows[0]["nulls"]) / float(total) * 100.0

    def get_column_sum(self, table: str, column: str) -> float | None:
        qualified = f"{self._schema}.{table}" if self._schema else table
        rows = self.execute_query(f"SELECT SUM({column}) as total FROM {qualified}")
        val = rows[0]["total"]
        return float(val) if val is not None else None

    def get_columns(self, table: str) -> list[str]:
        schema = self._schema or "public"
        rows = self.execute_query(
            "SELECT column_name FROM information_schema.columns "
            f"WHERE table_schema = '{schema}' AND table_name = '{table}' "
            "ORDER BY ordinal_position"
        )
        return [r["column_name"] for r in rows]

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
