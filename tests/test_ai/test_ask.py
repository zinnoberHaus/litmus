"""Unit tests for :mod:`litmus_api.ai.ask`.

All tests use a stub Anthropic client and a stub warehouse connector — we
never touch Claude or a real warehouse. The production path reads
``LITMUS_ANTHROPIC_API_KEY`` from the environment and builds its own client;
tests bypass that by passing ``anthropic_client=...`` directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from litmus_api.ai.ask import (
    DEFAULT_MODEL_ID,
    AskAnswer,
    AskError,
    answer_question,
)
from litmus_api.models import Base, Metric, Org, Run

# ---------------------------------------------------------------------------
# Stub Anthropic client
# ---------------------------------------------------------------------------


@dataclass
class _Block:
    type: str
    name: str | None = None
    input: dict[str, Any] | None = None


@dataclass
class _Response:
    content: list[_Block]
    stop_reason: str = "tool_use"


@dataclass
class _Messages:
    response: _Response
    calls: list[dict[str, Any]] = field(default_factory=list)

    def create(self, **kwargs: Any) -> _Response:
        self.calls.append(kwargs)
        return self.response


@dataclass
class _StubClient:
    messages: _Messages


def _intent_response(
    metric_slug: str = "revenue",
    time_window: str = "last_period",
    confidence: float = 0.95,
    unresolved_reason: str = "",
) -> _Response:
    return _Response(
        content=[
            _Block(
                type="tool_use",
                name="resolve_metric_intent",
                input={
                    "metric_slug": metric_slug,
                    "time_window": time_window,
                    "confidence": confidence,
                    "unresolved_reason": unresolved_reason,
                    "filters": [],
                },
            )
        ]
    )


def _make_stub(response: _Response | None = None) -> _StubClient:
    return _StubClient(messages=_Messages(response or _intent_response()))


# ---------------------------------------------------------------------------
# Stub warehouse connector
# ---------------------------------------------------------------------------


@dataclass
class _StubConnector:
    """Captures every ``execute_query`` call so tests can assert on the SQL."""

    rows: list[dict[str, Any]] = field(
        default_factory=lambda: [{"metric_value": 4_218_430.0}]
    )
    queries: list[str] = field(default_factory=list)
    raise_on_query: Exception | None = None

    def connect(self) -> None:
        return None

    def close(self) -> None:
        return None

    def execute_query(self, sql: str) -> list[dict[str, Any]]:
        self.queries.append(sql)
        if self.raise_on_query is not None:
            raise self.raise_on_query
        return list(self.rows)


# ---------------------------------------------------------------------------
# Fixtures
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
def org_with_metrics(session: Session) -> tuple[Org, Metric]:
    """One org, one metric, one passed run. The minimum viable catalog."""
    org = Org(slug="default", name="Default")
    session.add(org)
    session.flush()

    metric = Metric(
        org_id=org.id,
        slug="revenue",
        name="Monthly Revenue",
        description="Sum of completed orders per month.",
        spec_json={
            "sources": ["orders"],
            "trust": {
                "freshness": {"max_hours": 6},
            },
        },
        spec_text="(omitted)",
        primary_table="orders",
        owner_email="finance@example.com",
    )
    session.add(metric)
    session.flush()

    run = Run(
        org_id=org.id,
        metric_id=metric.id,
        started_at=datetime.utcnow() - timedelta(hours=1),
        finished_at=datetime.utcnow(),
        status="passed",
        trust_score=0.95,
        value_sum=4_218_430.0,
        row_count=1234,
    )
    session.add(run)
    session.flush()
    return org, metric


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestHappyPath:
    def test_resolves_and_answers(
        self,
        session: Session,
        org_with_metrics: tuple[Org, Metric],
    ) -> None:
        org, _metric = org_with_metrics
        connector = _StubConnector()
        client = _make_stub()

        result = answer_question(
            session,
            org,
            "what was revenue last month?",
            connector=connector,
            anthropic_client=client,
        )

        assert isinstance(result, AskAnswer)
        assert result.metric_slug == "revenue"
        assert result.metric_name == "Monthly Revenue"
        assert result.value == pytest.approx(4_218_430.0)
        assert result.trust_status == "passed"
        assert result.time_window == "last_period"
        assert result.model_id == DEFAULT_MODEL_ID
        # Answer string carries the formatted value + the trust clause.
        assert "4,218,430" in result.answer
        assert "green" in result.answer

    def test_executes_templated_sql_against_warehouse(
        self,
        session: Session,
        org_with_metrics: tuple[Org, Metric],
    ) -> None:
        org, _metric = org_with_metrics
        connector = _StubConnector()
        answer_question(
            session,
            org,
            "what was revenue last month?",
            connector=connector,
            anthropic_client=_make_stub(),
        )
        assert len(connector.queries) == 1
        sql = connector.queries[0]
        # SQL is server-templated — it must reference the primary_table and
        # the default timestamp column, NOT anything Claude returned.
        assert "FROM orders" in sql
        assert "SUM(amount)" in sql
        assert "updated_at" in sql
        assert "LIMIT 1" in sql

    def test_metric_slug_skips_claude(
        self,
        session: Session,
        org_with_metrics: tuple[Org, Metric],
    ) -> None:
        """If the caller supplies ``metric_slug`` we must NOT call Claude."""
        org, _metric = org_with_metrics
        connector = _StubConnector()
        client = _make_stub()

        result = answer_question(
            session,
            org,
            "how is revenue?",
            metric_slug="revenue",
            connector=connector,
            anthropic_client=client,
        )

        # Zero invocations of Claude.
        assert client.messages.calls == []
        # But we still ran SQL + returned a sensible answer.
        assert len(connector.queries) == 1
        assert result.metric_slug == "revenue"
        assert result.trust_status == "passed"

    def test_no_catalog_prompt_leaks_warehouse_data(
        self,
        session: Session,
        org_with_metrics: tuple[Org, Metric],
    ) -> None:
        """Privacy invariant: Claude's prompt contains catalog fields only —
        no SQL, no row data, no computed value."""
        org, _metric = org_with_metrics
        connector = _StubConnector(rows=[{"metric_value": 9_999.0}])
        client = _make_stub()

        answer_question(
            session,
            org,
            "what was revenue last month?",
            connector=connector,
            anthropic_client=client,
        )

        assert len(client.messages.calls) == 1
        messages = client.messages.calls[0]["messages"]
        prompt = messages[0]["content"]
        # The computed value must never appear in the Claude prompt.
        assert "9999" not in prompt
        assert "9,999" not in prompt
        # The SQL we generated server-side must never appear in the prompt.
        assert "SELECT SUM" not in prompt
        # But the catalog fields MUST appear.
        assert "revenue" in prompt
        assert "Monthly Revenue" in prompt


# ---------------------------------------------------------------------------
# Trust status derivation
# ---------------------------------------------------------------------------


class TestTrustStatus:
    def test_no_runs_is_unknown(
        self,
        session: Session,
        org_with_metrics: tuple[Org, Metric],
    ) -> None:
        org, metric = org_with_metrics
        # Drop every run so the metric has no trust signal.
        session.query(Run).filter_by(metric_id=metric.id).delete()
        session.flush()

        result = answer_question(
            session,
            org,
            "revenue",
            metric_slug="revenue",
            connector=_StubConnector(),
            anthropic_client=_make_stub(),
        )
        assert result.trust_status == "unknown"
        assert result.run_id is None
        assert "unverified" in result.answer.lower()

    @pytest.mark.parametrize(
        "status,expected",
        [
            ("passed", "passed"),
            ("warning", "warning"),
            ("failed", "failed"),
            ("error", "error"),
            ("errored", "error"),
            ("weird", "unknown"),
        ],
    )
    def test_run_status_is_normalized(
        self,
        session: Session,
        org_with_metrics: tuple[Org, Metric],
        status: str,
        expected: str,
    ) -> None:
        org, metric = org_with_metrics
        run = session.query(Run).filter_by(metric_id=metric.id).first()
        assert run is not None
        run.status = status
        session.flush()

        result = answer_question(
            session,
            org,
            "revenue",
            metric_slug="revenue",
            connector=_StubConnector(),
            anthropic_client=_make_stub(),
        )
        assert result.trust_status == expected


# ---------------------------------------------------------------------------
# Unresolved / ambiguous paths
# ---------------------------------------------------------------------------


class TestUnresolved:
    def test_low_confidence_raises_unresolved(
        self,
        session: Session,
        org_with_metrics: tuple[Org, Metric],
    ) -> None:
        org, _metric = org_with_metrics
        client = _make_stub(
            _intent_response(
                metric_slug="",
                time_window="last_period",
                confidence=0.2,
                unresolved_reason="Nothing in the catalog fits.",
            )
        )

        with pytest.raises(AskError) as exc_info:
            answer_question(
                session,
                org,
                "what's our NPS score?",
                connector=_StubConnector(),
                anthropic_client=client,
            )
        assert exc_info.value.code == "unresolved"
        assert "catalog" in str(exc_info.value)
        # Suggestions give the UI chips something to render.
        assert exc_info.value.suggestions

    def test_invented_slug_is_rejected_as_unresolved(
        self,
        session: Session,
        org_with_metrics: tuple[Org, Metric],
    ) -> None:
        """Defense-in-depth: if Claude returns a slug not in the catalog,
        don't blindly trust it — surface as unresolved."""
        org, _metric = org_with_metrics
        client = _make_stub(
            _intent_response(metric_slug="made_up_slug", confidence=0.9)
        )

        with pytest.raises(AskError) as exc_info:
            answer_question(
                session,
                org,
                "whatever",
                connector=_StubConnector(),
                anthropic_client=client,
            )
        assert exc_info.value.code == "unresolved"

    def test_ambiguous_question_explanation_notes_confidence(
        self,
        session: Session,
        org_with_metrics: tuple[Org, Metric],
    ) -> None:
        """When Claude picks one metric with moderate confidence, the
        response's ``explanation`` must call that out for the PM to see."""
        org, _metric = org_with_metrics
        client = _make_stub(
            _intent_response(
                metric_slug="revenue", confidence=0.6
            )
        )

        result = answer_question(
            session,
            org,
            "revenue or sales?",
            connector=_StubConnector(),
            anthropic_client=client,
        )
        assert result.explanation is not None
        assert "0.60" in result.explanation or "0.6" in result.explanation


