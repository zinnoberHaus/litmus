"""SQLite-backed history store for metric values across runs.

Enables ``ChangeRule`` checks (``Value must not change more than N% month over month``)
by recording each run's metric value + row count and letting later runs compare
against prior observations.

Schema (auto-migrated; older DBs gain the newer columns via ``ALTER TABLE``):

.. code-block:: sql

    CREATE TABLE history (
        id                 INTEGER PRIMARY KEY AUTOINCREMENT,
        metric_name        TEXT    NOT NULL,
        value_sum          REAL,             -- SUM of value column; NULL if unavailable
        row_count          INTEGER,          -- COUNT(*) of the primary source
        recorded_at        TEXT    NOT NULL, -- ISO-8601 UTC
        run_id             TEXT,             -- optional run identifier
        commit_sha         TEXT,             -- optional VCS commit
        schema_fingerprint TEXT,             -- sorted columns, comma-joined
        column_means_json  TEXT              -- JSON {col: AVG(col)}
    );
    CREATE INDEX idx_history_metric_time ON history (metric_name, recorded_at);
"""

from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

DEFAULT_HISTORY_PATH = Path(
    os.environ.get("LITMUS_HISTORY_DB", "~/.litmus/history.db")
).expanduser()

_PERIOD_DAYS = {
    "day": 1,
    "week": 7,
    "month": 30,
    "quarter": 90,
    "year": 365,
}


@dataclass
class HistoryRecord:
    metric_name: str
    value_sum: float | None
    row_count: int | None
    recorded_at: datetime
    run_id: str | None = None
    commit_sha: str | None = None
    schema_fingerprint: str | None = None
    column_means: dict[str, float | None] = field(default_factory=dict)


