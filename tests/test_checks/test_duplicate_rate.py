"""Tests for the duplicate-rate trust check."""

from __future__ import annotations

import duckdb
import pytest

from litmus.checks.duplicate_rate import check_duplicate_rate
from litmus.checks.runner import CheckStatus
from litmus.connectors.duckdb import DuckDBConnector
from litmus.spec.metric_spec import DuplicateRule


@pytest.fixture()
def dup_db():
    conn = duckdb.connect(":memory:")
    conn.execute(
        "CREATE TABLE events (id INTEGER, email VARCHAR);"
    )
    # 5 rows, 4 distinct emails → 1 duplicate → 20%
    conn.execute(
        "INSERT INTO events VALUES "
        "(1, 'a@x'), (2, 'b@x'), (3, 'c@x'), (4, 'd@x'), (5, 'a@x');"
    )
    yield conn
    conn.close()


def test_duplicate_rate_passes(dup_db):
    connector = DuckDBConnector(connection=dup_db)
    # 20% duplicates, threshold 50% → PASSED (well below 0.9 * 50)
    rule = DuplicateRule(column="email", max_percentage=50.0)
    result = check_duplicate_rate(connector, "events", rule)
    assert result.status == CheckStatus.PASSED
    assert result.actual_value == 20.0


def test_duplicate_rate_warns(dup_db):
    connector = DuckDBConnector(connection=dup_db)
    # 20% duplicates, threshold 22% → 20 > 22 * 0.9 = 19.8 → WARNING
    rule = DuplicateRule(column="email", max_percentage=22.0)
    result = check_duplicate_rate(connector, "events", rule)
    assert result.status == CheckStatus.WARNING


def test_duplicate_rate_fails(dup_db):
    connector = DuckDBConnector(connection=dup_db)
    rule = DuplicateRule(column="email", max_percentage=5.0)
    result = check_duplicate_rate(connector, "events", rule)
    assert result.status == CheckStatus.FAILED
    assert result.actual_value == 20.0


def test_duplicate_rate_zero_threshold_on_unique_column(dup_db):
    connector = DuckDBConnector(connection=dup_db)
    # id column is globally unique
    rule = DuplicateRule(column="id", max_percentage=0.0)
    result = check_duplicate_rate(connector, "events", rule)
    assert result.status == CheckStatus.PASSED
    assert result.actual_value == 0.0


def test_duplicate_rate_zero_threshold_on_duped_column(dup_db):
    connector = DuckDBConnector(connection=dup_db)
    rule = DuplicateRule(column="email", max_percentage=0.0)
    result = check_duplicate_rate(connector, "events", rule)
    assert result.status == CheckStatus.FAILED


def test_duplicate_rate_empty_table():
    conn = duckdb.connect(":memory:")
    conn.execute("CREATE TABLE empty_t (id INTEGER);")
    connector = DuckDBConnector(connection=conn)
    rule = DuplicateRule(column="id", max_percentage=5.0)
    result = check_duplicate_rate(connector, "empty_t", rule)
    # Empty table = 0 dupes = PASSED
    assert result.status == CheckStatus.PASSED
    assert result.actual_value == 0.0
    conn.close()


def test_duplicate_rate_errors_on_missing_column(dup_db):
    connector = DuckDBConnector(connection=dup_db)
    rule = DuplicateRule(column="nope", max_percentage=5.0)
    result = check_duplicate_rate(connector, "events", rule)
    assert result.status == CheckStatus.ERROR
