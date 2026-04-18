"""Parity tests for :class:`WarehouseHistoryStore` against DuckDB.

The warehouse store must match the SQLite-backed :class:`HistoryStore` row
for row — same inputs in, same :class:`HistoryRecord` out. We exercise it
through a real DuckDB connection (the same fixture the rest of the check
suite uses) rather than mocking, because SQL dialect quirks are exactly
what this backend exists to smooth over.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import duckdb
import pytest

from litmus.checks.change import check_change
from litmus.checks.history import HistoryStore, HistoryStoreProtocol, WarehouseHistoryStore
from litmus.checks.runner import CheckStatus, run_checks
from litmus.connectors.duckdb import DuckDBConnector
from litmus.spec.metric_spec import ChangeRule, MetricSpec, RangeRule, TrustSpec


@pytest.fixture()
def warehouse_store():
    """Fresh in-memory DuckDB + WarehouseHistoryStore per test.

    Each test gets its own connection so state doesn't leak. We hand both
    the connector and store back so tests can drive queries directly when
    they need to inspect the underlying table.
    """
    conn = duckdb.connect(":memory:")
    connector = DuckDBConnector(connection=conn)
    connector.connect()
    store = WarehouseHistoryStore(connector=connector)
    store.connect()
    try:
        yield store, connector
    finally:
        store.close()
        connector.close()


def test_satisfies_protocol(warehouse_store):
    """The store must structurally match the runner's expected interface."""
    store, _ = warehouse_store
    assert isinstance(store, HistoryStoreProtocol)


def test_creates_table_on_connect(warehouse_store):
    _, connector = warehouse_store
    # If the table exists, this query succeeds with zero rows.
    rows = connector.execute_query("SELECT COUNT(*) AS cnt FROM litmus_history")
    assert rows[0]["cnt"] == 0


def test_record_and_retrieve(warehouse_store):
    store, _ = warehouse_store
    store.record("Revenue", value_sum=1000.0, row_count=10)
    last = store.last_record("Revenue")
    assert last is not None
    assert last.metric_name == "Revenue"
    assert last.value_sum == 1000.0
    assert last.row_count == 10


def test_records_survive_metric_name_with_quotes(warehouse_store):
    """Apostrophes in metric names must not break the insert."""
    store, _ = warehouse_store
    store.record("Finance's Revenue", value_sum=1.0, row_count=1)
    got = store.last_record("Finance's Revenue")
    assert got is not None
    assert got.metric_name == "Finance's Revenue"


def test_previous_record_respects_period(warehouse_store):
    store, _ = warehouse_store
    now = datetime.now(timezone.utc)
    store.record("Revenue", 1000.0, 10, recorded_at=now - timedelta(days=40))
    store.record("Revenue", 1100.0, 11, recorded_at=now - timedelta(days=5))
    store.record("Revenue", 1200.0, 12, recorded_at=now - timedelta(hours=1))

    prior_month = store.previous_record("Revenue", "month", now=now)
    assert prior_month is not None
    assert prior_month.value_sum == 1000.0

    # 5-day-old row doesn't satisfy "week" (7 days); only the 40-day row does.
    prior_week = store.previous_record("Revenue", "week", now=now)
    assert prior_week is not None
    assert prior_week.value_sum == 1000.0

    # "day" accepts anything older than 1 day; 5-day row wins by recency.
    prior_day = store.previous_record("Revenue", "day", now=now)
    assert prior_day is not None
    assert prior_day.value_sum == 1100.0


def test_previous_record_none_if_empty(warehouse_store):
    store, _ = warehouse_store
    assert store.previous_record("never-seen", "month") is None


def test_unknown_period_raises(warehouse_store):
    store, _ = warehouse_store
    with pytest.raises(ValueError, match="Unknown period"):
        store.previous_record("Revenue", "fortnight")


def test_all_records_ordered_oldest_first(warehouse_store):
    store, _ = warehouse_store
    now = datetime.now(timezone.utc)
    store.record("Revenue", 200.0, 2, recorded_at=now - timedelta(days=2))
    store.record("Revenue", 100.0, 1, recorded_at=now - timedelta(days=5))
    store.record("Revenue", 300.0, 3, recorded_at=now - timedelta(days=1))

    records = store.all_records("Revenue")
    assert [r.value_sum for r in records] == [100.0, 200.0, 300.0]


def test_purge_single_metric(warehouse_store):
    store, _ = warehouse_store
    store.record("A", 1.0, 1)
    store.record("A", 2.0, 2)
    store.record("B", 3.0, 3)

    deleted = store.purge("A")
    assert deleted == 2
    assert store.last_record("A") is None
    assert store.last_record("B") is not None


def test_purge_all(warehouse_store):
    store, _ = warehouse_store
    store.record("A", 1.0, 1)
    store.record("B", 2.0, 2)
    assert store.purge() == 2
    assert store.last_record("A") is None
    assert store.last_record("B") is None


