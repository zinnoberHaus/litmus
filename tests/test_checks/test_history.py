"""Tests for the SQLite-backed history store + change-rule integration."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from litmus.checks.change import check_change
from litmus.checks.history import HistoryStore
from litmus.checks.runner import CheckStatus
from litmus.spec.metric_spec import ChangeRule


@pytest.fixture()
def store(tmp_path: Path) -> HistoryStore:
    s = HistoryStore(path=tmp_path / "history.db")
    s.connect()
    yield s
    s.close()


def test_record_and_retrieve(store: HistoryStore):
    store.record("Revenue", value_sum=1000.0, row_count=10)
    last = store.last_record("Revenue")
    assert last is not None
    assert last.value_sum == 1000.0
    assert last.row_count == 10


def test_previous_record_respects_period(store: HistoryStore):
    now = datetime.now(timezone.utc)
    store.record("Revenue", value_sum=1000.0, row_count=10, recorded_at=now - timedelta(days=40))
    store.record("Revenue", value_sum=1100.0, row_count=11, recorded_at=now - timedelta(days=5))
    store.record("Revenue", value_sum=1200.0, row_count=12, recorded_at=now - timedelta(hours=1))

    # One month ago = 30 days. Only the 40-day-old row qualifies.
    prior = store.previous_record("Revenue", "month", now=now)
    assert prior is not None
    assert prior.value_sum == 1000.0

    # One week ago = 7 days. The 40-day and 5-day rows qualify; latest wins.
    # Actually 5 days < 7 days, so only 40d qualifies.
    prior_week = store.previous_record("Revenue", "week", now=now)
    assert prior_week is not None
    assert prior_week.value_sum == 1000.0

    # One day ago: 40-day and 5-day both qualify; latest wins.
    prior_day = store.previous_record("Revenue", "day", now=now)
    assert prior_day is not None
    assert prior_day.value_sum == 1100.0


def test_previous_record_none_if_empty(store: HistoryStore):
    assert store.previous_record("Never-Seen", "month") is None


def test_unknown_period_raises(store: HistoryStore):
    with pytest.raises(ValueError, match="Unknown period"):
        store.previous_record("Revenue", "fortnight")


def test_purge_single_metric(store: HistoryStore):
    store.record("A", 1.0, 1)
    store.record("A", 2.0, 2)
    store.record("B", 3.0, 3)
    deleted = store.purge("A")
    assert deleted == 2
    assert store.last_record("A") is None
    assert store.last_record("B") is not None


def test_purge_all(store: HistoryStore):
    store.record("A", 1.0, 1)
    store.record("B", 2.0, 2)
    assert store.purge() == 2
    assert store.last_record("A") is None


def test_store_persists_across_connections(tmp_path: Path):
    path = tmp_path / "history.db"
    s1 = HistoryStore(path=path)
    s1.connect()
    s1.record("X", 42.0, 7)
    s1.close()

    s2 = HistoryStore(path=path)
    s2.connect()
    try:
        last = s2.last_record("X")
        assert last is not None
        assert last.value_sum == 42.0
        assert last.row_count == 7
    finally:
        s2.close()


def test_check_change_passes_when_no_history(store: HistoryStore):
    rule = ChangeRule(max_change_percentage=30.0, period="month")
    result = check_change(rule, "Revenue", current_value=1000.0, history=store)
    assert result.status == CheckStatus.PASSED
    assert "warming up" in result.message


def test_check_change_passes_when_history_none():
    rule = ChangeRule(max_change_percentage=30.0, period="month")
    result = check_change(rule, "Revenue", current_value=1000.0, history=None)
    assert result.status == CheckStatus.PASSED
    assert "history store disabled" in result.message


def test_check_change_detects_violation(store: HistoryStore):
    now = datetime.now(timezone.utc)
    # Record a value from 40 days ago so "month" period can find it.
    store.record("Revenue", value_sum=1000.0, row_count=10, recorded_at=now - timedelta(days=40))
    rule = ChangeRule(max_change_percentage=30.0, period="month")
    # Current value is 2000 (100% increase), threshold 30%.
    result = check_change(rule, "Revenue", current_value=2000.0, history=store)
    assert result.status == CheckStatus.FAILED
    assert result.actual_value == 100.0


def test_check_change_warns_in_margin(store: HistoryStore):
    now = datetime.now(timezone.utc)
    store.record("Revenue", value_sum=1000.0, row_count=10, recorded_at=now - timedelta(days=40))
    rule = ChangeRule(max_change_percentage=30.0, period="month")
    # 28% change: above 0.9 * 30 = 27 → WARNING band (27..30]
    result = check_change(rule, "Revenue", current_value=1280.0, history=store)
    assert result.status == CheckStatus.WARNING


def test_check_change_passes_within_threshold(store: HistoryStore):
    now = datetime.now(timezone.utc)
    store.record("Revenue", value_sum=1000.0, row_count=10, recorded_at=now - timedelta(days=40))
    rule = ChangeRule(max_change_percentage=30.0, period="month")
    result = check_change(rule, "Revenue", current_value=1050.0, history=store)  # +5%
    assert result.status == CheckStatus.PASSED


def test_check_change_errors_on_null_current(store: HistoryStore):
    rule = ChangeRule(max_change_percentage=30.0, period="month")
    result = check_change(rule, "Revenue", current_value=None, history=store)
    assert result.status == CheckStatus.ERROR


def test_check_change_handles_zero_prior(store: HistoryStore):
    now = datetime.now(timezone.utc)
    store.record("Revenue", value_sum=0.0, row_count=0, recorded_at=now - timedelta(days=40))
    rule = ChangeRule(max_change_percentage=30.0, period="month")
    result = check_change(rule, "Revenue", current_value=100.0, history=store)
    assert result.status == CheckStatus.WARNING
    assert "can't compute" in result.message


def test_runner_records_history_on_each_run(tmp_path: Path, test_db):
    """Full integration: run_checks() writes one row per metric per run."""
    from litmus.checks.runner import run_checks
    from litmus.connectors.duckdb import DuckDBConnector
    from litmus.spec.metric_spec import ChangeRule, MetricSpec, RangeRule, TrustSpec

    spec = MetricSpec(
        name="Test Revenue",
        sources=["orders"],
        trust=TrustSpec(
            range_rules=[RangeRule(min_value=0, max_value=1_000_000)],
            change_rules=[ChangeRule(max_change_percentage=50.0, period="month")],
        ),
    )
    connector = DuckDBConnector(connection=test_db)
    connector.connect()  # no-op; connection already open

    hist = HistoryStore(path=tmp_path / "hist.db")
    hist.connect()
    try:
        run_checks(connector, spec, history=hist, run_id="r1", commit_sha="abc123")
        run_checks(connector, spec, history=hist, run_id="r2", commit_sha="def456")

        records = hist.all_records("Test Revenue")
        assert len(records) == 2
        assert records[0].run_id == "r1"
        assert records[1].run_id == "r2"
        assert records[0].commit_sha == "abc123"
        assert records[1].value_sum is not None
        assert records[1].row_count == 5  # from the seed fixture
    finally:
        hist.close()
        connector.close()


def test_env_var_history_path(monkeypatch, tmp_path: Path):
    """LITMUS_HISTORY_DB env var overrides the default path."""
    import importlib

    target = tmp_path / "from_env.db"
    monkeypatch.setenv("LITMUS_HISTORY_DB", str(target))
    # Re-import the module so DEFAULT_HISTORY_PATH picks up the env var.
    import litmus.checks.history as history_mod

    importlib.reload(history_mod)
    try:
        assert history_mod.DEFAULT_HISTORY_PATH == target
        s = history_mod.HistoryStore()
        s.connect()
        s.record("EnvMetric", 1.0, 1)
        s.close()
        assert target.exists()
    finally:
        # Restore default state for other tests.
        monkeypatch.delenv("LITMUS_HISTORY_DB", raising=False)
        importlib.reload(history_mod)
