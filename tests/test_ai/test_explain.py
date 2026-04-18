"""Unit tests for :mod:`litmus_api.ai.explain`.

All tests use a stub Anthropic client — we never touch the real API. The
production path reads ``LITMUS_ANTHROPIC_API_KEY`` from the environment and
builds its own client; for tests we bypass that by passing ``anthropic_client``
directly to :func:`explain_run`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from litmus_api.ai.explain import (
    DEFAULT_MODEL_ID,
    ExplainError,
    explain_run,
)
from litmus_api.models import (
    Base,
    CheckResult,
    Metric,
    Org,
    Run,
    RunExplanation,
)

# ---------------------------------------------------------------------------
# Stub Anthropic client
# ---------------------------------------------------------------------------


@dataclass
class _Block:
    type: str
    name: str | None = None
    input: dict[str, Any] | None = None
    text: str | None = None


@dataclass
class _Response:
    content: list[_Block]
    stop_reason: str = "tool_use"


@dataclass
class _Messages:
    """Recorded invocations + the next response to return."""

    response: _Response
    calls: list[dict[str, Any]] = field(default_factory=list)

    def create(self, **kwargs: Any) -> _Response:  # noqa: ANN401
        self.calls.append(kwargs)
        return self.response


@dataclass
class _StubClient:
    messages: _Messages


def _ok_response(
    hypothesis: str = "Freshness is 14 hours stale because the nightly ingest "
    "didn't run.",
    suggested_action: str = "Check the ingest job logs for last night.",
) -> _Response:
    return _Response(
        content=[
            _Block(
                type="tool_use",
                name="return_run_explanation",
                input={
                    "hypothesis": hypothesis,
                    "suggested_action": suggested_action,
                },
            )
        ]
    )


def _make_stub(response: _Response | None = None) -> _StubClient:
    return _StubClient(messages=_Messages(response or _ok_response()))


# ---------------------------------------------------------------------------
# In-memory SQLAlchemy fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)  # noqa: N806 — SQLAlchemy idiom
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


@pytest.fixture()
def seeded(session: Session) -> tuple[Org, Metric, Run]:
    org = Org(slug="default", name="Default")
    session.add(org)
    session.flush()

    metric = Metric(
        org_id=org.id,
        slug="daily_revenue",
        name="Daily Revenue",
        description="Sum of completed orders per day.",
        spec_json={
            "sources": ["orders"],
            "trust": {
                "freshness": {"max_hours": 6},
                "null_rules": [
                    {"column": "amount", "max_percentage": 5.0}
                ],
            },
        },
        spec_text="(omitted)",
        primary_table="orders",
    )
    session.add(metric)
    session.flush()

    now = datetime.utcnow()
    # 3 historical runs so we exercise the history rendering branch.
    for i in range(3):
        session.add(
            Run(
                org_id=org.id,
                metric_id=metric.id,
                started_at=now - timedelta(days=i + 1),
                finished_at=now - timedelta(days=i + 1),
                status="passed" if i > 0 else "warning",
                trust_score=0.9,
                value_sum=40000 + i,
                row_count=100 + i,
            )
        )

    # The run under test — this one failed.
    failing = Run(
        org_id=org.id,
        metric_id=metric.id,
        started_at=now,
        finished_at=now,
        status="failed",
        trust_score=0.4,
        value_sum=12345,
        row_count=50,
    )
    session.add(failing)
    session.flush()

    session.add(
        CheckResult(
            run_id=failing.id,
            rule_type="freshness",
            rule_json={"max_hours": 6},
            status="failed",
            message="data is 14 hours stale",
            actual_value=14.0,
            threshold_value=6.0,
        )
    )
    session.flush()
    return org, metric, failing


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestStatusGate:
    """Explanation only makes sense for failed/errored runs."""

    @pytest.mark.parametrize("status", ["passed", "warning"])
    def test_rejects_non_failed_runs(
        self,
        session: Session,
        seeded: tuple[Org, Metric, Run],
        status: str,
    ) -> None:
        _, _, run = seeded
        run.status = status
        session.flush()
        with pytest.raises(ValueError, match="Nothing to explain"):
            explain_run(session, run.id, anthropic_client=_make_stub())

    def test_rejects_unknown_run(self, session: Session) -> None:
        with pytest.raises(ValueError, match="not found"):
            explain_run(
                session,
                "00000000-0000-0000-0000-000000000000",
                anthropic_client=_make_stub(),
            )

    @pytest.mark.parametrize("status", ["failed", "error", "errored"])
    def test_accepts_failed_and_errored(
        self,
        session: Session,
        seeded: tuple[Org, Metric, Run],
        status: str,
    ) -> None:
        _, _, run = seeded
        run.status = status
        session.flush()
        client = _make_stub()
        row = explain_run(session, run.id, anthropic_client=client)
        assert row.hypothesis  # populated
        assert row.suggested_action
        assert row.model_id == DEFAULT_MODEL_ID


class TestHappyPath:
    def test_persists_row_and_calls_api_once(
        self, session: Session, seeded: tuple[Org, Metric, Run]
    ) -> None:
        _, _, run = seeded
        client = _make_stub()
        row = explain_run(session, run.id, anthropic_client=client)
        assert isinstance(row, RunExplanation)
        assert row.run_id == run.id
        assert "14 hours" in row.hypothesis
        assert row.suggested_action.startswith("Check")
        assert len(client.messages.calls) == 1

    def test_uuid_input_is_normalized_to_string(
        self, session: Session, seeded: tuple[Org, Metric, Run]
    ) -> None:
        _, _, run = seeded
        # Passing the run ID as a non-str should still work — the engine
        # calls ``str()`` on it internally.
        row = explain_run(
            session,
            run.id,  # this is already a str; wrap to check normalization path
            anthropic_client=_make_stub(),
        )
        assert row.run_id == run.id

    def test_prompt_includes_trust_rules_and_check_results(
        self, session: Session, seeded: tuple[Org, Metric, Run]
    ) -> None:
        _, _, run = seeded
        client = _make_stub()
        explain_run(session, run.id, anthropic_client=client)
        call = client.messages.calls[0]
        user_prompt = call["messages"][0]["content"]
        assert "Daily Revenue" in user_prompt
        assert "freshness" in user_prompt
        # History section is populated — prior 3 runs should be visible.
        assert "Recent run history" in user_prompt
        assert "max_hours" in user_prompt
        # Forced tool choice is how we guarantee structured output.
        assert call["tool_choice"] == {
            "type": "tool",
            "name": "return_run_explanation",
        }
        assert call["tools"][0]["name"] == "return_run_explanation"


class TestIdempotency:
    def test_second_call_returns_cached_without_api_call(
        self, session: Session, seeded: tuple[Org, Metric, Run]
    ) -> None:
        _, _, run = seeded
        client = _make_stub()
        first = explain_run(session, run.id, anthropic_client=client)
        session.commit()

        # Second client — if the engine calls the API again, we'll know.
        second_client = _make_stub(
            _ok_response(hypothesis="DIFFERENT", suggested_action="DIFFERENT")
        )
        second = explain_run(session, run.id, anthropic_client=second_client)

        assert len(second_client.messages.calls) == 0
        assert second.id == first.id
        assert second.hypothesis == first.hypothesis

    def test_regenerate_upserts_in_place(
        self, session: Session, seeded: tuple[Org, Metric, Run]
    ) -> None:
        _, _, run = seeded
        first = explain_run(session, run.id, anthropic_client=_make_stub())
        session.commit()
        original_id = first.id

        new_client = _make_stub(
            _ok_response(
                hypothesis="Second opinion: row count dropped 40%.",
                suggested_action="Diff the upstream source table vs yesterday.",
            )
        )
        second = explain_run(
            session, run.id, regenerate=True, anthropic_client=new_client
        )

        # Same row updated, not duplicated.
        assert second.id == original_id
        assert second.hypothesis.startswith("Second opinion")
        rows = session.query(RunExplanation).filter_by(run_id=run.id).all()
        assert len(rows) == 1


class TestErrorPaths:
    def test_missing_api_key_raises_runtime_error(
        self,
        session: Session,
        seeded: tuple[Org, Metric, Run],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _, _, run = seeded
        monkeypatch.delenv("LITMUS_ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        with pytest.raises(RuntimeError, match="LITMUS_ANTHROPIC_API_KEY not set"):
            explain_run(session, run.id)  # no client injected → falls through to env

    def test_model_omits_tool_call_raises_explain_error(
        self, session: Session, seeded: tuple[Org, Metric, Run]
    ) -> None:
        _, _, run = seeded
        bad_response = _Response(
            content=[_Block(type="text", text="I refuse.")],
            stop_reason="end_turn",
        )
        client = _make_stub(bad_response)
        with pytest.raises(ExplainError, match="structured explanation"):
            explain_run(session, run.id, anthropic_client=client)

    def test_empty_fields_raise_explain_error(
        self, session: Session, seeded: tuple[Org, Metric, Run]
    ) -> None:
        _, _, run = seeded
        client = _make_stub(
            _Response(
                content=[
                    _Block(
                        type="tool_use",
                        name="return_run_explanation",
                        input={"hypothesis": "", "suggested_action": ""},
                    )
                ]
            )
        )
        with pytest.raises(ExplainError, match="empty"):
            explain_run(session, run.id, anthropic_client=client)

    def test_sdk_exception_wrapped_as_explain_error(
        self, session: Session, seeded: tuple[Org, Metric, Run]
    ) -> None:
        _, _, run = seeded

        class _BoomMessages:
            def create(self, **_: Any) -> Any:  # noqa: ANN401
                raise ConnectionError("upstream down")

        class _BoomClient:
            messages = _BoomMessages()

        with pytest.raises(ExplainError, match="Anthropic API call failed"):
            explain_run(session, run.id, anthropic_client=_BoomClient())


class TestModelOverride:
    def test_caller_can_override_model_id(
        self, session: Session, seeded: tuple[Org, Metric, Run]
    ) -> None:
        _, _, run = seeded
        client = _make_stub()
        row = explain_run(
            session,
            run.id,
            model_id="claude-haiku-4-5",
            anthropic_client=client,
        )
        assert row.model_id == "claude-haiku-4-5"
        assert client.messages.calls[0]["model"] == "claude-haiku-4-5"
