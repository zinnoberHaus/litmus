"""Reconciliation job: compare warehouse value to every BI-tool equivalent.

The caller is responsible for committing the session — we only ``flush``.

A reconciliation run for a metric does the following, per ``BIMapping``:

1. Instantiate the connector via :func:`litmus_api.bi.get_connector`.
2. Call ``fetch_metric_value(identifier)``.
3. Compute ``delta = (bi_value - warehouse_value) / warehouse_value``
   (0 if warehouse_value is 0/None — we can't divide by zero and a warehouse
   with no runs yet is a legitimate first-time state).
4. Bucket ``|delta|`` into pass/warn/fail using ``_DELTA_PASS`` / ``_DELTA_WARN``.
5. Write one ``Reconciliation`` row.

If the connector raises, we still write a row — ``status="fail"``, ``value``
and ``delta`` are null, the exception message goes into the ``error`` column.
That way the UI can render "Looker: errored with <reason>" next to a healthy
Tableau row rather than silently dropping the failing source.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import desc
from sqlalchemy.orm import Session

from litmus_api.bi import get_connector
from litmus_api.models import BIMapping, Reconciliation, Run

# Pass if the BI value is within 2% of the warehouse value. Warn up to 10%;
# anything larger is a hard fail. Thresholds live here rather than on the
# model so they stay easy to tune — nothing in the schema needs to change
# when we learn that 2% is too strict in practice.
_DELTA_PASS = Decimal("0.02")
_DELTA_WARN = Decimal("0.10")


def _bucket(delta: Decimal) -> str:
    abs_delta = abs(delta)
    if abs_delta < _DELTA_PASS:
        return "pass"
    if abs_delta < _DELTA_WARN:
        return "warn"
    return "fail"


def _latest_warehouse_value(session: Session, metric_id: str) -> Decimal | None:
    """Pull the most recent run's ``value_sum`` for a metric, or ``None``."""
    run: Run | None = (
        session.query(Run)
        .filter_by(metric_id=metric_id)
        .order_by(desc(Run.started_at))
        .first()
    )
    if run is None or run.value_sum is None:
        return None
    # Numeric columns round-trip as Decimal on SQLAlchemy 2.x; be explicit.
    return Decimal(str(run.value_sum))


def run_reconciliation(session: Session, metric_id: str) -> list[Reconciliation]:
    """Run reconciliation for every BI mapping on ``metric_id``.

    Returns the newly-inserted :class:`Reconciliation` rows in the same order
    as the underlying mappings. Empty list if the metric has no mappings.
    """
    mappings: list[BIMapping] = (
        session.query(BIMapping).filter_by(metric_id=metric_id).all()
    )
    if not mappings:
        return []

    warehouse_value = _latest_warehouse_value(session, metric_id)

    inserted: list[Reconciliation] = []
    for mapping in mappings:
        row = _reconcile_one(session, mapping, warehouse_value)
        inserted.append(row)

    session.flush()
    return inserted


def _reconcile_one(
    session: Session,
    mapping: BIMapping,
    warehouse_value: Decimal | None,
) -> Reconciliation:
    """Fetch one BI value, compute the delta, and persist a Reconciliation row.

    Any exception (bad connector config, network failure, parse error, …)
    becomes a ``status="fail"`` row with the message in ``error``. The
    whole-job loop in :func:`run_reconciliation` must keep running past
    per-mapping failures, so all handling lives here.
    """
    try:
        connector = get_connector(mapping.source)
        result = connector.fetch_metric_value(mapping.identifier)
    except Exception as exc:  # noqa: BLE001 — intentional catch-all
        row = Reconciliation(
            metric_id=mapping.metric_id,
            source=mapping.source,
            identifier=mapping.identifier,
            value=None,
            delta=None,
            status="fail",
            error=f"{type(exc).__name__}: {exc}",
        )
        session.add(row)
        session.flush()
        return row

    bi_value = Decimal(str(result.value))
    if warehouse_value is None or warehouse_value == 0:
        delta = Decimal("0")
    else:
        delta = (bi_value - warehouse_value) / warehouse_value
    status = _bucket(delta)

    row = Reconciliation(
        metric_id=mapping.metric_id,
        source=mapping.source,
        identifier=mapping.identifier,
        value=bi_value,
        delta=delta,
        status=status,
        error=None,
    )
    session.add(row)
    session.flush()
    return row
