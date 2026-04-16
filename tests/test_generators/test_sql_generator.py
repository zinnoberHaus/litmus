"""Tests for litmus.generators.sql_generator — SQL query generation."""

from __future__ import annotations

from litmus.generators.sql_generator import generate_check_queries
from litmus.spec.metric_spec import (
    FreshnessRule,
    MetricSpec,
    NullRule,
    TrustSpec,
    VolumeRule,
)


def _make_spec(**trust_overrides) -> MetricSpec:
    """Build a MetricSpec with a Trust block; trust_overrides go into TrustSpec."""
    trust = TrustSpec(**trust_overrides)
    return MetricSpec(
        name="Test Revenue",
        description="Total revenue",
        sources=["orders"],
        conditions=["all records from orders"],
        calculations=["sum the amount column"],
        result_name="Test Revenue",
        trust=trust,
    )


class TestGenerateFreshnessQuery:
    """Freshness generates a MAX(updated_at) query."""

    def test_freshness_query_present(self):
        spec = _make_spec(freshness=FreshnessRule(max_hours=24))
        queries = generate_check_queries(spec)

        assert "freshness" in queries
        sql = queries["freshness"]
        assert "MAX(updated_at)" in sql
        assert "orders" in sql

    def test_no_freshness_when_rule_absent(self):
        spec = _make_spec()
        queries = generate_check_queries(spec)

        assert "freshness" not in queries


class TestGenerateNullRateQuery:
    """Null rate generates a COUNT / NULL-count query."""

    def test_null_rate_query_present(self):
        spec = _make_spec(null_rules=[NullRule(column="amount", max_percentage=5.0)])
        queries = generate_check_queries(spec)

        assert "null_rate_amount" in queries
        sql = queries["null_rate_amount"]
        assert "amount" in sql
        assert "NULL" in sql
        assert "orders" in sql

    def test_multiple_null_rules(self):
        spec = _make_spec(
            null_rules=[
                NullRule(column="amount", max_percentage=5.0),
                NullRule(column="status", max_percentage=0.0),
            ]
        )
        queries = generate_check_queries(spec)

        assert "null_rate_amount" in queries
        assert "null_rate_status" in queries


class TestGenerateVolumeQuery:
    """Volume generates a COUNT(*) query."""

    def test_volume_query_present(self):
        spec = _make_spec(
            volume_rules=[VolumeRule(table=None, max_drop_percentage=25.0, period="day")]
        )
        queries = generate_check_queries(spec)

        assert "volume_orders" in queries
        sql = queries["volume_orders"]
        assert "COUNT(*)" in sql

    def test_volume_with_specific_table(self):
        spec = _make_spec(
            volume_rules=[VolumeRule(table="payments", max_drop_percentage=15.0, period="week")]
        )
        queries = generate_check_queries(spec)

        assert "volume_payments" in queries
        assert "payments" in queries["volume_payments"]


class TestGenerateAllQueries:
    """Multiple trust rules produce multiple queries."""

    def test_generates_freshness_null_volume(self):
        spec = _make_spec(
            freshness=FreshnessRule(max_hours=24),
            null_rules=[NullRule(column="amount", max_percentage=5.0)],
            volume_rules=[VolumeRule(table=None, max_drop_percentage=25.0, period="day")],
        )
        queries = generate_check_queries(spec)

        assert "freshness" in queries
        assert "null_rate_amount" in queries
        assert "volume_orders" in queries
        assert len(queries) == 3

    def test_empty_trust_returns_empty(self):
        spec = _make_spec()
        queries = generate_check_queries(spec)
        assert queries == {}


class TestNoTrustSpec:
    """A MetricSpec with no trust block produces no queries."""

    def test_none_trust(self):
        spec = MetricSpec(
            name="No Trust",
            sources=["orders"],
            conditions=[],
            calculations=[],
            result_name="No Trust",
            trust=None,
        )
        queries = generate_check_queries(spec)
        assert queries == {}
