"""Test the CLI → API push path.

We monkeypatch ``urllib.request.urlopen`` inside ``litmus.api_push`` so the
push helper runs against a live FastAPI TestClient instead of the network.
This covers the full round-trip: ``litmus check --push`` upserts a metric,
posts a run, and the resulting embed SVG reflects the status.
"""

from __future__ import annotations

import io
import json
from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient

from litmus.api_push import PushConfig, push_results
from litmus.checks.runner import CheckResult, CheckStatus, CheckSuite
from litmus.spec.metric_spec import (
    FreshnessRule,
    MetricSpec,
    TrustSpec,
)

_SPEC_TEXT = """Metric: Push Test Revenue
Description: Revenue via CLI push
Owner: data@example.com

Source: orders

Given all records from orders table

When we calculate
  Then sum the amount column

The result is "Push Test Revenue"

Trust:
  Freshness must be less than 24 hours
"""


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


def _install_urlopen_shim(client: TestClient, monkeypatch) -> list[dict]:
    """Route urlopen calls inside api_push through the FastAPI TestClient."""
    captured: list[dict] = []

    def fake_urlopen(req, timeout=None):
        method = req.get_method()
        # req.full_url includes the scheme+host, strip them to get the path
        path = req.full_url.split("://", 1)[-1].split("/", 1)[-1]
        path = "/" + path
        payload = json.loads(req.data.decode("utf-8")) if req.data else None
        headers = dict(req.header_items())
        captured.append({"method": method, "path": path, "payload": payload})
        resp = client.request(
            method, path, json=payload, headers={k: v for k, v in headers.items()}
        )
        if resp.status_code >= 400:
            import urllib.error

            err = urllib.error.HTTPError(
                req.full_url, resp.status_code, resp.reason_phrase,
                resp.headers, io.BytesIO(resp.content),
            )
            raise err
        return _FakeResponse(resp.status_code, resp.content)

    monkeypatch.setattr("litmus.api_push.urllib.request.urlopen", fake_urlopen)
    return captured


def test_push_results_upserts_metric_then_run(client: TestClient, monkeypatch):
    _install_urlopen_shim(client, monkeypatch)

    spec = MetricSpec(
        name="Push Test Revenue",
        description="Revenue via CLI push",
        owner="data@example.com",
        sources=["orders"],
        result_name="Push Test Revenue",
        trust=TrustSpec(freshness=FreshnessRule(max_hours=24)),
        raw_text=_SPEC_TEXT,
    )
    suite = CheckSuite(metric_name=spec.name)
    suite.results.append(
        CheckResult(
            name="freshness",
            status=CheckStatus.PASSED,
            message="fresh",
            actual_value=2.0,
            threshold=24.0,
        )
    )

    cfg = PushConfig(endpoint="http://testserver", api_key=None)
    metric_ids = push_results(cfg, [(spec, suite)], spec_texts={spec.name: _SPEC_TEXT})

    assert len(metric_ids) == 1
    metric_id = metric_ids[0]

    # History should show one run with a passing status + trust_score 1.0.
    hist = client.get(f"/api/v1/metrics/{metric_id}/history").json()
    assert len(hist["runs"]) == 1
    assert hist["runs"][0]["status"] == "passed"
    assert hist["runs"][0]["trust_score"] == pytest.approx(1.0)


def test_push_results_maps_warning_overall(client: TestClient, monkeypatch):
    _install_urlopen_shim(client, monkeypatch)

    spec = MetricSpec(
        name="Push Warning Case",
        sources=["orders"],
        raw_text=_SPEC_TEXT.replace("Push Test Revenue", "Push Warning Case"),
    )
    suite = CheckSuite(metric_name=spec.name)
    suite.results.append(
        CheckResult(
            name="null_rate", status=CheckStatus.PASSED, message="",
            actual_value=0, threshold=5,
        )
    )
    suite.results.append(
        CheckResult(
            name="freshness", status=CheckStatus.WARNING, message="close to limit",
            actual_value=22, threshold=24,
        )
    )

    cfg = PushConfig(endpoint="http://testserver")
    ids = push_results(
        cfg, [(spec, suite)], spec_texts={spec.name: spec.raw_text or ""}
    )
    hist = client.get(f"/api/v1/metrics/{ids[0]}/history").json()
    assert hist["runs"][0]["status"] == "warning"
    # trust_score is (1 passed + 0.5 warning) / 2 = 0.75
    assert hist["runs"][0]["trust_score"] == pytest.approx(0.75)
