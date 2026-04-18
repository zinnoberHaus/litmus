"""Integration tests for ``POST /api/v1/ask``.

We stub out the engine entirely — these tests exercise the HTTP layer (shape,
status codes, error mapping) not the Anthropic call path. The engine itself
is covered by ``tests/test_ai/test_ask.py``.
"""

from __future__ import annotations

from textwrap import dedent
from typing import Any

import pytest
from fastapi.testclient import TestClient

_VALID_SPEC = dedent("""\
    Metric: Monthly Revenue
    Description: Revenue metric used by the ask-route tests
    Owner: data@example.com

    Source: orders

    Given all records from orders table
      And status is "completed"

    When we calculate
      Then sum the amount column

    The result is "Monthly Revenue"

    Trust:
      Freshness must be less than 24 hours
""")


def _upsert_metric(client: TestClient, slug: str = "revenue") -> dict[str, Any]:
    resp = client.post(
        "/api/v1/metrics", json={"spec_text": _VALID_SPEC, "slug": slug}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _install_stub_engine(
    monkeypatch: pytest.MonkeyPatch,
    *,
    answer: str = "Monthly Revenue for last period was 4,218,430. Trust is green.",
    trust_status: str = "passed",
    raise_error: Any = None,
) -> list[dict[str, Any]]:
    """Replace the engine the route imports with a recording stub."""
    import litmus_api.ai.ask as ask_mod
    from litmus_api.ai.ask import AskAnswer

    calls: list[dict[str, Any]] = []

    def _stub(
        session: Any,
        org: Any,
        question: str,
        *,
        metric_slug: str | None = None,
        public_url: str = "",
        **_: Any,
    ) -> AskAnswer:
        calls.append(
            {
                "question": question,
                "metric_slug": metric_slug,
                "public_url": public_url,
            }
        )
        if raise_error is not None:
            raise raise_error
        return AskAnswer(
            answer=answer,
            metric_slug=metric_slug or "revenue",
            metric_name="Monthly Revenue",
            metric_url=f"{public_url}/metrics/revenue" if public_url else "/metrics/revenue",
            value=4_218_430.0,
            trust_status=trust_status,  # type: ignore[arg-type]
            definition_url=f"{public_url}/metrics/revenue" if public_url else "/metrics/revenue",
            explanation=None,
            run_id="run-abc",
            time_window="last_period",
            model_id="claude-sonnet-4-6",
        )

    monkeypatch.setattr(ask_mod, "answer_question", _stub)
    return calls


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestHappyPath:
    def test_returns_ui_contract_shape(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _upsert_metric(client)
        calls = _install_stub_engine(monkeypatch)

        resp = client.post(
            "/api/v1/ask",
            json={"question": "what was revenue last month?"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()

        # Shape mirrors ui/lib/ask.ts::AskResponse.
        assert body["answer"].startswith("Monthly Revenue")
        assert body["metric_slug"] == "revenue"
        assert body["metric_name"] == "Monthly Revenue"
        assert body["trust_status"] == "passed"
        assert body["definition_url"].endswith("/metrics/revenue")
        assert body["time_window"] == "last_period"
        assert body["model_id"] == "claude-sonnet-4-6"
        assert body["run_id"] == "run-abc"

        # Engine was called once with the raw question (no transformation).
        assert len(calls) == 1
        assert calls[0]["question"] == "what was revenue last month?"
        assert calls[0]["metric_slug"] is None

    def test_metric_slug_passed_through(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _upsert_metric(client)
        calls = _install_stub_engine(monkeypatch)
        resp = client.post(
            "/api/v1/ask",
            json={
                "question": "what's revenue?",
                "metric_slug": "revenue",
            },
        )
        assert resp.status_code == 200
        assert calls[0]["metric_slug"] == "revenue"


# ---------------------------------------------------------------------------
# Error mapping
# ---------------------------------------------------------------------------


class TestErrorMapping:
    def test_missing_api_key_is_500(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from litmus_api.ai.ask import AskError

        _upsert_metric(client)
        _install_stub_engine(
            monkeypatch,
            raise_error=AskError("ai_not_configured", "AI Q&A is not configured."),
        )

        resp = client.post("/api/v1/ask", json={"question": "revenue?"})
        assert resp.status_code == 500
        assert "not configured" in resp.text.lower()
        assert "LITMUS_ANTHROPIC_API_KEY" in resp.text

    def test_unresolved_is_422_with_suggestions(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from litmus_api.ai.ask import AskError

        _upsert_metric(client)
        err = AskError(
            "unresolved",
            "Couldn't match this question to a metric.",
            suggestions=["revenue", "churn", "mrr"],
        )
        _install_stub_engine(monkeypatch, raise_error=err)

        resp = client.post("/api/v1/ask", json={"question": "foo"})
        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert detail["code"] == "unresolved"
        assert detail["suggestions"] == ["revenue", "churn", "mrr"]

    def test_metric_not_found_is_404(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from litmus_api.ai.ask import AskError

        _upsert_metric(client)
        _install_stub_engine(
            monkeypatch,
            raise_error=AskError("metric_not_found", "Metric 'x' not found."),
        )
        resp = client.post(
            "/api/v1/ask", json={"question": "whatever", "metric_slug": "x"}
        )
        assert resp.status_code == 404

    def test_warehouse_error_is_503(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from litmus_api.ai.ask import AskError

        _upsert_metric(client)
        _install_stub_engine(
            monkeypatch,
            raise_error=AskError("warehouse_unavailable", "query failed"),
        )
        resp = client.post("/api/v1/ask", json={"question": "revenue"})
        assert resp.status_code == 503

    def test_bad_input_is_400(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from litmus_api.ai.ask import AskError

        _upsert_metric(client)
        _install_stub_engine(
            monkeypatch,
            raise_error=AskError("bad_input", "empty question"),
        )
        resp = client.post("/api/v1/ask", json={"question": "x"})
        assert resp.status_code == 400

    def test_ai_transport_is_502(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from litmus_api.ai.ask import AskError

        _upsert_metric(client)
        _install_stub_engine(
            monkeypatch,
            raise_error=AskError("ai_transport", "Anthropic 500"),
        )
        resp = client.post("/api/v1/ask", json={"question": "revenue"})
        assert resp.status_code == 502


# ---------------------------------------------------------------------------
# Pydantic validation
# ---------------------------------------------------------------------------


class TestValidation:
    def test_missing_question_is_422(self, client: TestClient) -> None:
        resp = client.post("/api/v1/ask", json={})
        assert resp.status_code == 422

    def test_empty_question_is_422(self, client: TestClient) -> None:
        resp = client.post("/api/v1/ask", json={"question": ""})
        assert resp.status_code == 422
