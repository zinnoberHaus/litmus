"""Integration tests for the run-explanation API routes.

We stub out the AI engine entirely — these tests exercise the HTTP layer
(auth, status codes, error mapping, idempotency) not the Anthropic call path.
The engine itself is covered by ``tests/test_ai/test_explain.py``.
"""

from __future__ import annotations

from textwrap import dedent
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

_VALID_SPEC = dedent("""\
    Metric: Daily Revenue
    Description: Revenue metric for AI explanation test
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


def _create_metric_and_failing_run(client: TestClient) -> str:
    """Helper: upsert a metric + post a failed run; return the run UUID."""
    m = client.post("/api/v1/metrics", json={"spec_text": _VALID_SPEC}).json()
    r = client.post(
        "/api/v1/runs",
        json={
            "metric_id": m["id"],
            "status": "failed",
            "trust_score": 0.4,
            "value_sum": 100.0,
            "row_count": 5,
            "check_results": [
                {
                    "rule_type": "freshness",
                    "rule": {"max_hours": 24},
                    "status": "failed",
                    "message": "stale",
                    "actual_value": 48.0,
                    "threshold_value": 24.0,
                }
            ],
        },
    ).json()
    return r["id"]


def _install_stub_engine(
    monkeypatch: pytest.MonkeyPatch,
    *,
    hypothesis: str = "Freshness is 48 hours stale — likely an ingest outage.",
    suggested_action: str = "Re-run the nightly ingest job and confirm logs.",
    calls: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Patch the engine used by the route. Returns the call list for asserts."""
    import litmus_api.ai.explain as explain_mod
    from litmus_api.models import RunExplanation

    recorded = calls if calls is not None else []

    def _stub(session: Any, run_id: Any, *, regenerate: bool = False, **kw: Any):
        recorded.append({"run_id": str(run_id), "regenerate": regenerate, **kw})
        run_id_s = str(run_id)
        existing = (
            session.query(RunExplanation).filter_by(run_id=run_id_s).one_or_none()
        )
        if existing is not None and not regenerate:
            return existing
        if existing is None:
            row = RunExplanation(
                run_id=run_id_s,
                hypothesis=hypothesis,
                suggested_action=suggested_action,
                model_id="claude-sonnet-4-6",
            )
            session.add(row)
        else:
            existing.hypothesis = hypothesis
            existing.suggested_action = suggested_action
            row = existing
        session.flush()
        return row

    monkeypatch.setattr(explain_mod, "explain_run", _stub)
    return recorded


class TestPostExplain:
    def test_happy_path_returns_200_and_persists(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls = _install_stub_engine(monkeypatch)
        run_id = _create_metric_and_failing_run(client)

        r = client.post(f"/api/v1/runs/{run_id}/explain")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["run_id"] == run_id
        assert "48 hours" in body["hypothesis"]
        assert body["suggested_action"].startswith("Re-run")
        assert body["model_id"] == "claude-sonnet-4-6"
        assert len(calls) == 1

        # GET should now return the cached explanation.
        g = client.get(f"/api/v1/runs/{run_id}/explanation")
        assert g.status_code == 200
        assert g.json()["id"] == body["id"]

    def test_idempotent_without_regenerate(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls = _install_stub_engine(monkeypatch)
        run_id = _create_metric_and_failing_run(client)

        first = client.post(f"/api/v1/runs/{run_id}/explain").json()
        second = client.post(f"/api/v1/runs/{run_id}/explain").json()

        assert first["id"] == second["id"]
        # Both calls flow into the stubbed engine — the engine handles the
        # cache check, so we see two invocations but the returned row is
        # the same.
        assert len(calls) == 2
        assert calls[1]["regenerate"] is False

    def test_regenerate_flag_is_passed_through(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls = _install_stub_engine(monkeypatch)
        run_id = _create_metric_and_failing_run(client)

        client.post(f"/api/v1/runs/{run_id}/explain")
        client.post(f"/api/v1/runs/{run_id}/explain?regenerate=true")

        assert [c["regenerate"] for c in calls] == [False, True]

    def test_missing_run_returns_404(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _install_stub_engine(monkeypatch)
        r = client.post(f"/api/v1/runs/{uuid4()}/explain")
        assert r.status_code == 404


class TestErrorMapping:
    def test_value_error_is_400(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import litmus_api.ai.explain as explain_mod

        def _raise_value(*_: Any, **__: Any) -> Any:
            raise ValueError("Nothing to explain")

        monkeypatch.setattr(explain_mod, "explain_run", _raise_value)
        run_id = _create_metric_and_failing_run(client)
        r = client.post(f"/api/v1/runs/{run_id}/explain")
        assert r.status_code == 400
        assert "Nothing to explain" in r.text

    def test_runtime_error_is_500_not_configured(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Missing API key → 500 so the UI can show 'not configured' copy."""
        import litmus_api.ai.explain as explain_mod

        def _raise_runtime(*_: Any, **__: Any) -> Any:
            raise RuntimeError("LITMUS_ANTHROPIC_API_KEY not set")

        monkeypatch.setattr(explain_mod, "explain_run", _raise_runtime)
        run_id = _create_metric_and_failing_run(client)
        r = client.post(f"/api/v1/runs/{run_id}/explain")
        assert r.status_code == 500
        assert "not configured" in r.text.lower()

    def test_explain_error_is_502(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import litmus_api.ai.explain as explain_mod
        from litmus_api.ai.explain import ExplainError

        def _raise_explain(*_: Any, **__: Any) -> Any:
            raise ExplainError("Anthropic API call failed: boom")

        monkeypatch.setattr(explain_mod, "explain_run", _raise_explain)
        run_id = _create_metric_and_failing_run(client)
        r = client.post(f"/api/v1/runs/{run_id}/explain")
        assert r.status_code == 502
        assert "boom" in r.text


class TestGetExplanation:
    def test_returns_404_when_no_explanation_exists(
        self, client: TestClient
    ) -> None:
        # Run exists, but no explain call has been made yet.
        run_id = _create_metric_and_failing_run(client)
        r = client.get(f"/api/v1/runs/{run_id}/explanation")
        assert r.status_code == 404
        assert "POST" in r.text

    def test_returns_404_for_unknown_run(self, client: TestClient) -> None:
        r = client.get(f"/api/v1/runs/{uuid4()}/explanation")
        assert r.status_code == 404