def test_column_means_round_trip(warehouse_store):
    """The JSON blob for per-column means must deserialise cleanly."""
    store, _ = warehouse_store
    store.record(
        "Revenue",
        1000.0,
        10,
        column_means={"amount": 100.0, "refund": 5.5},
    )
    last = store.last_record("Revenue")
    assert last is not None
    assert last.column_means == {"amount": 100.0, "refund": 5.5}


def test_connect_is_idempotent(warehouse_store):
    """Calling connect() twice must not fail (DDL is IF NOT EXISTS)."""
    store, _ = warehouse_store
    store.connect()  # already called by fixture
    store.connect()
    store.record("R", 1.0, 1)
    assert store.last_record("R") is not None


# ---------------------------------------------------------------------------
# Parity with the SQLite-backed HistoryStore. If these drift, either the
# abstraction is leaking or we've introduced a behavioural regression — either
# way a check-module consumer notices.
# ---------------------------------------------------------------------------


def test_parity_check_change_passes_when_history_empty(warehouse_store):
    store, _ = warehouse_store
    rule = ChangeRule(max_change_percentage=30.0, period="month")
    result = check_change(rule, "Revenue", current_value=1000.0, history=store)
    assert result.status == CheckStatus.PASSED
    assert "warming up" in result.message


def test_parity_check_change_detects_violation(warehouse_store):
    store, _ = warehouse_store
    now = datetime.now(timezone.utc)
    store.record("Revenue", 1000.0, 10, recorded_at=now - timedelta(days=40))

    rule = ChangeRule(max_change_percentage=30.0, period="month")
    result = check_change(rule, "Revenue", current_value=2000.0, history=store)
    assert result.status == CheckStatus.FAILED
    assert result.actual_value == 100.0


def test_parity_runner_records_each_run(warehouse_store, tmp_path):
    """Full run_checks() integration — warehouse path must match the SQLite path."""
    store, connector = warehouse_store

    # Seed the orders table on the same connector the history lives in.
    # (Prod users will run against a real warehouse with an existing orders
    # table; for this test we mint one so the check can compute SUM/COUNT.)
    raw = connector._ensure_connected()  # type: ignore[attr-defined]
    raw.execute(
        """
        CREATE TABLE orders (
            order_id   INTEGER,
            amount     DOUBLE,
            updated_at TIMESTAMP
        )
        """
    )
    raw.execute(
        "INSERT INTO orders VALUES "
        "(1, 100.0, CURRENT_TIMESTAMP), (2, 200.0, CURRENT_TIMESTAMP), "
        "(3, 300.0, CURRENT_TIMESTAMP)"
    )

    spec = MetricSpec(
        name="Test Revenue",
        sources=["orders"],
        trust=TrustSpec(
            range_rules=[RangeRule(min_value=0, max_value=1_000_000)],
            change_rules=[ChangeRule(max_change_percentage=50.0, period="month")],
        ),
    )
    run_checks(connector, spec, history=store, run_id="r1", commit_sha="abc")
    run_checks(connector, spec, history=store, run_id="r2", commit_sha="def")

    records = store.all_records("Test Revenue")
    assert len(records) == 2
    run_ids = [r.run_id for r in records]
    assert "r1" in run_ids
    assert "r2" in run_ids
    assert records[0].row_count == 3
    assert records[0].value_sum == 600.0


def test_parity_with_sqlite_backend(tmp_path):
    """Same inputs → identical HistoryRecord fields across both backends.

    Guards against silent drift — the blueprint's Risk table calls this out as
    a "pause and validate" signal (§5.2).
    """
    # SQLite side.
    sqlite_store = HistoryStore(path=tmp_path / "h.db")
    sqlite_store.connect()

    # Warehouse side.
    conn = duckdb.connect(":memory:")
    connector = DuckDBConnector(connection=conn)
    connector.connect()
    wh_store = WarehouseHistoryStore(connector=connector)
    wh_store.connect()

    try:
        ts = datetime(2026, 4, 18, 12, 0, tzinfo=timezone.utc)
        for s in (sqlite_store, wh_store):
            s.record(
                "Revenue",
                value_sum=1234.56,
                row_count=42,
                run_id="r1",
                commit_sha="deadbeef",
                recorded_at=ts,
                schema_fingerprint="a,b,c",
                column_means={"amount": 29.39},
            )

        sqlite_last = sqlite_store.last_record("Revenue")
        wh_last = wh_store.last_record("Revenue")
        assert sqlite_last is not None and wh_last is not None

        assert sqlite_last.metric_name == wh_last.metric_name
        assert sqlite_last.value_sum == wh_last.value_sum
        assert sqlite_last.row_count == wh_last.row_count
        assert sqlite_last.run_id == wh_last.run_id
        assert sqlite_last.commit_sha == wh_last.commit_sha
        assert sqlite_last.schema_fingerprint == wh_last.schema_fingerprint
        assert sqlite_last.column_means == wh_last.column_means
        # Recorded_at crosses a string boundary on both backends — compare
        # as datetimes not strings.
        assert sqlite_last.recorded_at == wh_last.recorded_at
    finally:
        sqlite_store.close()
        wh_store.close()
        connector.close()
