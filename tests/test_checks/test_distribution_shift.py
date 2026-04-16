"""Tests for the distribution-shift trust check."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from litmus.checks.distribution_shift import check_distribution_shift
from litmus.checks.history import HistoryStore
from litmus.checks.runner import CheckStatus
from litmus.spec.metric_spec import DistributionShiftRule


@pytest.fixture()
def store(tmp_path: Path):
    s = HistoryStore(path=tmp_path / "hist.db")
    s.connect()
    yield s
    s.close()


def test_passes_when_history_disabled():
    rule = DistributionShiftRule(column="amount", max_change_percentage=20.0, period="week")
    result = check_distribution_shift(rule, "Revenue", current_mean=100.0, history=None)
    assert result.status == CheckStatus.PASSED
    assert "history store disabled" in result.message


def test_errors_on_null_current_mean(store):
    rule = DistributionShiftRule(column="amount", max_change_percentage=20.0, period="week")
    result = check_distribution_shift(rule, "Revenue", current_mean=None, history=store)
    assert result.status == CheckStatus.ERROR


def test_passes_on_first_run(store):
    rule = DistributionShiftRule(column="amount", max_change_percentage=20.0, period="week")
    result = check_distribution_shift(rule, "Revenue", current_mean=100.0, history=store)
    assert result.status == CheckStatus.PASSED
    assert "warming up" in result.message


def test_passes_within_threshold(store):
    now = datetime.now(timezone.utc)
    store.record(
        "Revenue",
        value_sum=None,
        row_count=None,
        recorded_at=now - timedelta(days=40),
        column_means={"amount": 100.0},
    )
    rule = DistributionShiftRule(column="amount", max_change_percentage=20.0, period="month")
    result = check_distribution_shift(rule, "Revenue", current_mean=105.0, history=store)
    assert result.status == CheckStatus.PASSED


def test_warns_in_margin(store):
    now = datetime.now(timezone.utc)
    store.record(
        "Revenue",
        value_sum=None,
        row_count=None,
        recorded_at=now - timedelta(days=40),
        column_means={"amount": 100.0},
    )
    rule = DistributionShiftRule(column="amount", max_change_percentage=20.0, period="month")
    # 19% shift: above 0.9 * 20 = 18 → WARNING
    result = check_distribution_shift(rule, "Revenue", current_mean=119.0, history=store)
    assert result.status == CheckStatus.WARNING


def test_fails_on_big_shift(store):
    now = datetime.now(timezone.utc)
    store.record(
        "Revenue",
        value_sum=None,
        row_count=None,
        recorded_at=now - timedelta(days=40),
        column_means={"amount": 100.0},
    )
    rule = DistributionShiftRule(column="amount", max_change_percentage=20.0, period="month")
    result = check_distribution_shift(rule, "Revenue", current_mean=200.0, history=store)
    assert result.status == CheckStatus.FAILED
    assert result.actual_value == 100.0


def test_handles_zero_prior_mean(store):
    now = datetime.now(timezone.utc)
    store.record(
        "Revenue",
        value_sum=None,
        row_count=None,
        recorded_at=now - timedelta(days=40),
        column_means={"amount": 0.0},
    )
    rule = DistributionShiftRule(column="amount", max_change_percentage=20.0, period="month")
    result = check_distribution_shift(rule, "Revenue", current_mean=50.0, history=store)
    assert result.status == CheckStatus.WARNING
    assert "can't compute" in result.message


def test_missing_column_in_history_is_warming_up(store):
    """Prior record exists but doesn't have a mean for the rule's column."""
    now = datetime.now(timezone.utc)
    store.record(
        "Revenue",
        value_sum=None,
        row_count=None,
        recorded_at=now - timedelta(days=40),
        column_means={"refund": 10.0},  # different column
    )
    rule = DistributionShiftRule(column="amount", max_change_percentage=20.0, period="month")
    result = check_distribution_shift(rule, "Revenue", current_mean=100.0, history=store)
    assert result.status == CheckStatus.PASSED
    assert "warming up" in result.message


def test_unknown_period_errors(store):
    rule = DistributionShiftRule(
        column="amount", max_change_percentage=20.0, period="fortnight"
    )
    result = check_distribution_shift(rule, "Revenue", current_mean=100.0, history=store)
    assert result.status == CheckStatus.ERROR
