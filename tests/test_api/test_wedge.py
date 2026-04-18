"""End-to-end test of the Litmus 0.2 wedge: spec → API → embed SVG.

Covers the three surfaces a demo walks through:
  1. POST /api/v1/metrics with a raw .metric file
  2. POST /api/v1/runs posting a pass/warning/failed result
  3. GET /embed/<token>/badge.svg renders the correct colour

If any of these break, the product story breaks. Treat these tests as
a smoke alarm for the entire hosted catalog.
"""

from __future__ import annotations

from textwrap import dedent

import pytest
from fastapi.testclient import TestClient

_VALID_SPEC = dedent("""\
    Metric: Daily Revenue
    Description: Revenue metric for API wedge test
    Owner: data@example.com

    Source: orders

    Given all records from orders table
      And status is "completed"

    When we calculate
      Then sum the amount column

    The result is "Daily Revenue"

    Trust:
      Freshness must be less than 24 hours
      Null rate on amount must be less than 5%
""")


class TestHealth:
    def test_health(self, client: TestClient) -> None:
        r = client.get("/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert body["version"]


class TestMetricUpsert:
    def test_create_metric(self, client: TestClient) -> None:
        r = client.post("/api/v1/metrics", json={"spec_text": _VALID_SPEC})
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["name"] == "Daily Revenue"
        assert body["slug"] == "daily_revenue"
        assert body["primary_table"] == "orders"
        assert body["embed_token"].startswith("lme_")
        assert body["latest_run"] is None

    def test_upsert_is_idempotent(self, client: TestClient) -> None:
        r1 = client.post("/api/v1/metrics", json={"spec_text": _VALID_SPEC})
        r2 = client.post("/api/v1/metrics", json={"spec_text": _VALID_SPEC})
        assert r1.json()["id"] == r2.json()["id"]
        # Embed token persists across upserts — third-party embeds must not break.
        assert r1.json()["embed_token"] == r2.json()["embed_token"]

    def test_invalid_spec_returns_422(self, client: TestClient) -> None:
        r = client.post("/api/v1/metrics", json={"spec_text": "not a metric file"})
        assert r.status_code == 422
        assert "Metric" in r.text

    def test_list_metrics(self, client: TestClient) -> None:
        client.post("/api/v1/metrics", json={"spec_text": _VALID_SPEC})
        r = client.get("/api/v1/metrics")
        assert r.status_code == 200
        assert len(r.json()) == 1

    def test_get_by_slug(self, client: TestClient) -> None:
        client.post("/api/v1/metrics", json={"spec_text": _VALID_SPEC})
        r = client.get("/api/v1/metrics/daily_revenue")
        assert r.status_code == 200
        assert r.json()["name"] == "Daily Revenue"


class TestRuns:
    def test_post_run_and_history(self, client: TestClient) -> None:
        m = client.post("/api/v1/metrics", json={"spec_text": _VALID_SPEC}).json()
        r = client.post(
            "/api/v1/runs",
            json={
                "metric_id": m["id"],
                "status": "passed",
                "trust_score": 0.95,
                "value_sum": 42000.0,
                "row_count": 123,
                "check_results": [
                    {
                        "rule_type": "freshness",
                        "rule": {"max_hours": 24},
                        "status": "passed",
                        "message": "fresh",
                        "actual_value": 2.5,
                        "threshold_value": 24.0,
                    }
                ],
            },
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["status"] == "passed"
        assert len(body["check_results"]) == 1

        hist = client.get(f"/api/v1/metrics/{m['id']}/history").json()
        assert len(hist["runs"]) == 1
        assert hist["runs"][0]["trust_score"] == pytest.approx(0.95)

    def test_run_on_missing_metric_is_404(self, client: TestClient) -> None:
        r = client.post(
            "/api/v1/runs",
            json={"metric_slug": "no-such-metric", "status": "passed"},
        )
        assert r.status_code == 404


class TestEmbedSvg:
    def test_svg_has_correct_content_type(self, client: TestClient) -> None:
        m = client.post("/api/v1/metrics", json={"spec_text": _VALID_SPEC}).json()
        r = client.get(f"/embed/{m['embed_token']}/badge.svg")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("image/svg+xml")
        assert r.text.lstrip().startswith("<svg")

    def test_svg_reflects_latest_run_status(self, client: TestClient) -> None:
        m = client.post("/api/v1/metrics", json={"spec_text": _VALID_SPEC}).json()
        # No run → "Unknown" label
        r = client.get(f"/embed/{m['embed_token']}/badge.svg")
        assert "Unknown" in r.text

        # Post a failed run, SVG should reflect "Broken" with the red colour.
        client.post(
            "/api/v1/runs",
            json={
                "metric_id": m["id"],
                "status": "failed",
                "trust_score": 0.45,
            },
        )
        r = client.get(f"/embed/{m['embed_token']}/badge.svg")
        assert "Broken" in r.text
        assert "#dc2626" in r.text

        # Newer passing run wins on status.
        client.post(
            "/api/v1/runs",
            json={
                "metric_id": m["id"],
                "status": "passed",
                "trust_score": 0.98,
            },
        )
        r = client.get(f"/embed/{m['embed_token']}/badge.svg")
        assert "Trusted" in r.text
        assert "#16a34a" in r.text

    def test_unknown_token_returns_safe_svg_not_404(self, client: TestClient) -> None:
        """Third-party embeds must not break with HTTP errors — return a grey pill."""
        r = client.get("/embed/lme_definitelynotatoken/badge.svg")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("image/svg+xml")
        assert "Unknown" in r.text
