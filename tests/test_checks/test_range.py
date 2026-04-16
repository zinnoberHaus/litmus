"""Tests for litmus.checks.range — value range check."""

from __future__ import annotations

import duckdb

from litmus.checks.range import check_range
from litmus.checks.runner import CheckStatus
from litmus.connectors.duckdb import DuckDBConnector
from litmus.spec.metric_spec import RangeRule


def _make_connector(amounts: list[float]) -> DuckDBConnector:
    """Create an in-memory DuckDB with an orders table containing the given amounts."""
    conn = duckdb.connect(":memory:")
    conn.execute("CREATE TABLE orders (id INT, amount DOUBLE)")
    for i, amt in enumerate(amounts, 1):
        conn.execute("INSERT INTO orders VALUES (?, ?)", [i, amt])
    return DuckDBConnector(connection=conn)


class TestRangePassed:
    """Value is comfortably within the expected range."""

    def test_value_in_middle_of_range(self):
        # SUM = 100 + 200 + 300 = 600, range 0-1000
        connector = _make_connector([100.0, 200.0, 300.0])
        rule = RangeRule(min_value=0.0, max_value=1000.0)
        result = check_range(connector, "orders", "amount", rule)

        assert result.status == CheckStatus.PASSED
        assert result.actual_value == 600.0

    def test_large_range(self):
        # 500000 is well within [0, 1_000_000] — more than 10% from either edge
        connector = _make_connector([500000.0])
        rule = RangeRule(min_value=0.0, max_value=1_000_000.0)
        result = check_range(connector, "orders", "amount", rule)

        assert result.status == CheckStatus.PASSED


class TestRangeFailed:
    """Value is outside the expected range."""

    def test_value_above_max(self):
        # SUM = 5000, range 0-1000
        connector = _make_connector([2000.0, 3000.0])
        rule = RangeRule(min_value=0.0, max_value=1000.0)
        result = check_range(connector, "orders", "amount", rule)

        assert result.status == CheckStatus.FAILED
        assert result.actual_value == 5000.0

    def test_value_below_min(self):
        # SUM = -50, range 0-1000
        connector = _make_connector([-100.0, 50.0])
        rule = RangeRule(min_value=0.0, max_value=1000.0)
        result = check_range(connector, "orders", "amount", rule)

        assert result.status == CheckStatus.FAILED
        assert result.actual_value == -50.0


class TestRangeWarning:
    """Value is near the boundary of the range (within 10% margin)."""

    def test_near_lower_boundary_warns(self):
        # range 0-1000, margin = 100; SUM = 50 => within boundary margin
        connector = _make_connector([50.0])
        rule = RangeRule(min_value=0.0, max_value=1000.0)
        result = check_range(connector, "orders", "amount", rule)

        assert result.status == CheckStatus.WARNING

    def test_near_upper_boundary_warns(self):
        # range 0-1000, margin = 100; SUM = 950 => within upper margin
        connector = _make_connector([950.0])
        rule = RangeRule(min_value=0.0, max_value=1000.0)
        result = check_range(connector, "orders", "amount", rule)

        assert result.status == CheckStatus.WARNING


class TestRangeError:
    """Query failures produce ERROR."""

    def test_error_on_missing_table(self):
        conn = duckdb.connect(":memory:")
        connector = DuckDBConnector(connection=conn)
        rule = RangeRule(min_value=0.0, max_value=1000.0)
        result = check_range(connector, "nonexistent_table", "amount", rule)

        assert result.status == CheckStatus.ERROR
        assert "Could not query value" in result.message

    def test_error_on_missing_column(self):
        conn = duckdb.connect(":memory:")
        conn.execute("CREATE TABLE orders (id INT)")
        connector = DuckDBConnector(connection=conn)
        rule = RangeRule(min_value=0.0, max_value=1000.0)
        result = check_range(connector, "orders", "nonexistent_col", rule)

        assert result.status == CheckStatus.ERROR


class TestRangeResultShape:
    """Verify the result object has the expected fields."""

    def test_result_name(self):
        connector = _make_connector([500.0])
        rule = RangeRule(min_value=0.0, max_value=1000.0)
        result = check_range(connector, "orders", "amount", rule)

        assert result.name == "Value range"
        assert result.threshold is not None
        assert result.message is not None
