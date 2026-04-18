"""BI mapping CRUD + reconciliation endpoints.

Mounted under ``/api/v1`` from :mod:`litmus_api.main`. Kept in a separate
module from ``metrics.py`` because the BI scaffold is a self-contained
surface — mappings, reconciliations, and the trigger endpoint all speak the
same domain and share ``_resolve_metric`` via ``metrics._resolve_metric``.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import desc
from sqlalchemy.orm import Session

from litmus_api.bi import SUPPORTED_SOURCES
from litmus_api.deps import current_org, db_session
from litmus_api.jobs.reconciliation import run_reconciliation
from litmus_api.models import BIMapping, Metric, Org, Reconciliation, Run
from litmus_api.routes.metrics import _resolve_metric

router = APIRouter(tags=["bi"])


# ── Schemas ────────────────────────────────────────────────────────────


class BIMappingIn(BaseModel):
    source: str
    identifier: str


class BIMappingOut(BaseModel):
    id: str
    metric_id: str
    source: str
    identifier: str
    created_at: datetime


class ReconciliationRowOut(BaseModel):
    """One row in the reconciliation panel.

    ``source`` doubles as the display label — the UI formats it
    ("Warehouse (Litmus)" / "Looker" / "Tableau"). ``delta`` is a proportion
    (``0.023`` == 2.3%) so downstream code never has to guess the units.
    """

    source: str
    value: float
    delta: float
    status: str
    identifier: str | None = None
    error: str | None = None
    recorded_at: datetime | None = None


# ── Helpers ────────────────────────────────────────────────────────────


def _to_mapping_out(m: BIMapping) -> BIMappingOut:
    return BIMappingOut(
        id=m.id,
        metric_id=m.metric_id,
        source=m.source,
        identifier=m.identifier,
        created_at=m.created_at,
    )


def _to_recon_out(row: Reconciliation) -> ReconciliationRowOut:
    return ReconciliationRowOut(
        source=row.source,
        value=float(row.value) if row.value is not None else 0.0,
        delta=float(row.delta) if row.delta is not None else 0.0,
        status=row.status,
        identifier=row.identifier,
        error=row.error,
        recorded_at=row.recorded_at,
    )


def _warehouse_row(metric: Metric, session: Session) -> ReconciliationRowOut:
    """Build the synthetic 'warehouse' row that always tops the panel.

    The warehouse is the source of truth we reconcile *against* — its delta
    is always 0 and its status is always pass. If the metric has no runs
    yet, value falls back to 0 so the UI never renders an empty panel.
    """
    latest_run: Run | None = (
        session.query(Run)
        .filter_by(metric_id=metric.id)
        .order_by(desc(Run.started_at))
        .first()
    )
    value = 0.0
    recorded_at: datetime | None = None
    if latest_run is not None and latest_run.value_sum is not None:
        value = float(latest_run.value_sum)
        recorded_at = latest_run.started_at
    return ReconciliationRowOut(
        source="warehouse",
        value=value,
        delta=0.0,
        status="pass",
        identifier=metric.primary_table,
        recorded_at=recorded_at,
    )


# ── Mappings CRUD ──────────────────────────────────────────────────────


@router.post(
    "/metrics/{metric_id}/bi-mappings",
    response_model=BIMappingOut,
    status_code=status.HTTP_201_CREATED,
)
def create_bi_mapping(
    metric_id: str,
    payload: BIMappingIn,
    org: Org = Depends(current_org),
    session: Session = Depends(db_session),
) -> BIMappingOut:
    """Attach a metric to its equivalent in a BI tool.

    Idempotent on ``(metric_id, source)`` — attempting to add a second
    mapping for the same source returns 409 instead of silently overwriting.
    If you need to change an identifier, DELETE the existing mapping first.
    """
    metric = _resolve_metric(session, org, metric_id)
    source = payload.source.lower().strip()
    if source not in SUPPORTED_SOURCES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"unknown source {payload.source!r} "
            f"(supported: {', '.join(SUPPORTED_SOURCES)})",
        )

    existing = (
        session.query(BIMapping)
        .filter_by(metric_id=metric.id, source=source)
        .one_or_none()
    )
    if existing is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"mapping for source {source!r} already exists (delete it first)",
        )

    mapping = BIMapping(
        metric_id=metric.id,
        source=source,
        identifier=payload.identifier,
    )
    session.add(mapping)
    session.flush()
    out = _to_mapping_out(mapping)
    session.commit()
    return out


@router.get(
    "/metrics/{metric_id}/bi-mappings",
    response_model=list[BIMappingOut],
)
def list_bi_mappings(
    metric_id: str,
    org: Org = Depends(current_org),
    session: Session = Depends(db_session),
) -> list[BIMappingOut]:
    metric = _resolve_metric(session, org, metric_id)
    mappings = (
        session.query(BIMapping)
        .filter_by(metric_id=metric.id)
        .order_by(BIMapping.source.asc())
        .all()
    )
    return [_to_mapping_out(m) for m in mappings]


@router.delete(
    "/metrics/{metric_id}/bi-mappings/{mapping_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_bi_mapping(
    metric_id: str,
    mapping_id: str,
    org: Org = Depends(current_org),
    session: Session = Depends(db_session),
) -> None:
    metric = _resolve_metric(session, org, metric_id)
    mapping = (
        session.query(BIMapping)
        .filter_by(id=mapping_id, metric_id=metric.id)
        .one_or_none()
    )
    if mapping is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "mapping not found")
    session.delete(mapping)
    session.commit()


# ── Reconciliation ─────────────────────────────────────────────────────


@router.get(
    "/metrics/{metric_id}/reconciliation",
    response_model=list[ReconciliationRowOut],
)
def get_reconciliation(
    metric_id: str,
    org: Org = Depends(current_org),
    session: Session = Depends(db_session),
) -> list[ReconciliationRowOut]:
    """Return latest reconciliation state for a metric.

    Always includes a synthetic ``"warehouse"`` row at the top, built from
    the metric's latest run. Per-source rows come from the most recent
    :class:`Reconciliation` for each ``source`` on that metric. The response
    is intentionally never empty — even a metric with no runs and no
    mappings gets a single warehouse row with ``value=0``.
    """
    metric = _resolve_metric(session, org, metric_id)
    rows: list[ReconciliationRowOut] = [_warehouse_row(metric, session)]

    # One row per source = latest Reconciliation by recorded_at. SQLite
    # doesn't support DISTINCT ON, so we pull everything and dedupe in Python.
    # The table is keyed on (metric_id, recorded_at DESC) so this stays cheap
    # even with months of history — in practice there's < 10 rows per metric
    # per day.
    all_rows: list[Reconciliation] = (
        session.query(Reconciliation)
        .filter_by(metric_id=metric.id)
        .order_by(desc(Reconciliation.recorded_at), desc(Reconciliation.id))
        .all()
    )
    seen: set[str] = set()
    for row in all_rows:
        if row.source in seen:
            continue
        seen.add(row.source)
        rows.append(_to_recon_out(row))
    return rows


@router.post(
    "/metrics/{metric_id}/reconcile",
    response_model=list[ReconciliationRowOut],
    status_code=status.HTTP_200_OK,
)
def trigger_reconciliation(
    metric_id: str,
    org: Org = Depends(current_org),
    session: Session = Depends(db_session),
) -> list[ReconciliationRowOut]:
    """Fetch every BI-tool value for this metric and persist a new row per source.

    Returns the freshly-written rows (not including the warehouse synthetic).
    Callers hitting this on a schedule get idempotent behaviour: the rows
    pile up in ``reconciliations``, but ``GET /reconciliation`` only ever
    surfaces the newest per source.
    """
    metric = _resolve_metric(session, org, metric_id)
    created = run_reconciliation(session, metric.id)
    session.commit()
    return [_to_recon_out(r) for r in created]
