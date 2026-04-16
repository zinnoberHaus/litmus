"""Tests for litmus.generators.share_html — single-file HTML artefact."""

from __future__ import annotations

import pytest

from litmus.checks.runner import CheckResult, CheckStatus, CheckSuite
from litmus.generators.share_html import generate_share_html
from litmus.parser.parser import parse_metric_string
from litmus.spec.metric_spec import (
    DuplicateRule,
    FreshnessRule,
    MetricSpec,
    NullRule,
    RangeRule,
    SchemaDriftRule,
    TrustSpec,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _simple_spec() -> MetricSpec:
    return MetricSpec(
        name="Monthly Revenue",
        description="Total revenue for the current calendar month.",
        owner="finance-analytics",
        tags=["revenue", "finance"],
        sources=["invoices"],
        conditions=['status is "completed"'],
        calculations=["sum the net_amount column"],
        result_name="Monthly Revenue",
        trust=TrustSpec(
            freshness=FreshnessRule(max_hours=6),
            null_rules=[NullRule(column="currency", max_percentage=0)],
            duplicate_rules=[DuplicateRule(column="invoice_id", max_percentage=0)],
            range_rules=[RangeRule(min_value=10000, max_value=5_000_000)],
            schema_drift=SchemaDriftRule(),
        ),
    )


def _passing_suite(spec: MetricSpec) -> CheckSuite:
    suite = CheckSuite(metric_name=spec.name)
    # Same number + order of checks as _rule_labels
    suite.results.extend([
        CheckResult(
            name="freshness",
            status=CheckStatus.PASSED,
            message="Data is 1.2h old (limit: 6h).",
            actual_value=1.2,
            threshold=6,
        ),
        CheckResult(
            name="null_rate:currency",
            status=CheckStatus.PASSED,
            message="0% nulls on currency.",
            actual_value=0.0,
            threshold=0.0,
        ),
        CheckResult(
            name="value_range",
            status=CheckStatus.PASSED,
            message="Value 42,300 within [10000, 5000000].",
            actual_value=42300,
            threshold=(10000, 5_000_000),
        ),
        CheckResult(
            name="duplicate_rate:invoice_id",
            status=CheckStatus.PASSED,
            message="0% duplicates on invoice_id.",
            actual_value=0.0,
            threshold=0.0,
        ),
        CheckResult(
            name="schema_drift",
            status=CheckStatus.PASSED,
            message="Columns unchanged.",
            actual_value="unchanged",
            threshold=None,
        ),
    ])
    return suite


# ---------------------------------------------------------------------------
# Structural tests
# ---------------------------------------------------------------------------


class TestStructure:
    def test_is_valid_html5(self):
        html = generate_share_html(_simple_spec())
        assert html.startswith("<!DOCTYPE html>")
        assert '<html lang="en">' in html
        assert html.rstrip().endswith("</html>")

    def test_includes_metric_name_in_title_and_body(self):
        html = generate_share_html(_simple_spec())
        assert "<title>Monthly Revenue · Litmus</title>" in html
        assert "<h1>Monthly Revenue</h1>" in html

    def test_includes_description(self):
        html = generate_share_html(_simple_spec())
        assert "Total revenue for the current calendar month." in html

    def test_includes_owner_and_tags(self):
        html = generate_share_html(_simple_spec())
        assert "finance-analytics" in html
        assert "revenue" in html

    def test_renders_without_external_assets(self):
        """No <link>, no <script> — pure inline CSS + base64 logo."""
        html = generate_share_html(_simple_spec())
        assert "<link" not in html
        assert "<script" not in html
        # Logo is inlined via data URI, not http(s) or filesystem.
        assert 'src="data:image/' in html
        assert 'src="http' not in html
        assert 'src="/' not in html

    def test_inlines_styles(self):
        html = generate_share_html(_simple_spec())
        assert "<style>" in html
        assert "</style>" in html


# ---------------------------------------------------------------------------
# Given/When/Then rendering
# ---------------------------------------------------------------------------


class TestGivenWhenThen:
    def test_renders_given_conditions(self):
        html = generate_share_html(_simple_spec())
        assert "Given" in html
        assert "status is &quot;completed&quot;" in html

    def test_renders_calculations(self):
        html = generate_share_html(_simple_spec())
        assert "When we calculate" in html
        assert "sum the net_amount column" in html

    def test_renders_result(self):
        html = generate_share_html(_simple_spec())
        assert "Then the result is" in html
        assert "<strong>Monthly Revenue</strong>" in html

    def test_empty_metric_renders_safely(self):
        spec = MetricSpec(name="Placeholder")
        html = generate_share_html(spec)
        assert "<h1>Placeholder</h1>" in html
        # Empty trust block → explicit empty state, not a broken list.
        assert "No Trust rules defined yet" in html


# ---------------------------------------------------------------------------
# Trust checklist
# ---------------------------------------------------------------------------


class TestTrustChecklist:
    def test_pending_status_without_suite(self):
        html = generate_share_html(_simple_spec())
        assert "tick-pending" in html
        assert "Not yet checked" in html

    def test_pending_pill_in_header_without_suite(self):
        html = generate_share_html(_simple_spec())
        assert "pill-pending" in html

    def test_passing_status_with_green_suite(self):
        spec = _simple_spec()
        suite = _passing_suite(spec)
        html = generate_share_html(spec, suite)
        assert "tick-ok" in html
        assert "pill-ok" in html
        assert "Healthy" in html

    def test_warning_status_renders_yellow(self):
        spec = _simple_spec()
        suite = CheckSuite(metric_name=spec.name)
        # Only one trust rule for simplicity.
        spec.trust = TrustSpec(freshness=FreshnessRule(max_hours=6))
        suite.results.append(CheckResult(
            name="freshness",
            status=CheckStatus.WARNING,
            message="Data is 5.7h old, close to 6h limit.",
            actual_value=5.7,
            threshold=6,
        ))
        html = generate_share_html(spec, suite)
        assert "tick-warn" in html
        assert "pill-warn" in html
        assert "Warnings" in html

    def test_failing_status_renders_red(self):
        spec = _simple_spec()
        suite = CheckSuite(metric_name=spec.name)
        spec.trust = TrustSpec(freshness=FreshnessRule(max_hours=6))
        suite.results.append(CheckResult(
            name="freshness",
            status=CheckStatus.FAILED,
            message="Data is 12h old — stale.",
            actual_value=12,
            threshold=6,
        ))
        html = generate_share_html(spec, suite)
        assert "tick-fail" in html
        assert "pill-fail" in html
        assert "Failing" in html

    def test_error_renders_as_fail_visual(self):
        spec = _simple_spec()
        suite = CheckSuite(metric_name=spec.name)
        spec.trust = TrustSpec(freshness=FreshnessRule(max_hours=6))
        suite.results.append(CheckResult(
            name="freshness",
            status=CheckStatus.ERROR,
            message="Connector failed.",
            actual_value=None,
            threshold=6,
        ))
        html = generate_share_html(spec, suite)
        assert "tick-fail" in html  # ERROR reuses fail styling
        assert "Error" in html

    def test_mismatched_suite_falls_back_to_pending(self):
        """If the suite has a different count of results, don't lie — show pending."""
        spec = _simple_spec()
        suite = CheckSuite(metric_name=spec.name)
        suite.results.append(CheckResult(
            name="freshness",
            status=CheckStatus.PASSED,
            message="OK",
            actual_value=1,
            threshold=6,
        ))
        # suite has 1 result, spec has 5 rules → mismatch
        html = generate_share_html(spec, suite)
        assert "tick-pending" in html
        assert "Latest run did not include this rule" in html

    def test_renders_human_labels_not_raw_rule_names(self):
        html = generate_share_html(_simple_spec())
        # Human phrasing, not raw rule identifiers.
        assert "Data is no more than 6 hours old" in html
        assert "No currency values are missing" in html
        assert "No invoice_id values are duplicated" in html
        assert "Value stays between 10,000 and 5,000,000" in html
        # Apostrophe is HTML-escaped by ``html.escape(..., quote=True)``.
        assert "Column list hasn&#x27;t changed since the last run" in html


# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------


class TestFooter:
    def test_includes_last_updated(self):
        html = generate_share_html(_simple_spec())
        assert "Last updated" in html
        assert "UTC" in html

    def test_commit_sha_from_github_env(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("GITHUB_SHA", "deadbeef1234567890")
        html = generate_share_html(_simple_spec())
        assert "Commit deadbee" in html  # truncated to 7 chars

    def test_commit_sha_from_litmus_env(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("GITHUB_SHA", raising=False)
        monkeypatch.setenv("LITMUS_COMMIT_SHA", "abcdef01234567")
        html = generate_share_html(_simple_spec())
        assert "Commit abcdef0" in html

    def test_no_commit_section_when_env_unset(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.delenv("GITHUB_SHA", raising=False)
        monkeypatch.delenv("LITMUS_COMMIT_SHA", raising=False)
        html = generate_share_html(_simple_spec())
        assert "Commit " not in html

    def test_litmus_attribution(self):
        html = generate_share_html(_simple_spec())
        assert "Generated by" in html
        assert "Litmus" in html


# ---------------------------------------------------------------------------
# HTML-escape safety
# ---------------------------------------------------------------------------


class TestEscaping:
    def test_escapes_hostile_metric_name(self):
        spec = MetricSpec(name="<script>alert(1)</script>")
        html = generate_share_html(spec)
        assert "<script>alert" not in html
        assert "&lt;script&gt;alert" in html

    def test_escapes_condition_quotes(self):
        spec = MetricSpec(
            name="Escape Test",
            conditions=['status == "x"'],
        )
        html = generate_share_html(spec)
        assert 'status == &quot;x&quot;' in html


# ---------------------------------------------------------------------------
# End-to-end round-trip through the parser
# ---------------------------------------------------------------------------


_REVENUE_METRIC = """\
Metric: Monthly Revenue
Description: Total revenue for the current calendar month.
Owner: finance-analytics
Tags: revenue, finance

Source: invoices

Given the invoice has been finalized

When we calculate
  Then sum the net_amount column

The result is "Monthly Revenue"

Trust:
  Freshness must be less than 6 hours
  Null rate on currency must be less than 0%
  Duplicate rate on invoice_id must be 0%
  Value must be between 10000 and 5000000
"""


class TestRealParserRoundTrip:
    def test_parses_and_renders(self):
        spec = parse_metric_string(_REVENUE_METRIC)
        html = generate_share_html(spec)
        assert "<h1>Monthly Revenue</h1>" in html
        assert "No currency values are missing" in html
        assert "Data is no more than 6 hours old" in html
        assert "Value stays between 10,000 and 5,000,000" in html
