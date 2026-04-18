"""CRUD + read tests for the BI mapping & reconciliation API surface.

We exercise every endpoint on a real (SQLite) DB via the ``client`` fixture —
no BI SDKs are imported here. The reconciliation job itself is exercised in
``test_reconcile_job.py`` with mocked connectors.
"""

from __future__ import annotations

from textwrap import dedent

from fastapi.testclient import TestClient

_SPEC = dedent("""\
    Metric: Recon Demo
    Description: Used by reconciliation route tests
    Owner: data@example.com

    Source: orders

    Given all records from orders table

    When we calculate
      Then sum the amount column

    The result is "Recon Demo"

    Trust:
      Freshness must be less than 24 hours
""")


def _create_metric(client: TestClient) -> dict:
    r = client.post("/api/v1/metrics", json={"spec_text": _SPEC})
    assert r.status_code == 201, r.text
    return r.json()


def test_create_and_list_bi_mappings(client: TestClient) -> None:
    metric = _create_metric(client)

    # POST a Looker mapping.
    r = client.post(
        f"/api/v1/metrics/{metric['id']}/bi-mappings",
        json={"source": "looker", "identifier": "ecommerce::orders.total_revenue"},
    )
    assert r.status_code == 201, r.text
    created = r.json()
    assert created["source"] == "looker"
    assert created["identifier"] == "ecommerce::orders.total_revenue"

    # And a Tableau mapping.
    r2 = client.post(
        f"/api/v1/metrics/{metric['id']}/bi-mappings",
        json={"source": "tableau", "identifier": "wb-1/view-abc/SUM(Sales)"},
    )
    assert r2.status_code == 201, r2.text

    # GET lists both, alphabetical by source (looker < tableau).
    listed = client.get(f"/api/v1/metrics/{metric['id']}/bi-mappings").json()
    assert [m["source"] for m in listed] == ["looker", "tableau"]


def test_duplicate_mapping_is_409(client: TestClient) -> None:
    metric = _create_metric(client)
    payload = {"source": "looker", "identifier": "ecommerce::orders.total_revenue"}

    r1 = client.post(
        f"/api/v1/metrics/{metric['id']}/bi-mappings", json=payload
    )
    assert r1.status_code == 201
    r2 = client.post(
        f"/api/v1/metrics/{metric['id']}/bi-mappings", json=payload
    )
    assert r2.status_code == 409, r2.text


def test_unknown_source_is_422(client: TestClient) -> None:
    metric = _create_metric(client)
    r = client.post(
        f"/api/v1/metrics/{metric['id']}/bi-mappings",
        json={"source": "mode", "identifier": "whatever"},
    )
    assert r.status_code == 422, r.text


def test_delete_mapping(client: TestClient) -> None:
    metric = _create_metric(client)
    r = client.post(
        f"/api/v1/metrics/{metric['id']}/bi-mappings",
        json={"source": "looker", "identifier": "ecommerce::orders.total_revenue"},
    )
    mapping_id = r.json()["id"]

    d = client.delete(
        f"/api/v1/metrics/{metric['id']}/bi-mappings/{mapping_id}"
    )
    assert d.status_code == 204

    listed = client.get(f"/api/v1/metrics/{metric['id']}/bi-mappings").json()
    assert listed == []


def test_delete_unknown_mapping_is_404(client: TestClient) -> None:
    metric = _create_metric(client)
    r = client.delete(
        f"/api/v1/metrics/{metric['id']}/bi-mappings/nonexistent-id"
    )
    assert r.status_code == 404


def test_reconciliation_always_includes_warehouse_row(client: TestClient) -> None:
    """A metric with no runs and no mappings still returns the warehouse row
    so the UI panel never renders empty."""
    metric = _create_metric(client)
    r = client.get(f"/api/v1/metrics/{metric['id']}/reconciliation")
    assert r.status_code == 200, r.text
    rows = r.json()
    assert len(rows) == 1
    assert rows[0]["source"] == "warehouse"
    assert rows[0]["value"] == 0.0
    assert rows[0]["status"] == "pass"


def test_reconciliation_reads_warehouse_value_from_latest_run(
    client: TestClient,
) -> None:
    """The synthetic warehouse row tracks the latest Run's ``value_sum``."""
    metric = _create_metric(client)
    # Seed a run via the existing /runs endpoint.
    run_resp = client.post(
        "/api/v1/runs",
        json={
            "metric_id": metric["id"],
            "status": "passed",
            "trust_score": 1.0,
            "value_sum": 5000.0,
            "triggered_by": "test",
        },
    )
    assert run_resp.status_code == 201, run_resp.text

    rows = client.get(f"/api/v1/metrics/{metric['id']}/reconciliation").json()
    warehouse = next(r for r in rows if r["source"] == "warehouse")
    assert warehouse["value"] == 5000.0


def test_reconciliation_returns_latest_row_per_source(client: TestClient) -> None:
    """Directly seed two Reconciliation rows for Looker and verify GET
    only surfaces the newest one."""
    metric = _create_metric(client)

    # Poke rows into the DB directly — we're testing the read logic, not
    # the job. Going through the job would require mocking the SDKs.
    from datetime import datetime, timedelta

    from litmus_api.db import get_session
    from litmus_api.models import Reconciliation

    with next(get_session()) as session:
        old = Reconciliation(
            metric_id=metric["id"],
            source="looker",
            identifier="ecommerce::orders.total_revenue",
            value=100.0,
            delta=0.0,
            status="pass",
            recorded_at=datetime.utcnow() - timedelta(hours=2),
        )
        new = Reconciliation(
            metric_id=metric["id"],
            source="looker",
            identifier="ecommerce::orders.total_revenue",
            value=200.0,
            delta=0.05,
            status="warn",
            recorded_at=datetime.utcnow(),
        )
        session.add_all([old, new])
        session.commit()

    rows = client.get(f"/api/v1/metrics/{metric['id']}/reconciliation").json()
    looker_rows = [r for r in rows if r["source"] == "looker"]
    assert len(looker_rows) == 1
    assert looker_rows[0]["value"] == 200.0
    assert looker_rows[0]["status"] == "warn"


def test_reconciliation_on_unknown_metric_is_404(client: TestClient) -> None:
    r = client.get("/api/v1/metrics/no-such-metric/reconciliation")
    assert r.status_code == 404


def test_auth_required_when_multi_tenant(tmp_path, monkeypatch) -> None:
    """Sanity check that BI routes respect the same auth as the rest of the API."""
    # Rebuild the client with multi-tenant mode so ``current_org`` demands
    # a bearer token.
    db_path = tmp_path / "bi_auth.db"
    monkeypatch.setenv("LITMUS_DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("LITMUS_TENANT_MODE", "multi")

    import litmus_api.db as db_mod

    db_mod._engine = None
    db_mod._SessionLocal = None

    from litmus_api.db import get_engine, init_engine
    from litmus_api.models import Base

    init_engine()
    Base.metadata.create_all(bind=get_engine())

    from litmus_api.main import create_app

    app = create_app()
    c = TestClient(app)

    r = c.get("/api/v1/metrics/anything/reconciliation")
    assert r.status_code == 401
