"""BigQuery connector (stub — not included in v0.1 scope)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from litmus.connectors.base import BaseConnector


class BigQueryConnector(BaseConnector):
    """Connect to Google BigQuery.

    Not implemented in v0.1. Install with: pip install 'litmus-data[bigquery]'
    """

    def __init__(self, project: str, dataset: str, credentials_path: str | None = None):
        self._project = project
        self._dataset = dataset
        self._credentials_path = credentials_path
        self._client: Any = None

    def connect(self) -> None:
        try:
            from google.cloud import bigquery
        except ImportError:
            raise ImportError(
                "google-cloud-bigquery is required for the BigQuery connector. "
                "Install it with: pip install 'litmus-data[bigquery]'"
            )
        self._client = bigquery.Client(project=self._project)

    def execute_query(self, sql: str) -> list[dict]:
        if self._client is None:
            self.connect()
        assert self._client is not None
        query_job = self._client.query(sql)
        return [dict(row) for row in query_job.result()]

    def get_table_freshness(
        self, table: str, timestamp_column: str | None = None
    ) -> datetime | None:
        col = timestamp_column or "updated_at"
        qualified = f"`{self._project}.{self._dataset}.{table}`"
        rows = self.execute_query(f"SELECT MAX({col}) as max_ts FROM {qualified}")
        if rows and rows[0]["max_ts"] is not None:
            ts = rows[0]["max_ts"]
            return ts if isinstance(ts, datetime) else datetime.fromisoformat(str(ts))
        return None

    def get_row_count(self, table: str, conditions: list[str] | None = None) -> int:
        qualified = f"`{self._project}.{self._dataset}.{table}`"
        sql = f"SELECT COUNT(*) as cnt FROM {qualified}"
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        rows = self.execute_query(sql)
        return int(rows[0]["cnt"])

    def get_null_rate(self, table: str, column: str) -> float:
        qualified = f"`{self._project}.{self._dataset}.{table}`"
        rows = self.execute_query(
            f"SELECT COUNT(*) as total, "
            f"COUNTIF({column} IS NULL) as nulls "
            f"FROM {qualified}"
        )
        total = rows[0]["total"]
        if total == 0:
            return 0.0
        return float(rows[0]["nulls"]) / float(total) * 100.0

    def get_column_sum(self, table: str, column: str) -> float | None:
        qualified = f"`{self._project}.{self._dataset}.{table}`"
        rows = self.execute_query(f"SELECT SUM({column}) as total FROM {qualified}")
        val = rows[0]["total"]
        return float(val) if val is not None else None

    def get_columns(self, table: str) -> list[str]:
        rows = self.execute_query(
            f"SELECT column_name FROM `{self._project}.{self._dataset}`."
            f"INFORMATION_SCHEMA.COLUMNS "
            f"WHERE table_name = '{table}' ORDER BY ordinal_position"
        )
        return [r["column_name"] for r in rows]

    def close(self) -> None:
        self._client = None
