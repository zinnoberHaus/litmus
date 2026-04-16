"""Tests for the SQLite connector."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta

import pytest

from litmus.connectors.sqlite import SQLiteConnector


@pytest.fixture()
def sqlite_db(tmp_path):
    """Create an on-disk SQLite DB with an orders table for connector tests."""
    db_path = tmp_path / "orders.sqlite"
    conn = sqlite3.connect(str(db_path))
    now = datetime.utcnow().replace(microsecond=0)
    conn.executescript(
        f"""
        CREATE TABLE orders (
            order_id   INTEGER PRIMARY KEY,
            amount     REAL,
            status     TEXT NOT NULL,
            order_date TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        INSERT INTO orders VALUES
            (1, 100.00, 'completed', '2026-04-01', '{now.isoformat()}'),
            (2, 250.50, 'completed', '2026-04-02', '{(now - timedelta(hours=1)).isoformat()}'),
            (3, NULL,   'pending',   '2026-04-03', '{(now - timedelta(hours=2)).isoformat()}'),
            (4, 75.25,  'completed', '2026-04-04', '{(now - timedelta(hours=3)).isoformat()}');
        """
    )
    conn.commit()
    conn.close()
    yield db_path


def test_execute_query(sqlite_db):
    connector = SQLiteConnector(database=str(sqlite_db))
    connector.connect()
    try:
        rows = connector.execute_query("SELECT COUNT(*) as cnt FROM orders")
        assert rows == [{"cnt": 4}]
    finally:
        connector.close()


def test_row_count_with_conditions(sqlite_db):
    connector = SQLiteConnector(database=str(sqlite_db))
    with connector:
        total = connector.get_row_count("orders")
        completed = connector.get_row_count("orders", ["status = 'completed'"])
        assert total == 4
        assert completed == 3


def test_null_rate(sqlite_db):
    connector = SQLiteConnector(database=str(sqlite_db))
    with connector:
        rate = connector.get_null_rate("orders", "amount")
        # 1 null out of 4 = 25%
        assert rate == pytest.approx(25.0)


def test_null_rate_empty_table(tmp_path):
    db_path = tmp_path / "empty.sqlite"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE empty (col INTEGER)")
    conn.commit()
    conn.close()

    connector = SQLiteConnector(database=str(db_path))
    with connector:
        assert connector.get_null_rate("empty", "col") == 0.0


def test_column_sum(sqlite_db):
    connector = SQLiteConnector(database=str(sqlite_db))
    with connector:
        total = connector.get_column_sum("orders", "amount")
        # 100.00 + 250.50 + 75.25 (NULL skipped by SUM)
        assert total == pytest.approx(425.75)


def test_column_sum_all_null(tmp_path):
    db_path = tmp_path / "null.sqlite"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE t (v REAL);
        INSERT INTO t VALUES (NULL), (NULL);
        """
    )
    conn.commit()
    conn.close()

    connector = SQLiteConnector(database=str(db_path))
    with connector:
        assert connector.get_column_sum("t", "v") is None


def test_freshness(sqlite_db):
    connector = SQLiteConnector(database=str(sqlite_db))
    with connector:
        freshness = connector.get_table_freshness("orders")
        assert isinstance(freshness, datetime)
        # Most recent row is "now", so freshness should be within a few seconds.
        assert (datetime.utcnow() - freshness) < timedelta(seconds=10)


def test_freshness_empty_table(tmp_path):
    db_path = tmp_path / "empty_ts.sqlite"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE t (updated_at TEXT)")
    conn.commit()
    conn.close()

    connector = SQLiteConnector(database=str(db_path))
    with connector:
        assert connector.get_table_freshness("t") is None


def test_context_manager_closes(sqlite_db):
    connector = SQLiteConnector(database=str(sqlite_db))
    with connector:
        connector.execute_query("SELECT 1")
    # After exit, connection should be closed.
    assert connector._conn is None


def test_in_memory_database():
    connector = SQLiteConnector(":memory:")
    with connector:
        connector.execute_query("CREATE TABLE t (x INTEGER)")
        connector.execute_query("INSERT INTO t VALUES (1), (2), (3)")
        assert connector.get_row_count("t") == 3


def test_config_get_connector_returns_sqlite(tmp_path):
    from litmus.config.settings import LitmusConfig, WarehouseConfig, get_connector

    cfg = LitmusConfig(warehouse=WarehouseConfig(type="sqlite", database=":memory:"))
    connector = get_connector(cfg)
    assert isinstance(connector, SQLiteConnector)