class HistoryStore:
    """SQLite-backed store for metric value history.

    Typical use::

        store = HistoryStore()  # defaults to ~/.litmus/history.db
        store.record("Monthly Revenue", value_sum=3_250_000.0, row_count=9)
        prior = store.previous_value("Monthly Revenue", period="month")
    """

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path is not None else DEFAULT_HISTORY_PATH
        self._conn: sqlite3.Connection | None = None

    # ------------------------------------------------------------------ lifecycle
    def connect(self) -> None:
        if self._conn is not None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path))
        self._conn.row_factory = sqlite3.Row
        self._migrate()

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> HistoryStore:
        self.connect()
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def _migrate(self) -> None:
        assert self._conn is not None
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS history (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                metric_name TEXT    NOT NULL,
                value_sum   REAL,
                row_count   INTEGER,
                recorded_at TEXT    NOT NULL,
                run_id      TEXT,
                commit_sha  TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_history_metric_time
                ON history (metric_name, recorded_at);
            """
        )
        # Add columns introduced after the v1 schema. ``ALTER TABLE ADD COLUMN``
        # errors if the column already exists, so inspect pragma first.
        existing = {
            row["name"] for row in self._conn.execute("PRAGMA table_info(history)").fetchall()
        }
        if "schema_fingerprint" not in existing:
            self._conn.execute("ALTER TABLE history ADD COLUMN schema_fingerprint TEXT")
        if "column_means_json" not in existing:
            self._conn.execute("ALTER TABLE history ADD COLUMN column_means_json TEXT")
        self._conn.commit()

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
        """Append a history row for ``metric_name``.

        ``column_means`` is a dict mapping column name → AVG value. Stored as
        JSON so one row can carry means for any number of columns — this is what
        ``distribution_shift`` rules consult on the next run.
        """
        if self._conn is None:
            self.connect()
        assert self._conn is not None
        ts = (recorded_at or datetime.now(timezone.utc)).isoformat()
        means_json = json.dumps(column_means) if column_means else None
        self._conn.execute(
            "INSERT INTO history (metric_name, value_sum, row_count, recorded_at, run_id, "
            "commit_sha, schema_fingerprint, column_means_json)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (metric_name, value_sum, row_count, ts, run_id, commit_sha,
             schema_fingerprint, means_json),
        )
        self._conn.commit()

    def purge(self, metric_name: str | None = None) -> int:
        """Remove history rows. Returns the number of deleted rows."""
        if self._conn is None:
            self.connect()
        assert self._conn is not None
        if metric_name is None:
            cur = self._conn.execute("DELETE FROM history")
        else:
            cur = self._conn.execute("DELETE FROM history WHERE metric_name = ?", (metric_name,))
        self._conn.commit()
        return cur.rowcount

    # ------------------------------------------------------------------ reads
    def previous_record(
        self,
        metric_name: str,
        period: str,
        *,
        now: datetime | None = None,
    ) -> HistoryRecord | None:
        """Return the most recent record at least ``period`` old, or ``None``.

        ``period`` is one of ``day | week | month | quarter | year`` and is interpreted
        as "the newest row recorded before NOW minus that many days". Ties go to
        the latest row.
        """
        if self._conn is None:
            self.connect()
        assert self._conn is not None

        days = _PERIOD_DAYS.get(period)
        if days is None:
            raise ValueError(
                f"Unknown period: {period!r}. Expected one of {sorted(_PERIOD_DAYS)}."
            )
        cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=days)

        row = self._conn.execute(
            "SELECT metric_name, value_sum, row_count, recorded_at, run_id, commit_sha,"
            " schema_fingerprint, column_means_json"
            " FROM history"
            " WHERE metric_name = ? AND recorded_at <= ?"
            " ORDER BY recorded_at DESC LIMIT 1",
            (metric_name, cutoff.isoformat()),
        ).fetchone()
        if row is None:
            return None
        return HistoryRecord(
            metric_name=row["metric_name"],
            value_sum=row["value_sum"],
            row_count=row["row_count"],
            recorded_at=datetime.fromisoformat(row["recorded_at"]),
            run_id=row["run_id"],
            commit_sha=row["commit_sha"],
            schema_fingerprint=row["schema_fingerprint"],
            column_means=json.loads(row["column_means_json"]) if row["column_means_json"] else {},
        )

    def last_record(self, metric_name: str) -> HistoryRecord | None:
        """Return the most recent record for a metric regardless of age (for diagnostics)."""
        if self._conn is None:
            self.connect()
        assert self._conn is not None
        row = self._conn.execute(
            "SELECT metric_name, value_sum, row_count, recorded_at, run_id, commit_sha,"
            " schema_fingerprint, column_means_json"
            " FROM history WHERE metric_name = ?"
            " ORDER BY recorded_at DESC LIMIT 1",
            (metric_name,),
        ).fetchone()
        if row is None:
            return None
        return HistoryRecord(
            metric_name=row["metric_name"],
            value_sum=row["value_sum"],
            row_count=row["row_count"],
            recorded_at=datetime.fromisoformat(row["recorded_at"]),
            run_id=row["run_id"],
            commit_sha=row["commit_sha"],
            schema_fingerprint=row["schema_fingerprint"],
            column_means=json.loads(row["column_means_json"]) if row["column_means_json"] else {},
        )

    def all_records(self, metric_name: str) -> list[HistoryRecord]:
        """Return all records for a metric, oldest first. Used by tests + diagnostics."""
        if self._conn is None:
            self.connect()
        assert self._conn is not None
        rows = self._conn.execute(
            "SELECT metric_name, value_sum, row_count, recorded_at, run_id, commit_sha,"
            " schema_fingerprint, column_means_json"
            " FROM history WHERE metric_name = ? ORDER BY recorded_at ASC",
            (metric_name,),
        ).fetchall()
        return [
            HistoryRecord(
                metric_name=r["metric_name"],
                value_sum=r["value_sum"],
                row_count=r["row_count"],
                recorded_at=datetime.fromisoformat(r["recorded_at"]),
                run_id=r["run_id"],
                commit_sha=r["commit_sha"],
                schema_fingerprint=r["schema_fingerprint"],
                column_means=json.loads(r["column_means_json"]) if r["column_means_json"] else {},
            )
            for r in rows
        ]
