"""Shared pytest fixtures for the Litmus test suite."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import duckdb
import pytest

# ---------------------------------------------------------------------------
# Sample .metric text used by multiple test modules
# ---------------------------------------------------------------------------

SAMPLE_METRIC_TEXT = dedent("""\
    Metric: Test Revenue
    Description: Total revenue from completed orders
    Owner: data-team
    Tags: finance, revenue

    Source: orders

    Given all records from orders table
      And status is "completed"
      And order_date is within current calendar month

    When we calculate
      Then sum the amount column
      And round to 2 decimal places

    The result is "Test Revenue"

    Trust:
      Freshness must be less than 24 hours
      Null rate on amount must be less than 5%
      Row count must not drop more than 25% day over day
      Value must be between 0 and 1,000,000
      Value must not change more than 50% month over month
""")


@pytest.fixture()
def test_db():
    """In-memory DuckDB with a sample ``orders`` table.

    Schema:
        order_id   INTEGER
        amount     DOUBLE   (one row is NULL)
        refund     DOUBLE
        status     VARCHAR
        order_date DATE
        updated_at TIMESTAMP
    """
    conn = duckdb.connect(":memory:")
    conn.execute("""
        CREATE TABLE orders (
            order_id   INTEGER,
            amount     DOUBLE,
            refund     DOUBLE,
            status     VARCHAR,
            order_date DATE,
            updated_at TIMESTAMP
        );
    """)
    conn.execute("""
        INSERT INTO orders VALUES
            (1, 100.00, 0.00,  'completed', '2026-04-01', CURRENT_TIMESTAMP),
            (2, 250.50, 10.00, 'completed', '2026-04-02', CURRENT_TIMESTAMP),
            (3, NULL,   0.00,  'pending',   '2026-04-03', CURRENT_TIMESTAMP),
            (4, 75.25,  5.00,  'completed', '2026-04-04', CURRENT_TIMESTAMP),
            (5, 500.00, 0.00,  'refunded',  '2026-04-05', CURRENT_TIMESTAMP);
    """)
    yield conn
    conn.close()


@pytest.fixture()
def sample_metric_text() -> str:
    """Return a valid .metric file string for Test Revenue."""
    return SAMPLE_METRIC_TEXT


@pytest.fixture()
def sample_metric_file(tmp_path: Path, sample_metric_text: str) -> Path:
    """Write the sample metric text to a temp file and return the path."""
    metric_path = tmp_path / "test_revenue.metric"
    metric_path.write_text(sample_metric_text, encoding="utf-8")
    return metric_path
