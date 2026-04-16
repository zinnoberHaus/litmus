"""Tests for litmus.parser.parser — parsing .metric files into MetricSpec."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from litmus.parser.errors import InvalidTrustRuleError, MissingHeaderError
from litmus.parser.parser import parse_metric_file, parse_metric_string
from litmus.spec.metric_spec import (
    MetricSpec,
)

# ---------------------------------------------------------------------------
# Fixture data
# ---------------------------------------------------------------------------

_FULL_METRIC = dedent("""\
    Metric: Monthly Revenue
    Description: Total revenue from completed orders in the current calendar month
    Owner: data-team
    Tags: finance, revenue, monthly

    Source: orders, payments

    Given all records from orders table
      And status is "completed"
      And order_date is within current calendar month

    When we calculate
      Then sum the amount column
      And subtract refunds
      And round to 2 decimal places

    The result is "Monthly Revenue"

    Trust:
      Freshness must be less than 24 hours
      Null rate on amount must be less than 5%
      Null rate on order_id must be 0%
      Row count must not drop more than 25% day over day
      Row count of payments must not drop more than 15% week over week
      Value must be between 0 and 10,000,000
      Value must not change more than 50% month over month
""")

_MINIMAL_METRIC = dedent("""\
    Metric: Simple Count

    Source: events

    Given all records from events table

    When we calculate
      Then count the rows

    The result is "Simple Count"
