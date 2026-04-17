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
    """Value is near the boundary of the range (within 10% of the boundary's magnitude)."""

    def test_near_lower_boundary_warns(self):
        # range 100-200; lower margin = abs(100)*0.1 = 10; SUM = 105 => within
        # 10 of the lower boundary, so WARNING.
        connector = _make_connector([105.0])
        rule = RangeRule(min_value=100.0, max_value=200.0)
        result = check_range(connector, "orders", "amount", rule)

        assert result.status == CheckStatus.WARNING

    def test_near_upper_boundary_warns(self):
        # range 0-1000; upper margin = abs(1000)*0.1 = 100; SUM = 950 => within upper margin
        connector = _make_connector([950.0])
        rule = RangeRule(min_value=0.0, max_value=1000.0)
        result = check_range(connector, "orders", "amount", rule)

        assert result.status == CheckStatus.WARNING

    def test_small_value_on_wide_zero_indexed_range_passes(self):
        # Regression for the first-run "yellow by default" papercut: range
        # 0-10M with a value of 3,181 should be PASSED, not WARNING. The old
        # flat-10%-of-range-width logic would have flagged this.
        connector = _make_connector([3181.0])
        rule = RangeRule(min_value=0.0, max_value=10_000_000.0)
        result = check_range(connector, "orders", "amount", rule)

        assert result.status == CheckStatus.PASSED


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
