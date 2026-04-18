"""Tests for the lineage routes on ``/api/v1/metrics/{id}/lineage``.

The round-trip is: POST a nodes+edges subgraph → GET returns the same shape
(modulo DB row ids replacing client ids). A metric that has had no lineage
uploaded gets a 2-node ``source → metric`` stub so the UI never renders an
empty graph.
"""

from __future__ import annotations

from textwrap import dedent

from fastapi.testclient import TestClient

_SPEC = dedent("""\
    Metric: Lineage Demo
    Description: Used by lineage route tests
    Owner: data@example.com

    Source: orders

    Given all records from orders table

    When we calculate
      Then sum the amount column

    The result is "Lineage Demo"

    Trust:
      Freshness must be less than 24 hours
""")


def _create_metric(client: TestClient) -> dict:
    r = client.post("/api/v1/metrics", json={"spec_text": _SPEC})
    assert r.status_code == 201, r.text
    return r.json()


def test_post_lineage_then_get_returns_same_graph(client: TestClient) -> None:
    metric = _create_metric(client)
    payload = {
        "nodes": [
            {"id": "src:orders", "label": "orders", "kind": "source"},
            {"id": "model:stg_orders", "label": "stg_orders", "kind": "model"},
            {"id": "metric:lineage_demo", "label": "Lineage Demo", "kind": "metric"},
        ],
        "edges": [
            {"from": "src:orders", "to": "model:stg_orders"},
            {"from": "model:stg_orders", "to": "metric:lineage_demo"},
        ],
    }
    post = client.post(f"/api/v1/metrics/{metric['id']}/lineage", json=payload)
    assert post.status_code == 200, post.text
    post_body = post.json()
    assert len(post_body["nodes"]) == 3
    assert len(post_body["edges"]) == 2

    get = client.get(f"/api/v1/metrics/{metric['id']}/lineage")
    assert get.status_code == 200, get.text
    get_body = get.json()

    # Labels + kinds survive the round trip.
    labels = {n["label"] for n in get_body["nodes"]}
    assert labels == {"orders", "stg_orders", "Lineage Demo"}
    kinds = {n["kind"] for n in get_body["nodes"]}
    assert kinds == {"source", "model", "metric"}

    # Edges should reference the DB-assigned ids (the server doesn't echo
    # client ids — those are throwaway graph keys used only to wire edges
    # in the payload).
    node_ids = {n["id"] for n in get_body["nodes"]}
    for edge in get_body["edges"]:
        assert edge["from"] in node_ids
        assert edge["to"] in node_ids


def test_get_on_metric_with_no_lineage_returns_stub(client: TestClient) -> None:
    metric = _create_metric(client)
    r = client.get(f"/api/v1/metrics/{metric['id']}/lineage")
    assert r.status_code == 200, r.text
    body = r.json()
    # 2-node stub: source → metric. UI never sees an empty graph.
    assert len(body["nodes"]) == 2
    assert len(body["edges"]) == 1
    kinds = [n["kind"] for n in body["nodes"]]
    assert kinds == ["source", "metric"]
    # Stub carries the primary table name through.
    labels = [n["label"] for n in body["nodes"]]
    assert labels == ["orders", "Lineage Demo"]


def test_upsert_is_idempotent(client: TestClient) -> None:
    """POSTing the same lineage twice replaces, not duplicates."""
    metric = _create_metric(client)
    payload = {
        "nodes": [
            {"id": "a", "label": "orders", "kind": "source"},
            {"id": "b", "label": "metric", "kind": "metric"},
        ],
        "edges": [{"from": "a", "to": "b"}],
    }
    for _ in range(3):
        r = client.post(f"/api/v1/metrics/{metric['id']}/lineage", json=payload)
        assert r.status_code == 200, r.text

    final = client.get(f"/api/v1/metrics/{metric['id']}/lineage").json()
    assert len(final["nodes"]) == 2
    assert len(final["edges"]) == 1


def test_lineage_by_slug_works(client: TestClient) -> None:
    """The route should accept slug or id — matches the rest of /metrics/{id}."""
    _create_metric(client)
    r = client.get("/api/v1/metrics/lineage_demo/lineage")
    assert r.status_code == 200
    assert len(r.json()["nodes"]) == 2


def test_lineage_on_missing_metric_is_404(client: TestClient) -> None:
    r = client.get("/api/v1/metrics/no-such-metric/lineage")
    assert r.status_code == 404


def test_invalid_kind_rejected(client: TestClient) -> None:
    metric = _create_metric(client)
    payload = {
        "nodes": [{"id": "x", "label": "x", "kind": "bogus"}],
        "edges": [],
    }
    r = client.post(f"/api/v1/metrics/{metric['id']}/lineage", json=payload)
    assert r.status_code == 422


def test_edge_referencing_unknown_node_rejected(client: TestClient) -> None:
    metric = _create_metric(client)
    payload = {
        "nodes": [{"id": "a", "label": "a", "kind": "source"}],
        "edges": [{"from": "a", "to": "nonexistent"}],
    }
    r = client.post(f"/api/v1/metrics/{metric['id']}/lineage", json=payload)
    assert r.status_code == 422
