"""Tests for litmus.reporters.console — Rich-based CLI output."""

from __future__ import annotations

from io import StringIO

from rich.console import Console

from litmus.checks.runner import CheckResult, CheckStatus, CheckSuite
from litmus.reporters.console import report_summary, report_verbose
from litmus.spec.metric_spec import (
    FreshnessRule,
    MetricSpec,
    NullRule,
    TrustSpec,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_spec_and_suite() -> tuple[MetricSpec, CheckSuite]:
    """Build a sample MetricSpec + CheckSuite pair for testing reporters."""
    spec = MetricSpec(
        name="Test Revenue",
        description="Total revenue from completed orders",
        owner="data-team",
        tags=["finance"],
        sources=["orders"],
        conditions=["all records from orders"],
        calculations=["sum the amount column"],
        result_name="Test Revenue",
        trust=TrustSpec(
            freshness=FreshnessRule(max_hours=24),
            null_rules=[NullRule(column="amount", max_percentage=5.0)],
        ),
    )
    suite = CheckSuite(metric_name="Test Revenue")
    suite.results.append(
        CheckResult(
            name="Freshness",
            status=CheckStatus.PASSED,
            message="2.3 hours ago (threshold: < 24 hours)",
            actual_value=2.3,
            threshold=24,
        )
    )
    suite.results.append(
        CheckResult(
            name="Null rate on amount",
            status=CheckStatus.PASSED,
            message="0.0% (threshold: < 5%)",
            actual_value=0.0,
            threshold=5.0,
        )
    )
    return spec, suite


def _capture_output(report_fn, specs_and_suites) -> str:
    """Run a report function and capture the text output."""
    buf = StringIO()
    con = Console(file=buf, width=120, force_terminal=False, no_color=True, highlight=False)
    report_fn(con, specs_and_suites)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestReportVerbose:
    """report_verbose should run without errors and contain expected content."""

    def test_runs_without_error(self):
        spec, suite = _make_spec_and_suite()
        # Should not raise
        output = _capture_output(report_verbose, [(spec, suite)])
        assert output  # non-empty

    def test_contains_metric_name(self):
        spec, suite = _make_spec_and_suite()
        output = _capture_output(report_verbose, [(spec, suite)])
        assert "Test Revenue" in output

    def test_contains_check_results(self):
        spec, suite = _make_spec_and_suite()
        output = _capture_output(report_verbose, [(spec, suite)])
        assert "Freshness" in output
        assert "Null rate" in output

    def test_contains_trust_score(self):
        spec, suite = _make_spec_and_suite()
        output = _capture_output(report_verbose, [(spec, suite)])
        assert "Trust Score" in output

    def test_contains_footer(self):
        spec, suite = _make_spec_and_suite()
        output = _capture_output(report_verbose, [(spec, suite)])
        assert "1 metric checked" in output


class TestReportSummary:
    """report_summary should run without errors and contain expected content."""

    def test_runs_without_error(self):
        spec, suite = _make_spec_and_suite()
        output = _capture_output(report_summary, [(spec, suite)])
        assert output  # non-empty

    def test_contains_metric_name(self):
        spec, suite = _make_spec_and_suite()
        output = _capture_output(report_summary, [(spec, suite)])
        assert "Test Revenue" in output

    def test_contains_score(self):
        spec, suite = _make_spec_and_suite()
        output = _capture_output(report_summary, [(spec, suite)])
        assert "2/2" in output

    def test_multiple_metrics_shows_run_message(self):
        pairs = [_make_spec_and_suite(), _make_spec_and_suite()]
        output = _capture_output(report_summary, pairs)
        assert "Run with --verbose for details" in output


class TestReportWithFailures:
    """Reports containing failed checks still render correctly."""

    def test_verbose_with_failure(self):
        spec, suite = _make_spec_and_suite()
        suite.results.append(
            CheckResult(
                name="Value range",
                status=CheckStatus.FAILED,
                message="15,000 (range: 0 - 10,000)",
                actual_value=15000,
                threshold="0 - 10000",
            )
        )
        output = _capture_output(report_verbose, [(spec, suite)])
        assert "FAILED" in output

    def test_summary_with_warning(self):
        spec, suite = _make_spec_and_suite()
        suite.results.append(
            CheckResult(
                name="Volume",
                status=CheckStatus.WARNING,
                message="-22% day-over-day",
                actual_value=-22.0,
                threshold=25.0,
            )
        )
        output = _capture_output(report_summary, [(spec, suite)])
        # Score should be 2.5/3 (two passes + one warning at 0.5)
        assert "2.5/3" in output
