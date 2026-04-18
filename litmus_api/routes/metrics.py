from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import desc
from sqlalchemy.orm import Session

from litmus.parser.errors import LitmusParseError
from litmus.parser.parser import parse_metric_string
from litmus_api.deps import current_org, db_session
from litmus_api.models import EmbedKey, Metric, Org, Run, generate_embed_token
from litmus_api.serializers import slugify, spec_to_dict

router = APIRouter(tags=["metrics"])


class MetricUpsertIn(BaseModel):
    spec_text: str = Field(..., min_length=1)
    slug: str | None = None
    source_repo: str | None = None
    source_path: str | None = None
    source_sha: str | None = None


class MetricOut(BaseModel):
    id: str
    slug: str
    name: str
    description: str | None = None
    owner_email: str | None = None
    primary_table: str | None = None
    spec: dict[str, Any]
    source_repo: str | None = None
    source_path: str | None = None
    source_sha: str | None = None
    created_at: datetime
    updated_at: datetime
    latest_run: dict[str, Any] | None = None
    embed_token: str | None = None


def _latest_run_payload(session: Session, metric: Metric) -> dict[str, Any] | None:
    run: Run | None = (
        session.query(Run)
        .filter_by(metric_id=metric.id)
        .order_by(desc(Run.started_at))
        .first()
    )
    if run is None:
        return None
    return {
        "id": run.id,
        "status": run.status,
        "trust_score": float(run.trust_score) if run.trust_score is not None else None,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "value_sum": float(run.value_sum) if run.value_sum is not None else None,
        "row_count": run.row_count,
    }


def _embed_token(session: Session, metric: Metric) -> str:
    key: EmbedKey | None = (
        session.query(EmbedKey)
        .filter_by(metric_id=metric.id, revoked_at=None)
        .first()
    )
    if key is None:
        key = EmbedKey(
            org_id=metric.org_id,
            metric_id=metric.id,
            token=generate_embed_token(),
        )
        session.add(key)
        session.flush()
    return key.token


def _to_out(session: Session, metric: Metric) -> MetricOut:
    return MetricOut(
        id=metric.id,
        slug=metric.slug,
        name=metric.name,
        description=metric.description,
        owner_email=metric.owner_email,
        primary_table=metric.primary_table,
        spec=metric.spec_json,
        source_repo=metric.source_repo,
        source_path=metric.source_path,
        source_sha=metric.source_sha,
        created_at=metric.created_at,
        updated_at=metric.updated_at,
        latest_run=_latest_run_payload(session, metric),
        embed_token=_embed_token(session, metric),
    )


@router.get("/metrics", response_model=list[MetricOut])
def list_metrics(
    org: Org = Depends(current_org),
    session: Session = Depends(db_session),
) -> list[MetricOut]:
    metrics = (
        session.query(Metric)
        .filter_by(org_id=org.id, deleted_at=None)
        .order_by(Metric.name.asc())
        .all()
    )
    out = [_to_out(session, m) for m in metrics]
    session.commit()
    return out


@router.post("/metrics", response_model=MetricOut, status_code=status.HTTP_201_CREATED)
def upsert_metric(
    payload: MetricUpsertIn,
    org: Org = Depends(current_org),
    session: Session = Depends(db_session),
) -> MetricOut:
    try:
        spec = parse_metric_string(payload.spec_text)
    except LitmusParseError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    slug = (payload.slug or slugify(spec.name)).lower()
    existing = (
        session.query(Metric).filter_by(org_id=org.id, slug=slug).one_or_none()
    )

    primary_table = spec.sources[0] if spec.sources else None
    spec_dict = spec_to_dict(spec)

    if existing is None:
        metric = Metric(
            org_id=org.id,
            slug=slug,
            name=spec.name,
            description=spec.description,
            owner_email=spec.owner,
            primary_table=primary_table,
            spec_json=spec_dict,
            spec_text=payload.spec_text,
            source_repo=payload.source_repo,
            source_path=payload.source_path,
            source_sha=payload.source_sha,
        )
        session.add(metric)
    else:
        metric = existing
        metric.name = spec.name
        metric.description = spec.description
        metric.owner_email = spec.owner
        metric.primary_table = primary_table
        metric.spec_json = spec_dict
        metric.spec_text = payload.spec_text
        if payload.source_repo is not None:
            metric.source_repo = payload.source_repo
        if payload.source_path is not None:
            metric.source_path = payload.source_path
        if payload.source_sha is not None:
            metric.source_sha = payload.source_sha

    session.flush()
    out = _to_out(session, metric)
    session.commit()
    return out


@router.get("/metrics/{metric_id}", response_model=MetricOut)
def get_metric(
    metric_id: str,
    org: Org = Depends(current_org),
    session: Session = Depends(db_session),
) -> MetricOut:
    metric = (
        session.query(Metric)
        .filter_by(id=metric_id, org_id=org.id, deleted_at=None)
        .one_or_none()
    )
    if metric is None:
        # allow slug lookup for friendly URLs
        metric = (
            session.query(Metric)
            .filter_by(slug=metric_id, org_id=org.id, deleted_at=None)
            .one_or_none()
        )
    if metric is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "metric not found")
    out = _to_out(session, metric)
    session.commit()
    return out


@router.get("/metrics/{metric_id}/history")
def get_history(
    metric_id: str,
    limit: int = 50,
    org: Org = Depends(current_org),
    session: Session = Depends(db_session),
) -> dict[str, Any]:
    metric = (
        session.query(Metric)
        .filter_by(id=metric_id, org_id=org.id, deleted_at=None)
        .one_or_none()
    )
    if metric is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "metric not found")
    runs = (
        session.query(Run)
        .filter_by(metric_id=metric.id)
        .order_by(desc(Run.started_at))
        .limit(max(1, min(limit, 500)))
        .all()
    )
    return {
        "metric_id": metric.id,
        "runs": [
            {
                "id": r.id,
                "status": r.status,
                "trust_score": float(r.trust_score) if r.trust_score is not None else None,
                "started_at": r.started_at,
                "finished_at": r.finished_at,
                "value_sum": float(r.value_sum) if r.value_sum is not None else None,
                "row_count": r.row_count,
                "commit_sha": r.commit_sha,
            }
            for r in runs
        ],
    }
