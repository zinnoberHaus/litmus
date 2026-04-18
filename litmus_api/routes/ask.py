"""AI Q&A endpoint — ``POST /api/v1/ask``.

The PM-facing surface per REFACTOR_BLUEPRINT §2.4 / task #54. Takes a plain
English question (optionally scoped by ``metric_slug``), runs it through
:func:`litmus_api.ai.ask.answer_question`, and returns a JSON envelope the UI
``<AskPanel>`` (``ui/lib/ask.ts``) consumes verbatim.

Contract is authored in ``ui/lib/ask.ts`` — if the request/response shape
changes here, update the TypeScript types at the same time.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from litmus_api.config import get_settings
from litmus_api.deps import current_org, db_session
from litmus_api.models import Org

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ask"])


class AskContext(BaseModel):
    """Optional metadata the UI or Slack handler may attach.

    We don't currently surface any of this to Claude — it's here so v0.4
    multi-turn / personalization has a place to live without a schema change.
    """

    user: str | None = None
    channel: str | None = None
    source: str | None = None


class AskIn(BaseModel):
    question: str = Field(
        ..., min_length=1, description="The user's natural-language question."
    )
    metric_slug: str | None = Field(
        default=None,
        description=(
            "Optional — if provided, skip intent resolution and go straight "
            "to SQL templating against this metric."
        ),
    )
    context: AskContext | None = None


class AskOut(BaseModel):
    """Response shape mirrored in ``ui/lib/ask.ts::AskResponse``.

    Additive-only per the v0.3 stability bar — the UI tolerates extra keys
    and only renders what it knows.
    """

    # ``model_id`` collides with Pydantic v2's protected ``model_`` prefix;
    # opt out for this model so the field keeps its on-wire name.
    model_config = {"protected_namespaces": ()}

    answer: str
    metric_slug: str
    metric_name: str | None = None
    metric_url: str | None = None
    value: float | None = None
    trust_status: str
    definition_url: str
    explanation: str | None = None
    suggestions: list[str] | None = None
    run_id: str | None = None
    time_window: str | None = None
    model_id: str | None = None


@router.post("/ask", response_model=AskOut)
def ask(
    payload: AskIn,
    org: Org = Depends(current_org),
    session: Session = Depends(db_session),
) -> AskOut:
    """Answer a business question against the metric catalog.

    Error mapping (kept in lockstep with ``ui/lib/ask.ts::AskError``):

    * 400 — empty question or spec with no Source.
    * 404 — the caller passed an unknown ``metric_slug``.
    * 422 — Claude couldn't resolve the question; body includes top-3 slug
      suggestions for the UI chips.
    * 500 — ``LITMUS_ANTHROPIC_API_KEY`` unset / SDK missing.
    * 502 — Anthropic call failed after we reached the API.
    * 503 — warehouse query failed.
    """
    from litmus_api.ai.ask import AskError, answer_question  # noqa: PLC0415

    settings = get_settings()
    try:
        result = answer_question(
            session,
            org,
            payload.question,
            metric_slug=payload.metric_slug,
            public_url=settings.public_url,
        )
    except AskError as exc:
        raise _to_http_error(exc) from exc

    session.commit()

    return AskOut(
        answer=result.answer,
        metric_slug=result.metric_slug,
        metric_name=result.metric_name,
        metric_url=result.metric_url,
        value=result.value,
        trust_status=result.trust_status,
        definition_url=result.definition_url,
        explanation=result.explanation,
        run_id=result.run_id,
        time_window=result.time_window,
        model_id=result.model_id,
    )


def _to_http_error(exc: Any) -> HTTPException:
    """Translate ``AskError.code`` to the right HTTP status + body.

    Kept as a plain function (not a FastAPI exception handler) so the Slack
    ``app_mention`` handler can share the engine without inheriting our HTTP
    semantics.
    """
    code = getattr(exc, "code", "") or ""
    msg = str(exc) or "AI Q&A failed"
    suggestions = getattr(exc, "suggestions", None) or None

    if code == "bad_input":
        return HTTPException(status.HTTP_400_BAD_REQUEST, msg)
    if code == "metric_not_found":
        return HTTPException(status.HTTP_404_NOT_FOUND, msg)
    if code == "unresolved":
        detail: dict[str, Any] = {"message": msg, "code": "unresolved"}
        if suggestions:
            detail["suggestions"] = suggestions
        return HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail)
    if code == "ai_not_configured":
        return HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "AI Q&A is not configured. Set LITMUS_ANTHROPIC_API_KEY or install 'litmus-data[ai]'.",
        )
    if code == "ai_transport":
        return HTTPException(status.HTTP_502_BAD_GATEWAY, msg)
    if code == "warehouse_unavailable":
        return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, msg)
    return HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, msg)
