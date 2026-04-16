"""Tests for litmus.checks.freshness — data freshness check."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import duckdb

from litmus.checks.freshness import check_freshness
from litmus.checks.runner import CheckStatus
from litmus.connectors.duckdb import DuckDBConnector
from litmus.spec.metric_spec import FreshnessRule


def _make_connector_with_timestamp(ts: datetime) -> DuckDBConnector:
    """Create an in-memory DuckDB with a single row carrying *ts* as updated_at."""
    conn = duckdb.connect(":memory:")
    conn.execute("CREATE TABLE orders (id INT, updated_at TIMESTAMP)")
    conn.execute(
        "INSERT INTO orders VALUES (1, ?)",
        [ts],
    )
    return DuckDBConnector(connection=conn)


class TestFreshnessPassed:
    """Data is fresh enough -- should PASS."""

    def test_recent_data_passes(self):
        recent = datetime.now(timezone.utc) - timedelta(hours=1)
        connector = _make_connector_with_timestamp(recent)
        rule = FreshnessRule(max_hours=24)
        result = check_freshness(connector, "orders", rule)

        assert result.status == CheckStatus.PASSED
        assert result.name == "Freshness"
        assert result.actual_value is not None
        assert result.actual_value < 24

    def test_just_under_threshold_passes(self):
        # 10 hours old, threshold 24 — well within limits (10/24 = 0.42 < 0.9 warning)
        ts = datetime.now(timezone.utc) - timedelta(hours=10)
        connector = _make_connector_with_timestamp(ts)
        rule = FreshnessRule(max_hours=24)
        result = check_freshness(connector, "orders", rule)

        assert result.status == CheckStatus.PASSED


class TestFreshnessFailed:
    """Data is stale -- should FAIL."""

    def test_old_data_fails(self):
        old = datetime.now(timezone.utc) - timedelta(hours=48)
        connector = _make_connector_with_timestamp(old)
        rule = FreshnessRule(max_hours=24)
        result = check_freshness(connector, "orders", rule)

        assert result.status == CheckStatus.FAILED
        assert result.actual_value is not None
        assert result.actual_value > 24

    def test_barely_over_threshold_fails(self):
        ts = datetime.now(timezone.utc) - timedelta(hours=25)
        connector = _make_connector_with_timestamp(ts)
        rule = FreshnessRule(max_hours=24)
        result = check_freshness(connector, "orders", rule)

        assert result.status == CheckStatus.FAILED


class TestFreshnessError:
    """Query fails -- should return ERROR."""

    def test_error_on_missing_table(self):
        conn = duckdb.connect(":memory:")
        connector = DuckDBConnector(connection=conn)
        rule = FreshnessRule(max_hours=24)
        result = check_freshness(connector, "nonexistent_table", rule)

        assert result.status == CheckStatus.ERROR
        assert "Could not query freshness" in result.message

    def test_error_on_empty_table(self):
        conn = duckdb.connect(":memory:")
        conn.execute("CREATE TABLE empty_orders (id INT, updated_at TIMESTAMP)")
        connector = DuckDBConnector(connection=conn)
        rule = FreshnessRule(max_hours=24)
        result = check_freshness(connector, "empty_orders", rule)

        assert result.status == CheckStatus.ERROR
        assert "No timestamp data" in result.message


class TestFreshnessWarning:
    """Data age is within the 90% warning threshold."""

    def test_near_threshold_gives_warning(self):
        # Directly test the logic: if age_hours is between threshold*0.9 and threshold
        # we should get WARNING. Use a connector that returns a known time.
        from unittest.mock import MagicMock

        connector = MagicMock()
        # Return a timestamp that is 22 hours ago
        connector.get_table_freshness.return_value = (
            datetime.now(timezone.utc) - timedelta(hours=22)
        )
        rule = FreshnessRule(max_hours=24)
        result = check_freshness(connector, "orders", rule)

        # 22/24 = 0.917 > 0.9 but < 1.0 => WARNING
        assert result.status == CheckStatus.WARNING
