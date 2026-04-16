"""Tests for litmus.checks.null_rate — null rate check."""

from __future__ import annotations

import duckdb

from litmus.checks.null_rate import check_null_rate
from litmus.checks.runner import CheckStatus
from litmus.connectors.duckdb import DuckDBConnector
from litmus.spec.metric_spec import NullRule


def _make_connector(rows: list[tuple]) -> DuckDBConnector:
    """Create an in-memory DuckDB with an orders table from the given rows.

    Each row is (order_id, amount) where amount may be None.
    """
    conn = duckdb.connect(":memory:")
    conn.execute("CREATE TABLE orders (order_id INT, amount DOUBLE)")
    for row in rows:
        conn.execute("INSERT INTO orders VALUES (?, ?)", list(row))
    return DuckDBConnector(connection=conn)


class TestNullRatePassed:
    """Null rate is within the allowed threshold."""

    def test_no_nulls_passes(self):
        connector = _make_connector([
            (1, 100.0),
            (2, 200.0),
            (3, 300.0),
        ])
        rule = NullRule(column="amount", max_percentage=5.0)
        result = check_null_rate(connector, "orders", rule)

        assert result.status == CheckStatus.PASSED
        assert result.actual_value == 0.0

    def test_low_null_rate_passes(self):
        # 1 null out of 10 = 10%, threshold 15%
        rows = [(i, float(i * 10)) for i in range(1, 10)]
        rows.append((10, None))
        connector = _make_connector(rows)
        rule = NullRule(column="amount", max_percentage=15.0)
        result = check_null_rate(connector, "orders", rule)

        assert result.status == CheckStatus.PASSED
        assert result.actual_value == 10.0


class TestNullRateFailed:
    """Null rate exceeds the allowed threshold."""

    def test_high_null_rate_fails(self):
        # 3 nulls out of 5 = 60%, threshold 5%
        connector = _make_connector([
            (1, 100.0),
            (2, None),
            (3, None),
            (4, None),
            (5, 500.0),
        ])
        rule = NullRule(column="amount", max_percentage=5.0)
        result = check_null_rate(connector, "orders", rule)

        assert result.status == CheckStatus.FAILED
        assert result.actual_value == 60.0

    def test_all_nulls_fails(self):
        connector = _make_connector([
            (1, None),
            (2, None),
        ])
        rule = NullRule(column="amount", max_percentage=5.0)
        result = check_null_rate(connector, "orders", rule)

        assert result.status == CheckStatus.FAILED
        assert result.actual_value == 100.0


class TestNullRateExactZero:
    """When max_percentage is 0, any nulls at all should fail."""

    def test_zero_threshold_passes_when_no_nulls(self):
        connector = _make_connector([
            (1, 100.0),
            (2, 200.0),
        ])
        rule = NullRule(column="amount", max_percentage=0.0)
        result = check_null_rate(connector, "orders", rule)

        assert result.status == CheckStatus.PASSED

    def test_zero_threshold_fails_with_any_null(self):
        connector = _make_connector([
            (1, 100.0),
            (2, None),
            (3, 300.0),
        ])
        rule = NullRule(column="amount", max_percentage=0.0)
        result = check_null_rate(connector, "orders", rule)

        assert result.status == CheckStatus.FAILED


class TestNullRateWarning:
    """Null rate near the threshold triggers WARNING."""

    def test_near_threshold_gives_warning(self):
        # 91 nulls out of 1000 = 9.1%, threshold 10% => 9.1/10 = 0.91 > 0.9 => warning
        rows = [(i, float(i)) for i in range(1, 910)]
        for i in range(910, 1001):
            rows.append((i, None))
        connector = _make_connector(rows)
        rule = NullRule(column="amount", max_percentage=10.0)
        result = check_null_rate(connector, "orders", rule)

        assert result.status == CheckStatus.WARNING


class TestNullRateResult:
    """Verify the result object shape."""

    def test_result_has_expected_fields(self):
        connector = _make_connector([(1, 100.0)])
        rule = NullRule(column="amount", max_percentage=5.0)
        result = check_null_rate(connector, "orders", rule)

        assert result.name == "Null rate on amount"
        assert result.threshold == 5.0
        assert result.message is not None