""")


# ---------------------------------------------------------------------------
# Core parsing tests
# ---------------------------------------------------------------------------


class TestParseValidMetric:
    """Parse a complete .metric string with all sections."""

    def test_name(self):
        spec = parse_metric_string(_FULL_METRIC)
        assert spec.name == "Monthly Revenue"

    def test_description(self):
        spec = parse_metric_string(_FULL_METRIC)
        expected = (
            "Total revenue from completed orders"
            " in the current calendar month"
        )
        assert spec.description == expected

    def test_owner(self):
        spec = parse_metric_string(_FULL_METRIC)
        assert spec.owner == "data-team"

    def test_tags(self):
        spec = parse_metric_string(_FULL_METRIC)
        assert spec.tags == ["finance", "revenue", "monthly"]

    def test_sources(self):
        spec = parse_metric_string(_FULL_METRIC)
        assert spec.sources == ["orders", "payments"]

    def test_conditions(self):
        spec = parse_metric_string(_FULL_METRIC)
        assert len(spec.conditions) == 3
        assert "all records from orders table" in spec.conditions[0]
        assert 'status is "completed"' in spec.conditions[1]
        assert "order_date is within current calendar month" in spec.conditions[2]

    def test_calculations(self):
        spec = parse_metric_string(_FULL_METRIC)
        assert len(spec.calculations) == 3
        assert "sum the amount column" in spec.calculations[0]
        assert "subtract refunds" in spec.calculations[1]
        assert "round to 2 decimal places" in spec.calculations[2]

    def test_result_name(self):
        spec = parse_metric_string(_FULL_METRIC)
        assert spec.result_name == "Monthly Revenue"

    def test_trust_is_present(self):
        spec = parse_metric_string(_FULL_METRIC)
        assert spec.trust is not None

    def test_raw_text_preserved(self):
        spec = parse_metric_string(_FULL_METRIC)
        assert spec.raw_text == _FULL_METRIC

    def test_returns_metric_spec_instance(self):
        spec = parse_metric_string(_FULL_METRIC)
        assert isinstance(spec, MetricSpec)


class TestParseMinimalMetric:
    """Parse a metric with only required sections (no Trust block)."""

    def test_name(self):
        spec = parse_metric_string(_MINIMAL_METRIC)
        assert spec.name == "Simple Count"

    def test_no_description(self):
        spec = parse_metric_string(_MINIMAL_METRIC)
        assert spec.description is None

    def test_no_owner(self):
        spec = parse_metric_string(_MINIMAL_METRIC)
        assert spec.owner is None

    def test_empty_tags(self):
        spec = parse_metric_string(_MINIMAL_METRIC)
        assert spec.tags == []

    def test_sources(self):
        spec = parse_metric_string(_MINIMAL_METRIC)
        assert spec.sources == ["events"]

    def test_trust_is_none(self):
        spec = parse_metric_string(_MINIMAL_METRIC)
        assert spec.trust is None


# ---------------------------------------------------------------------------
# Trust rule parsing
# ---------------------------------------------------------------------------


class TestParseTrustFreshness:
    """Verify freshness rule parsing."""

    def test_hours(self):
        spec = parse_metric_string(_FULL_METRIC)
        assert spec.trust is not None
        assert spec.trust.freshness is not None
        assert spec.trust.freshness.max_hours == 24.0

    def test_minutes(self):
        text = dedent("""\
            Metric: Fast Metric
            Source: events
            Given all records from events table
            When we calculate
              Then count the rows
            The result is "Fast Metric"
            Trust:
              Freshness must be less than 30 minutes
        """)
        spec = parse_metric_string(text)
        assert spec.trust is not None
        assert spec.trust.freshness is not None
        assert spec.trust.freshness.max_hours == 0.5

    def test_days(self):
        text = dedent("""\
            Metric: Slow Metric
            Source: events
            Given all records from events table
            When we calculate
              Then count the rows
            The result is "Slow Metric"
            Trust:
              Freshness must be less than 2 days
        """)
        spec = parse_metric_string(text)
        assert spec.trust is not None
        assert spec.trust.freshness is not None
        assert spec.trust.freshness.max_hours == 48.0


class TestParseTrustNullRate:
    """Verify null rate parsing with 'less than' and exact 0%."""

    def test_less_than_percentage(self):
        spec = parse_metric_string(_FULL_METRIC)
        assert spec.trust is not None
        amount_rules = [r for r in spec.trust.null_rules if r.column == "amount"]
        assert len(amount_rules) == 1
        assert amount_rules[0].max_percentage == 5.0

    def test_exact_zero(self):
        spec = parse_metric_string(_FULL_METRIC)
        assert spec.trust is not None
        id_rules = [r for r in spec.trust.null_rules if r.column == "order_id"]
        assert len(id_rules) == 1
        assert id_rules[0].max_percentage == 0.0

    def test_multiple_null_rules(self):
        spec = parse_metric_string(_FULL_METRIC)
        assert spec.trust is not None
        assert len(spec.trust.null_rules) == 2


class TestParseTrustVolume:
    """Verify volume rule with 'of table' and without."""

    def test_volume_without_table(self):
        spec = parse_metric_string(_FULL_METRIC)
        assert spec.trust is not None
        no_table_rules = [r for r in spec.trust.volume_rules if r.table is None]
        assert len(no_table_rules) == 1
        assert no_table_rules[0].max_drop_percentage == 25.0
        assert no_table_rules[0].period == "day"

    def test_volume_with_table(self):
        spec = parse_metric_string(_FULL_METRIC)
        assert spec.trust is not None
        table_rules = [r for r in spec.trust.volume_rules if r.table == "payments"]
        assert len(table_rules) == 1
        assert table_rules[0].max_drop_percentage == 15.0
        assert table_rules[0].period == "week"


class TestParseTrustRange:
    """Range rule with comma-formatted numbers."""

    def test_range_values(self):
        spec = parse_metric_string(_FULL_METRIC)
        assert spec.trust is not None
        assert len(spec.trust.range_rules) == 1
        assert spec.trust.range_rules[0].min_value == 0.0
        assert spec.trust.range_rules[0].max_value == 10_000_000.0


class TestParseTrustChange:
    """Change rule with different time periods."""

    def test_change_month(self):
        spec = parse_metric_string(_FULL_METRIC)
        assert spec.trust is not None
        assert len(spec.trust.change_rules) == 1
        assert spec.trust.change_rules[0].max_change_percentage == 50.0
        assert spec.trust.change_rules[0].period == "month"

    def test_change_day(self):
        text = dedent("""\
            Metric: Daily Metric
            Source: events
            Given all records from events table
            When we calculate
              Then count the rows
            The result is "Daily Metric"
            Trust:
              Value must not change more than 20% day over day
        """)
        spec = parse_metric_string(text)
        assert spec.trust is not None
        assert spec.trust.change_rules[0].period == "day"

    def test_change_week(self):
        text = dedent("""\
            Metric: Weekly Metric
            Source: events
            Given all records from events table
            When we calculate
              Then count the rows
            The result is "Weekly Metric"
            Trust:
              Value must not change more than 35% week over week
        """)
        spec = parse_metric_string(text)
        assert spec.trust is not None
        assert spec.trust.change_rules[0].period == "week"
        assert spec.trust.change_rules[0].max_change_percentage == 35.0


# ---------------------------------------------------------------------------
# File parsing
# ---------------------------------------------------------------------------


class TestParseFile:
    """Test parse_metric_file from disk."""

    def test_parse_from_fixture(self):
        fixture_path = Path(__file__).parent / "test_fixtures" / "valid_metric.metric"
        spec = parse_metric_file(fixture_path)
        assert spec.name == "Monthly Recurring Revenue"
        assert spec.trust is not None
        assert spec.trust.freshness is not None
        assert spec.trust.freshness.max_hours == 12.0

    def test_parse_from_tmp(self, sample_metric_file: Path):
        spec = parse_metric_file(sample_metric_file)
        assert spec.name == "Test Revenue"


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestMissingHeaderError:
    """Should raise MissingHeaderError when file lacks the Metric: line."""

    def test_raises_on_missing_header(self):
        bad_text = dedent("""\
            Description: No metric header here
            Source: orders
            Given all records
            When we calculate
              Then count rows
            The result is "Broken"
        """)
        with pytest.raises(MissingHeaderError):
            parse_metric_string(bad_text)

    def test_raises_on_empty_input(self):
        with pytest.raises(MissingHeaderError):
            parse_metric_string("")

    def test_raises_from_invalid_fixture_file(self):
        fixture_path = Path(__file__).parent / "test_fixtures" / "invalid_metric.metric"
        with pytest.raises(MissingHeaderError):
            parse_metric_file(fixture_path)


class TestInvalidTrustRuleError:
    """Should raise InvalidTrustRuleError for malformed trust rules."""

    def test_raises_on_gibberish_trust_rule(self):
        bad_text = dedent("""\
            Metric: Bad Trust
            Source: orders
            Given all records from orders table
            When we calculate
              Then count rows
            The result is "Bad Trust"
            Trust:
              This is not a valid trust rule at all
        """)
        with pytest.raises(InvalidTrustRuleError):
            parse_metric_string(bad_text)

    def test_raises_on_incomplete_freshness(self):
        bad_text = dedent("""\
            Metric: Bad Freshness
            Source: orders
            Given all records from orders table
            When we calculate
              Then count rows
            The result is "Bad Freshness"
            Trust:
              Freshness must be
        """)
        with pytest.raises(InvalidTrustRuleError):
            parse_metric_string(bad_text)
