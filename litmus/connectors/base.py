"""Abstract base class for all data warehouse connectors."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime


class BaseConnector(ABC):
    """Interface that every warehouse connector must implement."""

    @abstractmethod
    def connect(self) -> None:
        """Establish a connection to the warehouse."""

    @abstractmethod
    def execute_query(self, sql: str) -> list[dict]:
        """Execute a SQL query and return rows as dicts."""

    @abstractmethod
    def get_table_freshness(
        self, table: str, timestamp_column: str | None = None
    ) -> datetime | None:
        """Return the most recent timestamp in the table, or None if empty."""

    @abstractmethod
    def get_row_count(self, table: str, conditions: list[str] | None = None) -> int:
        """Return the number of rows, optionally filtered by SQL conditions."""

    @abstractmethod
    def get_null_rate(self, table: str, column: str) -> float:
        """Return the null rate (0.0–100.0) for a column."""

    @abstractmethod
    def get_column_sum(self, table: str, column: str) -> float | None:
        """Return the SUM of a numeric column."""

    def get_column_mean(self, table: str, column: str) -> float | None:
        """Return the AVG of a numeric column. Default uses AVG(); override if needed."""
        rows = self.execute_query(f"SELECT AVG({column}) AS avg_val FROM {table}")
        val = rows[0].get("avg_val") if rows else None
        if val is None:
            # Some drivers uppercase result keys (Snowflake).
            val = rows[0].get("AVG_VAL") if rows else None
        return float(val) if val is not None else None

    def get_duplicate_rate(self, table: str, column: str) -> float:
        """Return the percentage of rows whose value in ``column`` is non-unique.

        ``dupes = total - COUNT(DISTINCT column)``.  Returns 0.0 if the table is empty.
        Default implementation uses plain SQL — override if your warehouse has a
        faster path.
        """
        rows = self.execute_query(
            f"SELECT COUNT(*) AS total, COUNT(DISTINCT {column}) AS distinct_count "
            f"FROM {table}"
        )
        if not rows:
            return 0.0
        row = rows[0]
        total = row.get("total") or row.get("TOTAL") or 0
        distinct = row.get("distinct_count") or row.get("DISTINCT_COUNT") or 0
        if total == 0:
            return 0.0
        dupes = total - distinct
        return (dupes / total) * 100.0

    def get_columns(self, table: str) -> list[str]:
        """Return the column names of ``table``. Default implementation uses
        ``SELECT * ... LIMIT 0`` and reads the result keys; override for better
        fidelity (e.g. SQLite ``PRAGMA table_info``)."""
        rows = self.execute_query(f"SELECT * FROM {table} LIMIT 0")
        # Most drivers return an empty rows list for LIMIT 0 but still surface the
        # column names via the cursor description. If the fallback leaves us
        # empty-handed we let the connector override.
        if rows:
            return list(rows[0].keys())
        return []

    # ------------------------------------------------------------------ history
    def create_history_tables(
        self,
        schema: str | None = None,
        history_table: str = "litmus_history",
    ) -> None:
        """Idempotently create the warehouse history table used by
        :class:`litmus.checks.history.WarehouseHistoryStore`.

        Dialect notes:
          * DuckDB, Postgres, SQLite — ``CREATE TABLE IF NOT EXISTS`` works natively.
          * Snowflake — same syntax; VARCHAR without a length defaults to 16MB.
          * BigQuery — standard SQL supports ``IF NOT EXISTS``. ``VARCHAR``
            aliases to ``STRING``.

        We deliberately use only ANSI-ish types (VARCHAR, DOUBLE/FLOAT, BIGINT)
        that survive every adapter without per-dialect overrides. Connectors
        override this method when their adapter requires tweaks (e.g. BigQuery
        type names, schema qualification).
        """
        qualified = f"{schema}.{history_table}" if schema else history_table
        # ``DOUBLE PRECISION`` is the ANSI form: Postgres requires it, DuckDB
        # + Snowflake accept it. ``VARCHAR(N)`` without a length works in
        # Snowflake but not Postgres, so we pin lengths.
        ddl = (
            f"CREATE TABLE IF NOT EXISTS {qualified} (\n"
            "    metric_name        VARCHAR(500) NOT NULL,\n"
            "    value_sum          DOUBLE PRECISION,\n"
            "    row_count          BIGINT,\n"
            "    recorded_at        VARCHAR(64) NOT NULL,\n"
            "    run_id             VARCHAR(128),\n"
            "    commit_sha         VARCHAR(128),\n"
            "    schema_fingerprint VARCHAR(4000),\n"
            "    column_means_json  VARCHAR(16000)\n"
            ")"
        )
        self.execute_query(ddl)

    @abstractmethod
    def close(self) -> None:
        """Close the connection."""

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *exc):
        self.close()
