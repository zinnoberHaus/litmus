from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from litmus.parser.errors import LitmusParseError
from litmus.parser.parser import parse_metric_string
from litmus_api.deps import current_org, db_session
from litmus_api.models import (
    EmbedKey,
    LineageEdge,
    LineageNode,
    Metric,
    MetricRevision,
    Org,
    Run,
    generate_embed_token,
)
from litmus_api.serializers import slugify, spec_to_dict

router = APIRouter(tags=["metrics"])


class MetricUpsertIn(BaseModel):
    spec_text: str = Field(..., min_length=1)
    slug: str | None = None
    source_repo: str | None = None
    source_path: str | None = None
    source_sha: str | None = None
    author: str | None = None


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
    revision_count: int = 0


class RevisionOut(BaseModel):
    id: str
    metric_id: str
    spec_text: str
    spec: dict[str, Any]
    source_sha: str | None = None
    author: str | None = None
    created_at: datetime


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


def _latest_revision(session: Session, metric_id: str) -> MetricRevision | None:
    return (
        session.query(MetricRevision)
        .filter_by(metric_id=metric_id)
        .order_by(desc(MetricRevision.created_at), desc(MetricRevision.id))
        .first()
    )


def _revision_count(session: Session, metric_id: str) -> int:
    return int(
        session.query(func.count(MetricRevision.id))
        .filter_by(metric_id=metric_id)
        .scalar()
        or 0
    )


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
        revision_count=_revision_count(session, metric.id),
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


def _perform_upsert(
    session: Session,
    org: Org,
    payload: MetricUpsertIn,
) -> Metric:
    """Parse ``payload.spec_text`` and upsert a :class:`Metric` for ``org``.

    This is the shared core used by both the HTTP route (``POST /metrics``)
    and the GitHub webhook ingestor — keeping the upsert logic in one place
    means a ``.metric`` edit lands the same way whether it came in via the
    CLI push or via a ``git push``. The caller is responsible for committing
    (the HTTP route commits once per request; the webhook commits once per
    push event after it has processed every changed file).

    Raises :class:`LitmusParseError` if ``spec_text`` cannot be parsed — the
    caller decides whether that is a 422 (HTTP) or an ``ignored`` entry in
    the webhook response.
    """
    spec = parse_metric_string(payload.spec_text)

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
        session.flush()
        # First upsert always records a revision — this seeds the history
        # so even metrics that never change have an audit trail.
        _record_revision(session, metric, payload, spec_dict, force=True)
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
        # Only record a revision when the spec text actually changed — identical
        # re-upserts (common in CI) would otherwise clutter the log.
        _record_revision(session, metric, payload, spec_dict, force=False)

    session.flush()
    return metric


@router.post("/metrics", response_model=MetricOut, status_code=status.HTTP_201_CREATED)
def upsert_metric(
    payload: MetricUpsertIn,
    org: Org = Depends(current_org),
    session: Session = Depends(db_session),
) -> MetricOut:
    try:
        metric = _perform_upsert(session, org, payload)
    except LitmusParseError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    out = _to_out(session, metric)
    session.commit()
    return out


def _record_revision(
    session: Session,
    metric: Metric,
    payload: MetricUpsertIn,
    spec_dict: dict[str, Any],
    *,
    force: bool,
) -> MetricRevision | None:
    """Insert a MetricRevision row if the spec has meaningfully changed.

    ``force=True`` always inserts (used on first upsert so the history is
    seeded). ``force=False`` compares against the most recent revision's
    ``spec_text`` and skips the write if they match.
    """
    if not force:
        latest = _latest_revision(session, metric.id)
        if latest is not None and latest.spec_text == payload.spec_text:
            return None

    revision = MetricRevision(
        metric_id=metric.id,
        spec_text=payload.spec_text,
        spec_json=spec_dict,
        source_sha=payload.source_sha,
        author=payload.author,
    )
    session.add(revision)
    session.flush()
    return revision


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


_REVISION_LIST_LIMIT = 30


@router.get("/metrics/{metric_id}/revisions", response_model=list[RevisionOut])
def list_revisions(
    metric_id: str,
    org: Org = Depends(current_org),
    session: Session = Depends(db_session),
) -> list[RevisionOut]:
    """Return the last ``_REVISION_LIST_LIMIT`` spec revisions for a metric.

    Results are ordered oldest-last (i.e. the newest revision is the final
    entry in the list) so consumers can render a top-to-bottom timeline
    without reversing client-side.
    """
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

    # Pull the newest N by created_at, then reverse so the response is
    # oldest-first (matches the contract in the task spec).
    recent = (
        session.query(MetricRevision)
        .filter_by(metric_id=metric.id)
        .order_by(desc(MetricRevision.created_at), desc(MetricRevision.id))
        .limit(_REVISION_LIST_LIMIT)
        .all()
    )
    revisions = list(reversed(recent))
    return [
        RevisionOut(
            id=rev.id,
            metric_id=rev.metric_id,
            spec_text=rev.spec_text,
            spec=rev.spec_json,
            source_sha=rev.source_sha,
            author=rev.author,
            created_at=rev.created_at,
        )
        for rev in revisions
    ]


# ── Lineage ────────────────────────────────────────────────────────────


class LineageNodeIn(BaseModel):
    """Incoming node payload. ``id`` is the client-supplied graph key
    (e.g. a dbt unique_id) used to wire edges; it is *not* the DB row id."""

    id: str
    label: str
    kind: str  # "source" | "model" | "metric"


