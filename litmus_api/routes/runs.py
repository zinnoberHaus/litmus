from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from litmus_api.deps import current_org, db_session
from litmus_api.models import CheckResult, Metric, Org, Run, RunExplanation

router = APIRouter(tags=["runs"])


class RunExplanationOut(BaseModel):
    """Response body for ``POST /runs/{id}/explain`` and the GET sibling."""

    # ``model_id`` collides with Pydantic v2's protected ``model_`` prefix;
    # unset the protection for this model so we can keep the DB column name.
    model_config = {"protected_namespaces": ()}

    id: str
    run_id: str
    hypothesis: str
    suggested_action: str
    model_id: str
    created_at: datetime


class CheckResultIn(BaseModel):
    rule_type: str
    rule: dict[str, Any] = Field(default_factory=dict)
    status: str
    message: str | None = None
    actual_value: float | None = None
    threshold_value: float | None = None
    duration_ms: int | None = None


class RunIn(BaseModel):
    metric_slug: str | None = None
    metric_id: str | None = None
    status: str
    trust_score: float | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    commit_sha: str | None = None
    ci_run_id: str | None = None
    triggered_by: str = "cli"
    value_sum: float | None = None
    row_count: int | None = None
    schema_fingerprint: str | None = None
    column_means: dict[str, float] | None = None
    check_results: list[CheckResultIn] = Field(default_factory=list)


class RunOut(BaseModel):
    id: str
    metric_id: str
    status: str
    trust_score: float | None
    started_at: datetime
    finished_at: datetime | None
    check_results: list[dict[str, Any]]


def _resolve_metric(
    session: Session, org: Org, slug: str | None, metric_id: str | None
) -> Metric:
    if metric_id:
        m = session.query(Metric).filter_by(id=metric_id, org_id=org.id).one_or_none()
        if m:
            return m
    if slug:
        m = session.query(Metric).filter_by(slug=slug, org_id=org.id).one_or_none()
        if m:
            return m
    raise HTTPException(
        status.HTTP_404_NOT_FOUND,
        "metric not found (pass metric_id or metric_slug; upsert the metric first)",
    )


@router.post("/runs", response_model=RunOut, status_code=status.HTTP_201_CREATED)
def create_run(
    payload: RunIn,
    org: Org = Depends(current_org),
    session: Session = Depends(db_session),
) -> RunOut:
    metric = _resolve_metric(session, org, payload.metric_slug, payload.metric_id)
    now = datetime.utcnow()
    run = Run(
        org_id=org.id,
        metric_id=metric.id,
        started_at=payload.started_at or now,
        finished_at=payload.finished_at or now,
        status=payload.status,
        trust_score=payload.trust_score,
        commit_sha=payload.commit_sha,
        ci_run_id=payload.ci_run_id,
        triggered_by=payload.triggered_by,
        value_sum=payload.value_sum,
        row_count=payload.row_count,
        schema_fingerprint=payload.schema_fingerprint,
        column_means_json=payload.column_means,
    )
    session.add(run)
    session.flush()

    for r in payload.check_results:
        session.add(
            CheckResult(
                run_id=run.id,
                rule_type=r.rule_type,
                rule_json=r.rule,
                status=r.status,
                message=r.message,
                actual_value=r.actual_value,
                threshold_value=r.threshold_value,
                duration_ms=r.duration_ms,
            )
        )
    session.flush()

    out = RunOut(
        id=run.id,
        metric_id=metric.id,
        status=run.status,
        trust_score=float(run.trust_score) if run.trust_score is not None else None,
        started_at=run.started_at,
        finished_at=run.finished_at,
        check_results=[
            {
                "rule_type": r.rule_type,
                "status": r.status,
                "message": r.message,
                "actual_value": float(r.actual_value)
                if r.actual_value is not None
                else None,
                "threshold_value": float(r.threshold_value)
                if r.threshold_value is not None
                else None,
            }
            for r in run.results
        ],
    )
    session.commit()
    return out


def _to_explanation_out(row: RunExplanation) -> RunExplanationOut:
    return RunExplanationOut(
        id=row.id,
        run_id=row.run_id,
        hypothesis=row.hypothesis,
        suggested_action=row.suggested_action,
        model_id=row.model_id,
        created_at=row.created_at,
    )


@router.post(
    "/runs/{run_id}/explain",
    response_model=RunExplanationOut,
    status_code=status.HTTP_200_OK,
)
def explain_run_route(
    run_id: str,
    regenerate: bool = False,
    org: Org = Depends(current_org),
    session: Session = Depends(db_session),
) -> RunExplanationOut:
    """Generate (or return) an AI hypothesis for a failed/errored run.

    Blocking up to ~30s on the upstream Anthropic call. Idempotent — the first
    call persists a :class:`RunExplanation` row, subsequent calls short-circuit
    to the cached row unless ``?regenerate=true`` is passed.
    """
    run = session.query(Run).filter_by(id=run_id, org_id=org.id).one_or_none()
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"run {run_id} not found")

    # Heavy import lazy — don't pull anthropic into the default FastAPI boot.
    from litmus_api.ai.explain import ExplainError, explain_run  # noqa: PLC0415

    try:
        row = explain_run(session, run_id, regenerate=regenerate)
    except ValueError as exc:
        # Bad input — the run is passed/warning, or missing.
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except ExplainError as exc:
        # Upstream model call failed or returned garbage. Checked BEFORE
        # RuntimeError because ``ExplainError`` inherits from it.
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    except RuntimeError as exc:
        # API key / SDK missing — operator configuration problem.
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            f"AI explanations not configured: {exc}",
        ) from exc

    session.commit()
    return _to_explanation_out(row)


@router.get(
    "/runs/{run_id}/explanation",
    response_model=RunExplanationOut,
)
def get_run_explanation(
    run_id: str,
    org: Org = Depends(current_org),
    session: Session = Depends(db_session),
) -> RunExplanationOut:
    """Return the cached AI explanation for a run, or 404 if none exists yet."""
    run = session.query(Run).filter_by(id=run_id, org_id=org.id).one_or_none()
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"run {run_id} not found")
    row = (
        session.query(RunExplanation).filter_by(run_id=run_id).one_or_none()
    )
    if row is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "no explanation generated yet — POST /runs/{id}/explain first",
        )
    return _to_explanation_out(row)
