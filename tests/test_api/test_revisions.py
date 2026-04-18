"""Tests for the ``MetricRevision`` append-only spec-change log.

The contract exercised here:
  1. POST /metrics on a brand-new slug writes exactly one revision.
  2. Re-posting the same spec_text verbatim does NOT write another revision.
  3. Re-posting with any spec_text change writes a new revision.
  4. GET /metrics/{id}/revisions returns up to 30 rows, oldest-last.
  5. MetricOut.revision_count reflects the count on every response.

These map directly to the Part B5 checklist. If any of these fail we've
regressed the audit story that metric owners rely on to correlate trust
regressions with definition edits.
"""

from __future__ import annotations

from textwrap import dedent

from fastapi.testclient import TestClient

_BASE_SPEC = dedent("""\
    Metric: Revisioned Revenue
    Description: initial description
    Owner: data@example.com

    Source: orders

    Given all records from orders table

    When we calculate
      Then sum the amount column

    The result is "Revisioned Revenue"

    Trust:
      Freshness must be less than 24 hours
""")


def _edited_spec(suffix: str) -> str:
    # Tweak the Trust block so the parsed spec_json also changes — this
    # defends against any accidental optimisation that compares spec_json
    # instead of the raw text.
    return _BASE_SPEC.replace(
        "Freshness must be less than 24 hours",
        f"Freshness must be less than 24 hours\n  {suffix}",
    )


class TestRevisionCreation:
    def test_first_upsert_creates_one_revision(self, client: TestClient) -> None:
        r = client.post("/api/v1/metrics", json={"spec_text": _BASE_SPEC})
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["revision_count"] == 1

        revisions = client.get(
            f"/api/v1/metrics/{body['id']}/revisions"
        ).json()
        assert len(revisions) == 1
        assert revisions[0]["spec_text"] == _BASE_SPEC
        assert revisions[0]["metric_id"] == body["id"]

    def test_identical_reupsert_does_not_create_revision(
        self, client: TestClient
    ) -> None:
        first = client.post("/api/v1/metrics", json={"spec_text": _BASE_SPEC})
        first_id = first.json()["id"]
        assert first.json()["revision_count"] == 1

        # Exact same spec_text — simulates the common CI case where the
        # same .metric file is re-pushed every build.
        second = client.post("/api/v1/metrics", json={"spec_text": _BASE_SPEC})
        assert second.status_code == 201
        assert second.json()["id"] == first_id
        assert second.json()["revision_count"] == 1

        revisions = client.get(
            f"/api/v1/metrics/{first_id}/revisions"
        ).json()
        assert len(revisions) == 1

    def test_changed_spec_creates_new_revision(self, client: TestClient) -> None:
        first = client.post("/api/v1/metrics", json={"spec_text": _BASE_SPEC})
        first_id = first.json()["id"]

        edited = _edited_spec("Null rate on amount must be less than 5%")
        second = client.post("/api/v1/metrics", json={"spec_text": edited})
        assert second.status_code == 201
        assert second.json()["id"] == first_id
        assert second.json()["revision_count"] == 2

        revisions = client.get(
            f"/api/v1/metrics/{first_id}/revisions"
        ).json()
        assert len(revisions) == 2
        # Oldest-last ordering: the originally submitted spec is position 0,
        # the newer one is position -1.
        assert revisions[0]["spec_text"] == _BASE_SPEC
        assert revisions[-1]["spec_text"] == edited

    def test_author_and_source_sha_are_persisted(
        self, client: TestClient
    ) -> None:
        r = client.post(
            "/api/v1/metrics",
            json={
                "spec_text": _BASE_SPEC,
                "source_sha": "deadbeef",
                "author": "alice@example.com",
            },
        )
        assert r.status_code == 201
        revisions = client.get(
            f"/api/v1/metrics/{r.json()['id']}/revisions"
        ).json()
        assert revisions[0]["source_sha"] == "deadbeef"
        assert revisions[0]["author"] == "alice@example.com"


class TestRevisionListEndpoint:
    def test_returns_oldest_last_across_many_edits(
        self, client: TestClient
    ) -> None:
        # Upsert a sequence of 5 distinct specs; each edit differs by one line.
        first = client.post("/api/v1/metrics", json={"spec_text": _BASE_SPEC})
        metric_id = first.json()["id"]
        edits = [f"Null rate on amount must be less than {pct}%" for pct in range(1, 5)]
        for rule in edits:
            client.post(
                "/api/v1/metrics",
                json={"spec_text": _edited_spec(rule)},
            )

        revisions = client.get(
            f"/api/v1/metrics/{metric_id}/revisions"
        ).json()
        assert len(revisions) == 5
        # First entry is the seed spec, last entry is the most recent edit.
        assert revisions[0]["spec_text"] == _BASE_SPEC
        assert edits[-1] in revisions[-1]["spec_text"]

    def test_caps_at_30_revisions(self, client: TestClient) -> None:
        first = client.post("/api/v1/metrics", json={"spec_text": _BASE_SPEC})
        metric_id = first.json()["id"]
        # 34 further edits -> 35 total -> endpoint must trim to the newest 30.
        for i in range(34):
            client.post(
                "/api/v1/metrics",
                json={
                    "spec_text": _edited_spec(
                        f"Null rate on amount must be less than {i % 99 + 1}%"
                    ),
                },
            )

        revisions = client.get(
            f"/api/v1/metrics/{metric_id}/revisions"
        ).json()
        assert len(revisions) == 30
        # Oldest-last: the tail must be the most recent write.
        assert "less than 34" in revisions[-1]["spec_text"]

    def test_missing_metric_is_404(self, client: TestClient) -> None:
        r = client.get("/api/v1/metrics/does-not-exist/revisions")
        assert r.status_code == 404

    def test_slug_lookup_works(self, client: TestClient) -> None:
        created = client.post(
            "/api/v1/metrics", json={"spec_text": _BASE_SPEC}
        ).json()
        slug = created["slug"]
        r = client.get(f"/api/v1/metrics/{slug}/revisions")
        assert r.status_code == 200
        assert len(r.json()) == 1
