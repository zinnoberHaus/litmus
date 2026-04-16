"""Tests for litmus.checks.volume — row volume check."""

from __future__ import annotations

from datetime import datetime, timedelta

import duckdb

from litmus.checks.runner import CheckStatus
from litmus.checks.volume import check_volume
from litmus.connectors.duckdb import DuckDBConnector
from litmus.spec.metric_spec import VolumeRule


def _make_connector(
    current_rows: int,
    old_rows: int = 0,
    include_timestamp: bool = True,
) -> DuckDBConnector:
    """Build an in-memory DuckDB with orders split into current and old rows.

    ``current_rows`` get a recent updated_at; ``old_rows`` get one set
    far in the past so they fall outside the period comparison window.
    """
    conn = duckdb.connect(":memory:")
    conn.execute("CREATE TABLE orders (id INT, updated_at TIMESTAMP)")

    now = datetime.utcnow()

    for i in range(1, current_rows + 1):
        conn.execute(
            "INSERT INTO orders VALUES (?, ?)",
            [i, now - timedelta(minutes=i)],
        )

    for i in range(1, old_rows + 1):
        conn.execute(
            "INSERT INTO orders VALUES (?, ?)",
            [current_rows + i, now - timedelta(days=10, minutes=i)],
        )

    return DuckDBConnector(connection=conn)


class TestVolumePassed:
    """Row count is stable — should PASS."""

    def test_stable_volume_passes(self):
        # 100 current + 100 old => change = 0% (all rows remain)
        connector = _make_connector(current_rows=100, old_rows=100)
        rule = VolumeRule(table=None, max_drop_percentage=25.0, period="day")
        result = check_volume(connector, "orders", rule)

        assert result.status == CheckStatus.PASSED

    def test_with_table_override(self):
        connector = _make_connector(current_rows=50, old_rows=50)
        rule = VolumeRule(table="orders", max_drop_percentage=25.0, period="day")
        result = check_volume(connector, "orders", rule)

        assert result.status == CheckStatus.PASSED
        assert "orders" in result.name


class TestVolumeFallback:
    """When no historical data exists, the check should PASS with a fallback message."""

    def test_no_old_data_passes_with_message(self):
        # Only current rows, no old rows => prior_count = 0, should get fallback
        connector = _make_connector(current_rows=10, old_rows=0)
        rule = VolumeRule(table=None, max_drop_percentage=25.0, period="day")
        result = check_volume(connector, "orders", rule)

        assert result.status == CheckStatus.PASSED
        msg = result.message.lower()
        assert "no prior period data" in msg or "no historical" in msg

    def test_empty_table_passes_gracefully(self):
        connector = _make_connector(current_rows=0, old_rows=0)
        rule = VolumeRule(table=None, max_drop_percentage=25.0, period="day")
        result = check_volume(connector, "orders", rule)

        # With 0 rows and 0 prior, should still handle gracefully
        assert result.status in (CheckStatus.PASSED, CheckStatus.ERROR)


class TestVolumeResult:
    """Verify result object structure."""

    def test_result_name_without_table(self):
        connector = _make_connector(current_rows=10, old_rows=10)
        rule = VolumeRule(table=None, max_drop_percentage=25.0, period="day")
        result = check_volume(connector, "orders", rule)

        assert result.name == "Row count"

    def test_result_name_with_table(self):
        connector = _make_connector(current_rows=10, old_rows=10)
        rule = VolumeRule(table="orders", max_drop_percentage=25.0, period="day")
        result = check_volume(connector, "orders", rule)

        assert "orders" in result.name

    def test_threshold_stored(self):
        connector = _make_connector(current_rows=10, old_rows=10)
        rule = VolumeRule(table=None, max_drop_percentage=25.0, period="day")
        result = check_volume(connector, "orders", rule)

        assert result.threshold == 25.0