class LineageEdgeIn(BaseModel):
    """Accept ``{"from": ..., "to": ...}`` — the idiomatic graph shape —
    while avoiding Python's ``from`` keyword collision via alias."""

    from_: str = Field(alias="from")
    to: str

    model_config = {"populate_by_name": True}


class LineageIn(BaseModel):
    nodes: list[LineageNodeIn] = Field(default_factory=list)
    edges: list[LineageEdgeIn] = Field(default_factory=list)


class LineageNodeOut(BaseModel):
    id: str
    label: str
    kind: str


class LineageOut(BaseModel):
    """We serialize edges as plain dicts so the wire format is exactly
    ``{"from": ..., "to": ...}`` without Pydantic alias gymnastics on
    response serialization."""

    nodes: list[LineageNodeOut]
    edges: list[dict[str, str]]


_ALLOWED_KINDS = {"source", "model", "metric"}


def _resolve_metric(
    session: Session, org: Org, metric_id: str
) -> Metric:
    """Look up a metric by UUID or slug, filtered to ``org``."""
    metric = (
        session.query(Metric)
        .filter_by(id=metric_id, org_id=org.id, deleted_at=None)
        .one_or_none()
    )
    if metric is None:
        metric = (
            session.query(Metric)
            .filter_by(slug=metric_id, org_id=org.id, deleted_at=None)
            .one_or_none()
        )
    if metric is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "metric not found")
    return metric


@router.post("/metrics/{metric_id}/lineage", response_model=LineageOut)
def upsert_lineage(
    metric_id: str,
    payload: LineageIn,
    org: Org = Depends(current_org),
    session: Session = Depends(db_session),
) -> LineageOut:
    """Replace a metric's lineage subgraph atomically.

    We delete existing nodes + edges first (cascade cleans edges when a node
    goes) then re-insert. This keeps ``litmus import-dbt --push`` idempotent
    — running it twice produces the same graph, not a doubled one.
    """
    metric = _resolve_metric(session, org, metric_id)

    # Validate up front so a bad kind doesn't half-write the graph.
    for node in payload.nodes:
        if node.kind not in _ALLOWED_KINDS:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"invalid kind {node.kind!r} (allowed: {sorted(_ALLOWED_KINDS)})",
            )

    client_ids = {n.id for n in payload.nodes}
    for edge in payload.edges:
        if edge.from_ not in client_ids or edge.to not in client_ids:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "edge references a node that is not in the payload",
            )

    # Wipe the existing subgraph. Edges first (FK to nodes, cascade handles
    # this too but being explicit keeps the intent obvious).
    session.query(LineageEdge).filter_by(metric_id=metric.id).delete()
    session.query(LineageNode).filter_by(metric_id=metric.id).delete()
    session.flush()

    # Insert nodes, keeping a client_id → db_id map so we can wire edges.
    id_map: dict[str, str] = {}
    for node in payload.nodes:
        row = LineageNode(
            metric_id=metric.id,
            label=node.label,
            kind=node.kind,
        )
        session.add(row)
        session.flush()
        id_map[node.id] = row.id

    for edge in payload.edges:
        session.add(
            LineageEdge(
                metric_id=metric.id,
                from_node_id=id_map[edge.from_],
                to_node_id=id_map[edge.to],
            )
        )
    session.flush()
    session.commit()

    # Round-trip back through the DB so the response shape matches GET.
    return _load_lineage(session, metric)


@router.get("/metrics/{metric_id}/lineage", response_model=LineageOut)
def get_lineage(
    metric_id: str,
    org: Org = Depends(current_org),
    session: Session = Depends(db_session),
) -> LineageOut:
    """Return the stored lineage for a metric, or a 2-node spec-derived stub
    if nothing has been imported yet.

    The stub keeps the UI happy — an empty lineage block on the detail page
    looks broken; a ``source → metric`` placeholder communicates "lineage
    hasn't been wired yet" without rendering a blank rectangle.
    """
    metric = _resolve_metric(session, org, metric_id)
    out = _load_lineage(session, metric)
    if out.nodes:
        return out

    primary = metric.primary_table or "source_table"
    return LineageOut(
        nodes=[
            LineageNodeOut(id="src", label=primary, kind="source"),
            LineageNodeOut(id="metric", label=metric.name, kind="metric"),
        ],
        edges=[{"from": "src", "to": "metric"}],
    )


def _load_lineage(session: Session, metric: Metric) -> LineageOut:
    """Pull the stored subgraph out of the DB and reshape it for the API.

    We expose the node's DB row id as the public ``id`` — edges reference
    node ids, so whatever the client sees on GET must round-trip through
    POST unchanged.
    """
    nodes = (
        session.query(LineageNode)
        .filter_by(metric_id=metric.id)
        .order_by(LineageNode.created_at, LineageNode.id)
        .all()
    )
    edges = (
        session.query(LineageEdge)
        .filter_by(metric_id=metric.id)
        .order_by(LineageEdge.created_at, LineageEdge.id)
        .all()
    )
    return LineageOut(
        nodes=[
            LineageNodeOut(id=n.id, label=n.label, kind=n.kind)
            for n in nodes
        ],
        edges=[
            {"from": e.from_node_id, "to": e.to_node_id}
            for e in edges
        ],
    )
