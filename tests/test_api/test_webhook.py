"""Tests for ``POST /webhooks/github`` — the GitHub push ingestion path.

Signature verification is HMAC-SHA256 over the raw body; fetching ``.metric``
files uses stdlib ``urllib.request``, which we monkeypatch to return canned
spec text instead of hitting ``raw.githubusercontent.com``.
"""

from __future__ import annotations

import hashlib
import hmac
import io
import json
from dataclasses import dataclass
from textwrap import dedent

from fastapi.testclient import TestClient

_SECRET = "shhh-its-a-secret"

_VALID_SPEC = dedent("""\
    Metric: Webhook Revenue
    Description: Revenue metric landed via GitHub webhook
    Owner: data@example.com

    Source: orders

    Given all records from orders table
      And status is "completed"

    When we calculate
      Then sum the amount column

    The result is "Webhook Revenue"

    Trust:
      Freshness must be less than 24 hours
""")

_BROKEN_SPEC = "this is not a valid metric file"


@dataclass
class _FakeResponse:
    status: int
    body: bytes

    def read(self) -> bytes:
        return self.body

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *exc) -> None:
        return None


def _sign(body: bytes) -> str:
    """Return the same ``sha256=…`` header GitHub sends."""
    digest = hmac.new(_SECRET.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _push_payload(
    repo: str = "acme/data",
    sha: str = "deadbeef",
    added: list[str] | None = None,
    modified: list[str] | None = None,
    author_email: str = "push-author@example.com",
) -> dict:
    return {
        "repository": {"full_name": repo},
        "head_commit": {
            "id": sha,
            "author": {"email": author_email},
        },
        "commits": [
            {
                "id": sha,
                "added": added or [],
                "modified": modified or [],
                "removed": [],
            }
        ],
    }


def _install_url_shim(files: dict[str, str], monkeypatch) -> None:
    """Patch ``urllib.request.urlopen`` inside the webhooks module.

    ``files`` is keyed by path suffix (the ``{repo}/{sha}/{path}`` portion of
    the raw.githubusercontent URL). Unknown paths raise a 404-style HTTPError
    so we can exercise the "ignored" code path.
    """

    def fake_urlopen(req, timeout=None):
        import urllib.error

        url = req.full_url
        for key, body in files.items():
            if url.endswith(key):
                return _FakeResponse(200, body.encode("utf-8"))
        raise urllib.error.HTTPError(
            url, 404, "Not Found", {}, io.BytesIO(b"")  # type: ignore[arg-type]
        )

    monkeypatch.setattr(
        "litmus_api.routes.webhooks.urllib.request.urlopen", fake_urlopen
    )


def test_valid_push_upserts_metric_and_writes_revision(
    client: TestClient, monkeypatch
) -> None:
    monkeypatch.setenv("LITMUS_GITHUB_WEBHOOK_SECRET", _SECRET)
    _install_url_shim(
        {"acme/data/deadbeef/metrics/revenue.metric": _VALID_SPEC},
        monkeypatch,
    )

    payload = _push_payload(added=["metrics/revenue.metric"])
    body = json.dumps(payload).encode("utf-8")

    resp = client.post(
        "/webhooks/github",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "push",
            "X-Hub-Signature-256": _sign(body),
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["upserted"] == ["webhook_revenue"]
    assert data["ignored"] == []

    # The metric must now be in the catalog, with source_* threaded through.
    metric = client.get("/api/v1/metrics/webhook_revenue").json()
    assert metric["source_repo"] == "acme/data"
    assert metric["source_path"] == "metrics/revenue.metric"
    assert metric["source_sha"] == "deadbeef"

    # And a revision must have been recorded (the webhook is the first
    # touch, so revision_count starts at 1).
    assert metric["revision_count"] == 1
    revs = client.get(f"/api/v1/metrics/{metric['id']}/revisions").json()
    assert len(revs) == 1
    assert revs[0]["author"] == "push-author@example.com"
    assert revs[0]["source_sha"] == "deadbeef"


def test_bad_signature_returns_401(client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("LITMUS_GITHUB_WEBHOOK_SECRET", _SECRET)
    body = json.dumps(_push_payload()).encode("utf-8")
    resp = client.post(
        "/webhooks/github",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "push",
            "X-Hub-Signature-256": "sha256=not-a-real-digest",
        },
    )
    assert resp.status_code == 401


def test_missing_signature_header_returns_401(
    client: TestClient, monkeypatch
) -> None:
    monkeypatch.setenv("LITMUS_GITHUB_WEBHOOK_SECRET", _SECRET)
    body = json.dumps(_push_payload()).encode("utf-8")
    resp = client.post(
        "/webhooks/github",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "push",
        },
    )
    assert resp.status_code == 401


def test_non_push_event_returns_ignored(client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("LITMUS_GITHUB_WEBHOOK_SECRET", _SECRET)
    body = json.dumps({"zen": "Approachable is better than simple."}).encode("utf-8")
    resp = client.post(
        "/webhooks/github",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "ping",
            "X-Hub-Signature-256": _sign(body),
        },
    )
    assert resp.status_code == 200
    assert resp.json() == {"status": "ignored"}


def test_push_with_no_metric_changes_returns_empty(
    client: TestClient, monkeypatch
) -> None:
    monkeypatch.setenv("LITMUS_GITHUB_WEBHOOK_SECRET", _SECRET)
    payload = _push_payload(
        added=["README.md", "src/main.py"],
        modified=["docs/guide.md"],
    )
    body = json.dumps(payload).encode("utf-8")
    resp = client.post(
        "/webhooks/github",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "push",
            "X-Hub-Signature-256": _sign(body),
        },
    )
    assert resp.status_code == 200
    assert resp.json() == {"upserted": [], "ignored": []}


def test_unparseable_metric_goes_to_ignored(
    client: TestClient, monkeypatch
) -> None:
    monkeypatch.setenv("LITMUS_GITHUB_WEBHOOK_SECRET", _SECRET)
    _install_url_shim(
        {
            "acme/data/deadbeef/metrics/good.metric": _VALID_SPEC,
            "acme/data/deadbeef/metrics/broken.metric": _BROKEN_SPEC,
        },
        monkeypatch,
    )

    payload = _push_payload(
        added=["metrics/good.metric"],
        modified=["metrics/broken.metric"],
    )
    body = json.dumps(payload).encode("utf-8")

    resp = client.post(
        "/webhooks/github",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "push",
            "X-Hub-Signature-256": _sign(body),
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["upserted"] == ["webhook_revenue"]
    assert data["ignored"] == ["metrics/broken.metric"]

    # The broken file must NOT have been upserted.
    listing = client.get("/api/v1/metrics").json()
    slugs = {m["slug"] for m in listing}
    assert "webhook_revenue" in slugs
    # Nothing else snuck in.
    assert len(slugs) == 1


def test_missing_server_secret_returns_401(client: TestClient, monkeypatch) -> None:
    """Operator forgot to set the env var — fail closed, don't silently accept."""
    monkeypatch.delenv("LITMUS_GITHUB_WEBHOOK_SECRET", raising=False)
    body = json.dumps(_push_payload()).encode("utf-8")
    resp = client.post(
        "/webhooks/github",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "push",
            "X-Hub-Signature-256": "sha256=anything",
        },
    )
    assert resp.status_code == 401
