"""Parser coverage for the three trust-rule grammars added in 2026-04."""

from __future__ import annotations

from textwrap import dedent

import pytest

from litmus.parser.errors import InvalidTrustRuleError
from litmus.parser.parser import parse_metric_string


def _wrap_trust(trust_body: str) -> str:
    """Return a minimal .metric with the given lines under Trust:."""
    return dedent(
        """\
        Metric: Example
        Source: orders
        Given all records from orders table
        When we calculate
          Then sum the amount column
        The result is "Example"

        Trust:
        """
    ) + "\n".join(f"  {line}" for line in trust_body.strip().splitlines()) + "\n"


class TestDuplicateRate:
    def test_parses_with_less_than(self):
        spec = parse_metric_string(_wrap_trust("Duplicate rate on order_id must be less than 1%"))
        assert len(spec.trust.duplicate_rules) == 1
        rule = spec.trust.duplicate_rules[0]
        assert rule.column == "order_id"
        assert rule.max_percentage == 1.0

    def test_parses_without_less_than(self):
        spec = parse_metric_string(_wrap_trust("Duplicate rate on email must be 0%"))
        rule = spec.trust.duplicate_rules[0]
        assert rule.column == "email"
        assert rule.max_percentage == 0.0

    def test_multiple_rules(self):
        spec = parse_metric_string(_wrap_trust(
            "Duplicate rate on order_id must be less than 1%\n"
            "Duplicate rate on customer_id must be less than 5%"
        ))
        assert len(spec.trust.duplicate_rules) == 2
        columns = [r.column for r in spec.trust.duplicate_rules]
        assert columns == ["order_id", "customer_id"]


class TestSchemaDrift:
    def test_schema_must_not_drift(self):
        spec = parse_metric_string(_wrap_trust("Schema must not drift"))
        assert spec.trust.schema_drift is not None

    def test_schema_must_not_change_is_alias(self):
        spec = parse_metric_string(_wrap_trust("Schema must not change"))
        assert spec.trust.schema_drift is not None

    def test_default_absent(self):
        spec = parse_metric_string(_wrap_trust("Null rate on amount must be less than 5%"))
        assert spec.trust.schema_drift is None


class TestDistributionShift:
    def test_week_over_week(self):
        spec = parse_metric_string(_wrap_trust(
            "Mean of amount must not shift more than 20% week over week"
        ))
        rules = spec.trust.distribution_shift_rules
        assert len(rules) == 1
        assert rules[0].column == "amount"
        assert rules[0].max_change_percentage == 20.0
        assert rules[0].period == "week"

    def test_change_is_alias(self):
        spec = parse_metric_string(_wrap_trust(
            "Mean of amount must not change more than 20% month over month"
        ))
        assert spec.trust.distribution_shift_rules[0].period == "month"

    def test_quarter_period(self):
        spec = parse_metric_string(_wrap_trust(
            "Mean of refund must not change more than 10% quarter over quarter"
        ))
        assert spec.trust.distribution_shift_rules[0].period == "quarter"

    def test_year_period(self):
        spec = parse_metric_string(_wrap_trust(
            "Mean of amount must not change more than 5% year over year"
        ))
        assert spec.trust.distribution_shift_rules[0].period == "year"

    def test_invalid_distribution_shift_rule_fails(self):
        # Missing period
        with pytest.raises(InvalidTrustRuleError):
            parse_metric_string(_wrap_trust(
                "Mean of amount must not change more than 20%"
            ))


class TestPlainEnglish:
    def test_explains_new_rules(self):
        from litmus.generators.plain_english import explain

        spec = parse_metric_string(_wrap_trust(
            "Duplicate rate on order_id must be less than 1%\n"
            "Schema must not drift\n"
            "Mean of amount must not change more than 20% week over week"
        ))
        text = explain(spec)
        assert "duplicated" in text
        assert "column list" in text
        assert "average amount" in text
