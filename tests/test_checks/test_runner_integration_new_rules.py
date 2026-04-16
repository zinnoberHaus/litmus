"""End-to-end: run_checks dispatches the three new rule types through the full flow."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from litmus.checks.history import HistoryStore
from litmus.checks.runner import CheckStatus, run_checks
from litmus.connectors.duckdb import DuckDBConnector
from litmus.spec.metric_spec import (
    DistributionShiftRule,
    DuplicateRule,
    MetricSpec,
    SchemaDriftRule,
    TrustSpec,
)


def _build_spec() -> MetricSpec:
    return MetricSpec(
        name="Integration Revenue",
        sources=["orders"],
        trust=TrustSpec(
            duplicate_rules=[DuplicateRule(column="order_id", max_percentage=0.0)],
            schema_drift=SchemaDriftRule(),
            distribution_shift_rules=[
                DistributionShiftRule(
                    column="amount",
                    max_change_percentage=20.0,
                    period="month",
                ),
            ],
        ),
    )


def test_first_run_passes_new_rules(tmp_path: Path, test_db):
    """Warming up: duplicate=PASSED, schema=PASSED, distribution=PASSED."""
    connector = DuckDBConnector(connection=test_db)
    hist = HistoryStore(path=tmp_path / "h.db")
    hist.connect()
    try:
        suite = run_checks(connector, _build_spec(), history=hist)
        statuses = {r.name: r.status for r in suite.results}
        # All three new checks should be in the suite
        assert "Duplicate rate on order_id" in statuses
        assert "Schema drift" in statuses
        assert any(name.startswith("Month-over-month mean shift") for name in statuses)
        # Duplicates: order_id is unique in fixture → PASSED
        assert statuses["Duplicate rate on order_id"] == CheckStatus.PASSED
        # Schema drift: first run → PASSED (warming up)
        assert statuses["Schema drift"] == CheckStatus.PASSED
        # Distribution shift: no prior → PASSED
        shift_status = next(
            s for name, s in statuses.items() if name.startswith("Month-over-month mean shift")
        )
        assert shift_status == CheckStatus.PASSED
    finally:
        hist.close()


def test_schema_drift_fails_on_column_removal(tmp_path: Path, test_db):
    """After a run, drop a column and re-run — schema_drift should FAIL."""
    connector = DuckDBConnector(connection=test_db)
    hist = HistoryStore(path=tmp_path / "h.db")
    hist.connect()
    try:
        # First run: records schema
        run_checks(connector, _build_spec(), history=hist)
        # Mutate schema: drop refund column
        test_db.execute("ALTER TABLE orders DROP COLUMN refund")
        # Second run should catch the drift
        suite = run_checks(connector, _build_spec(), history=hist)
        drift = next(r for r in suite.results if r.name == "Schema drift")
        assert drift.status == CheckStatus.FAILED
        assert "refund" in drift.message
    finally:
        hist.close()


def test_distribution_shift_fires_on_mean_change(tmp_path: Path, test_db):
    """Seed history 40 days ago with a low mean, then run against the fixture."""
    connector = DuckDBConnector(connection=test_db)
    hist = HistoryStore(path=tmp_path / "h.db")
    hist.connect()
    try:
        # Seed history with a much lower mean one month ago
        hist.record(
            "Integration Revenue",
            value_sum=100.0,
            row_count=4,
            recorded_at=datetime.now(timezone.utc) - timedelta(days=40),
            column_means={"amount": 10.0},  # fixture mean is ~231 → huge shift
        )
        suite = run_checks(connector, _build_spec(), history=hist)
        shift = next(
            r for r in suite.results if r.name.startswith("Month-over-month mean shift")
        )
        assert shift.status == CheckStatus.FAILED
    finally:
        hist.close()


def test_duplicate_rule_fails_on_duped_table(tmp_path: Path):
    import duckdb

    conn = duckdb.connect(":memory:")
    conn.execute("CREATE TABLE orders (order_id INTEGER, amount DOUBLE);")
    conn.execute(
        "INSERT INTO orders VALUES (1, 10), (1, 20), (2, 30), (2, 40), (3, 50);"
    )
    spec = MetricSpec(
        name="Duped",
        sources=["orders"],
        trust=TrustSpec(duplicate_rules=[DuplicateRule(column="order_id", max_percentage=0.0)]),
    )
    connector = DuckDBConnector(connection=conn)
    hist = HistoryStore(path=tmp_path / "h.db")
    hist.connect()
    try:
        suite = run_checks(connector, spec, history=hist)
        dup = next(r for r in suite.results if r.name == "Duplicate rate on order_id")
        assert dup.status == CheckStatus.FAILED
    finally:
        hist.close()
        conn.close()