# ---------------------------------------------------------------------------
# Error surfaces
# ---------------------------------------------------------------------------


class TestErrors:
    def test_empty_question_is_bad_input(
        self,
        session: Session,
        org_with_metrics: tuple[Org, Metric],
    ) -> None:
        org, _metric = org_with_metrics
        with pytest.raises(AskError) as exc_info:
            answer_question(
                session,
                org,
                "   ",
                connector=_StubConnector(),
                anthropic_client=_make_stub(),
            )
        assert exc_info.value.code == "bad_input"

    def test_unknown_metric_slug_is_metric_not_found(
        self,
        session: Session,
        org_with_metrics: tuple[Org, Metric],
    ) -> None:
        org, _metric = org_with_metrics
        with pytest.raises(AskError) as exc_info:
            answer_question(
                session,
                org,
                "whatever",
                metric_slug="ghost_metric",
                connector=_StubConnector(),
                anthropic_client=_make_stub(),
            )
        assert exc_info.value.code == "metric_not_found"

    def test_warehouse_error_is_mapped(
        self,
        session: Session,
        org_with_metrics: tuple[Org, Metric],
    ) -> None:
        org, _metric = org_with_metrics
        connector = _StubConnector(raise_on_query=RuntimeError("pg disconnected"))

        with pytest.raises(AskError) as exc_info:
            answer_question(
                session,
                org,
                "revenue",
                metric_slug="revenue",
                connector=connector,
                anthropic_client=_make_stub(),
            )
        assert exc_info.value.code == "warehouse_unavailable"
        assert "pg disconnected" in str(exc_info.value)

    def test_empty_catalog_is_unresolved(
        self,
        session: Session,
    ) -> None:
        """No metrics → we can't answer anything; don't waste a Claude call."""
        org = Org(slug="empty", name="Empty")
        session.add(org)
        session.flush()

        with pytest.raises(AskError) as exc_info:
            answer_question(
                session,
                org,
                "whatever",
                connector=_StubConnector(),
                anthropic_client=_make_stub(),
            )
        assert exc_info.value.code == "unresolved"

    def test_missing_api_key_raises_ai_not_configured(
        self,
        session: Session,
        org_with_metrics: tuple[Org, Metric],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Default ``anthropic_client=None`` with no env key → a clear error."""
        org, _metric = org_with_metrics
        monkeypatch.delenv("LITMUS_ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        with pytest.raises(AskError) as exc_info:
            answer_question(
                session,
                org,
                "what was revenue?",
                connector=_StubConnector(),
            )
        assert exc_info.value.code == "ai_not_configured"


# ---------------------------------------------------------------------------
# SQL templating — time windows
# ---------------------------------------------------------------------------


class TestTimeWindows:
    @pytest.mark.parametrize(
        "window,expect_where",
        [
            ("all_time", False),
            ("last_7_days", True),
            ("last_30_days", True),
            ("last_period", True),
            ("current_period", True),
            ("last_quarter", True),
            ("last_year", True),
        ],
    )
    def test_where_clause_presence(
        self,
        session: Session,
        org_with_metrics: tuple[Org, Metric],
        window: str,
        expect_where: bool,
    ) -> None:
        org, _metric = org_with_metrics
        connector = _StubConnector()
        client = _make_stub(_intent_response(time_window=window))
        answer_question(
            session,
            org,
            "how about this window",
            connector=connector,
            anthropic_client=client,
        )
        sql = connector.queries[0]
        assert ("WHERE" in sql) is expect_where

    def test_no_rows_means_value_is_none(
        self,
        session: Session,
        org_with_metrics: tuple[Org, Metric],
    ) -> None:
        org, _metric = org_with_metrics
        connector = _StubConnector(rows=[{"metric_value": None}])
        result = answer_question(
            session,
            org,
            "revenue",
            metric_slug="revenue",
            connector=connector,
            anthropic_client=_make_stub(),
        )
        assert result.value is None
        assert "couldn't find a value" in result.answer
