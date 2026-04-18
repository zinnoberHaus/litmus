"""End-to-end test for ``run_reconciliation`` with mocked BI connectors.

Two mappings:
- Looker → 2020.0 vs warehouse 2000.0 → +1% drift → PASS
- Tableau → 2300.0 vs warehouse 2000.0 → +15% drift → FAIL

A third case covers connector-level failures: a mapping whose connector
raises must not take down the other mappings, and its row is persisted with
``status="fail"`` so the UI can show "errored" next to healthy sources.
"""

from __future__ import annotations

from decimal import Decimal
from textwrap import dedent
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from litmus_api.bi.base import BIResult

_SPEC = dedent("""\
    Metric: Recon Job Demo
    Description: End-to-end reconciliation test
    Owner: data@example.com

    Source: orders

    Given all records from orders table

    When we calculate
      Then sum the amount column

    The result is "Recon Job Demo"

    Trust:
      Freshness must be less than 24 hours
""")


def _setup_metric_with_mappings(client: TestClient) -> dict:
    """Create a metric, seed a Run with ``value_sum=2000``, add two BI mappings."""
    r = client.post("/api/v1/metrics", json={"spec_text": _SPEC})
    assert r.status_code == 201
    metric = r.json()

    run_resp = client.post(
        "/api/v1/runs",
        json={
            "metric_id": metric["id"],
            "status": "passed",
            "trust_score": 1.0,
            "value_sum": 2000.0,
            "triggered_by": "test",
        },
    )
    assert run_resp.status_code == 201, run_resp.text

    for source, identifier in (
        ("looker", "ecommerce::orders.total_revenue"),
        ("tableau", "wb-1/view-abc/SUM(Sales)"),
    ):
        m = client.post(
            f"/api/v1/metrics/{metric['id']}/bi-mappings",
            json={"source": source, "identifier": identifier},
        )
        assert m.status_code == 201, m.text

    return metric


def _fake_connector(value: float, source: str) -> MagicMock:
    conn = MagicMock()
    conn.fetch_metric_value.return_value = BIResult(
        source=source,
        value=value,
        recorded_at=__import__("datetime").datetime.utcnow(),
        raw_metadata={},
    )
    return conn


def test_reconcile_two_mappings_bucket_correctly(client: TestClient) -> None:
    metric = _setup_metric_with_mappings(client)

    def _get(source: str):
        if source == "looker":
            return _fake_connector(2020.0, "looker")  # +1% → pass
        if source == "tableau":
            return _fake_connector(2300.0, "tableau")  # +15% → fail
        raise ValueError(source)

    with patch("litmus_api.jobs.reconciliation.get_connector", side_effect=_get):
        resp = client.post(f"/api/v1/metrics/{metric['id']}/reconcile")
    assert resp.status_code == 200, resp.text

    rows = {r["source"]: r for r in resp.json()}
    assert set(rows.keys()) == {"looker", "tableau"}
    assert rows["looker"]["status"] == "pass"
    assert rows["looker"]["value"] == 2020.0
    assert rows["looker"]["delta"] == 0.01
    assert rows["tableau"]["status"] == "fail"
    assert rows["tableau"]["value"] == 2300.0
    assert rows["tableau"]["delta"] == 0.15


def test_reconcile_rows_persist_and_surface_in_get(client: TestClient) -> None:
    metric = _setup_metric_with_mappings(client)

    def _get(source: str):
        if source == "looker":
            return _fake_connector(2040.0, "looker")  # +2% exactly → warn (>= 0.02)
        return _fake_connector(2000.0, "tableau")  # 0% → pass

    with patch("litmus_api.jobs.reconciliation.get_connector", side_effect=_get):
        client.post(f"/api/v1/metrics/{metric['id']}/reconcile")

    # GET should include warehouse + the two freshly-inserted rows.
    rows = client.get(f"/api/v1/metrics/{metric['id']}/reconciliation").json()
    sources = [r["source"] for r in rows]
    assert sources[0] == "warehouse"
    assert set(sources[1:]) == {"looker", "tableau"}


def test_connector_failure_is_isolated(client: TestClient) -> None:
    """A failing connector does NOT break the job — we still get a row for
    the healthy connector, and the errored one shows ``status="fail"`` plus
    the exception message in ``error``.
    """
    metric = _setup_metric_with_mappings(client)

    def _get(source: str):
        if source == "looker":
            broken = MagicMock()
            broken.fetch_metric_value.side_effect = RuntimeError("boom: api down")
            return broken
        return _fake_connector(2000.0, "tableau")

    with patch("litmus_api.jobs.reconciliation.get_connector", side_effect=_get):
        resp = client.post(f"/api/v1/metrics/{metric['id']}/reconcile")
    assert resp.status_code == 200, resp.text

    rows = {r["source"]: r for r in resp.json()}
    assert rows["looker"]["status"] == "fail"
    assert rows["looker"]["value"] == 0.0  # null → 0 in the response for compactness
    assert "boom: api down" in (rows["looker"].get("error") or "")
    # Tableau still ran and produced a pass row.
    assert rows["tableau"]["status"] == "pass"


def test_reconcile_with_no_warehouse_runs_returns_zero_delta(
    client: TestClient,
) -> None:
    """If the metric has no runs at all, delta is forced to 0 instead of
    attempting to divide by None/0. The row still gets ``pass``."""
    r = client.post("/api/v1/metrics", json={"spec_text": _SPEC})
    metric = r.json()
    client.post(
        f"/api/v1/metrics/{metric['id']}/bi-mappings",
        json={"source": "looker", "identifier": "ecommerce::orders.total_revenue"},
    )

    with patch(
        "litmus_api.jobs.reconciliation.get_connector",
        return_value=_fake_connector(4200.0, "looker"),
    ):
        resp = client.post(f"/api/v1/metrics/{metric['id']}/reconcile")
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["delta"] == 0.0
    assert rows[0]["status"] == "pass"


def test_reconcile_with_no_mappings_returns_empty_list(client: TestClient) -> None:
    """No mappings → the trigger endpoint returns an empty list (GET still
    shows the warehouse row)."""
    r = client.post("/api/v1/metrics", json={"spec_text": _SPEC})
    metric = r.json()
    resp = client.post(f"/api/v1/metrics/{metric['id']}/reconcile")
    assert resp.status_code == 200
    assert resp.json() == []


def test_delta_computation_sanity() -> None:
    """Cross-check the raw bucketing thresholds so a future tweak fails a
    focused test instead of surprising the end-to-end suite."""
    from litmus_api.jobs.reconciliation import _bucket

    assert _bucket(Decimal("0.01")) == "pass"
    assert _bucket(Decimal("-0.019")) == "pass"
    assert _bucket(Decimal("0.02")) == "warn"
    assert _bucket(Decimal("0.05")) == "warn"
    assert _bucket(Decimal("-0.09")) == "warn"
    assert _bucket(Decimal("0.10")) == "fail"
    assert _bucket(Decimal("-0.5")) == "fail"
