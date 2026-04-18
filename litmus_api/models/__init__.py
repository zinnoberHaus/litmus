from __future__ import annotations

import secrets
import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Session, relationship


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.utcnow()


class Base(DeclarativeBase):
    pass


class Org(Base):
    __tablename__ = "orgs"

    id = Column(String(36), primary_key=True, default=_uuid)
    slug = Column(String(100), nullable=False, unique=True)
    name = Column(String(200), nullable=False)
    plan = Column(String(20), nullable=False, default="oss")
    created_at = Column(DateTime, nullable=False, default=_now)
    deleted_at = Column(DateTime)


class ApiKey(Base):
    __tablename__ = "api_keys"

    id = Column(String(36), primary_key=True, default=_uuid)
    org_id = Column(String(36), ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False)
    prefix = Column(String(32), nullable=False)
    hash = Column(String(128), nullable=False, unique=True)
    scopes = Column(JSON, nullable=False, default=list)
    last_used_at = Column(DateTime)
    revoked_at = Column(DateTime)
    created_at = Column(DateTime, nullable=False, default=_now)


class Metric(Base):
    __tablename__ = "metrics"
    __table_args__ = (UniqueConstraint("org_id", "slug", name="uq_metrics_org_slug"),)

    id = Column(String(36), primary_key=True, default=_uuid)
    org_id = Column(String(36), ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False)
    slug = Column(String(200), nullable=False)
    name = Column(String(500), nullable=False)
    description = Column(Text)
    owner_email = Column(String(320))
    source_repo = Column(String(500))
    source_path = Column(String(500))
    source_sha = Column(String(64))
    spec_json = Column(JSON, nullable=False)
    spec_text = Column(Text, nullable=False)
    primary_table = Column(String(300))
    created_at = Column(DateTime, nullable=False, default=_now)
    updated_at = Column(DateTime, nullable=False, default=_now, onupdate=_now)
    deleted_at = Column(DateTime)

    runs = relationship("Run", back_populates="metric", cascade="all, delete-orphan")
    embed_keys = relationship("EmbedKey", back_populates="metric", cascade="all, delete-orphan")
    revisions = relationship(
        "MetricRevision", back_populates="metric", cascade="all, delete-orphan"
    )


class MetricRevision(Base):
    """Append-only log of metric spec changes.

    One row is written every time a metric's ``spec_text`` actually changes
    on upsert — identical re-upserts are deduped. This is what powers the
    ``GET /api/v1/metrics/{id}/revisions`` endpoint so owners can see how a
    definition evolved (and correlate a trust regression to a spec edit).
    """

    __tablename__ = "metric_revisions"
    __table_args__ = (
        Index("ix_metric_revisions_metric_time", "metric_id", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    metric_id = Column(
        String(36), ForeignKey("metrics.id", ondelete="CASCADE"), nullable=False
    )
    spec_text = Column(Text, nullable=False)
    spec_json = Column(JSON, nullable=False)
    source_sha = Column(String(64))
    author = Column(String(320))
    created_at = Column(DateTime, nullable=False, default=_now)

    metric = relationship("Metric", back_populates="revisions")


class Run(Base):
    __tablename__ = "runs"
    __table_args__ = (Index("ix_runs_metric_time", "metric_id", "started_at"),)

    id = Column(String(36), primary_key=True, default=_uuid)
    org_id = Column(String(36), ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False)
    metric_id = Column(
        String(36), ForeignKey("metrics.id", ondelete="CASCADE"), nullable=False
    )
    started_at = Column(DateTime, nullable=False)
    finished_at = Column(DateTime)
    status = Column(String(16), nullable=False)
    trust_score = Column(Numeric(5, 4))
    commit_sha = Column(String(64))
    ci_run_id = Column(String(64))
    triggered_by = Column(String(32), nullable=False, default="cli")
    value_sum = Column(Numeric)
    row_count = Column(Integer)
    schema_fingerprint = Column(String(128))
    column_means_json = Column(JSON)
    created_at = Column(DateTime, nullable=False, default=_now)

    metric = relationship("Metric", back_populates="runs")
    results = relationship(
        "CheckResult", back_populates="run", cascade="all, delete-orphan"
    )


class CheckResult(Base):
    __tablename__ = "check_results"
    __table_args__ = (Index("ix_check_results_run", "run_id"),)

    id = Column(String(36), primary_key=True, default=_uuid)
    run_id = Column(String(36), ForeignKey("runs.id", ondelete="CASCADE"), nullable=False)
    rule_type = Column(String(32), nullable=False)
    rule_json = Column(JSON, nullable=False)
    status = Column(String(16), nullable=False)
    message = Column(Text)
    actual_value = Column(Numeric)
    threshold_value = Column(Numeric)
    duration_ms = Column(Integer)

    run = relationship("Run", back_populates="results")


class RunExplanation(Base):
    """AI-generated explanation for a failed/errored run.

    One explanation per run (enforced by the UNIQUE constraint on ``run_id``).
    Re-triggering ``POST /api/v1/runs/{id}/explain?regenerate=true`` upserts
    the existing row so the UI always sees the latest hypothesis.

    TODO(architect): when alembic lands, add an explicit migration creating
    this table. Until then we rely on ``Base.metadata.create_all`` in
    ``main.create_app`` to create the table on first boot.
    """

    __tablename__ = "run_explanations"
    __table_args__ = (
        UniqueConstraint("run_id", name="uq_run_explanations_run_id"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    run_id = Column(
        String(36),
        ForeignKey("runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    hypothesis = Column(Text, nullable=False)
    suggested_action = Column(Text, nullable=False)
    model_id = Column(String(64), nullable=False)
    created_at = Column(DateTime, nullable=False, default=_now)

    run = relationship("Run")


class EmbedKey(Base):
    __tablename__ = "embed_keys"

    id = Column(String(36), primary_key=True, default=_uuid)
    org_id = Column(String(36), ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False)
    metric_id = Column(
        String(36), ForeignKey("metrics.id", ondelete="CASCADE"), nullable=False
    )
    token = Column(String(64), nullable=False, unique=True)
    created_at = Column(DateTime, nullable=False, default=_now)
    revoked_at = Column(DateTime)

    metric = relationship("Metric", back_populates="embed_keys")


class LineageNode(Base):
    """One node in a metric's lineage graph (a source table, an intermediate
    dbt model, or the metric itself).

    Edges are intra-metric only — we deliberately don't join lineage across
    metrics in the catalog. Each metric owns its own subgraph so deleting a
    metric deletes its lineage without ripple effects.
    """

    __tablename__ = "lineage_nodes"
    __table_args__ = (
        Index("ix_lineage_nodes_metric", "metric_id"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    metric_id = Column(
        String(36),
        ForeignKey("metrics.id", ondelete="CASCADE"),
        nullable=True,
    )
    label = Column(String(500), nullable=False)
    # kind ∈ {"source", "model", "metric"} — validated at the route layer
    # rather than with a CHECK constraint so the set stays easy to extend.
    kind = Column(String(32), nullable=False)
    created_at = Column(DateTime, nullable=False, default=_now)


class LineageEdge(Base):
    """A directed edge in a metric's lineage graph (from upstream to downstream)."""

    __tablename__ = "lineage_edges"
    __table_args__ = (
        Index("ix_lineage_edges_metric", "metric_id"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    metric_id = Column(
        String(36),
        ForeignKey("metrics.id", ondelete="CASCADE"),
        nullable=False,
    )
    from_node_id = Column(
        String(36),
        ForeignKey("lineage_nodes.id", ondelete="CASCADE"),
        nullable=False,
    )
    to_node_id = Column(
        String(36),
        ForeignKey("lineage_nodes.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at = Column(DateTime, nullable=False, default=_now)


class BIMapping(Base):
    """Links a catalog metric to its equivalent in a BI tool.

    One mapping per (metric, source) pair — enforced by a UNIQUE constraint so
    the reconciliation job doesn't have to disambiguate. The ``identifier``
    shape is per-connector (see ``litmus_api/bi/<source>.py`` docstrings); the
    catalog stores it as opaque text so adding a new BI tool doesn't require
    a schema change.
    """

    __tablename__ = "bi_mappings"
    __table_args__ = (
        UniqueConstraint("metric_id", "source", name="uq_bi_mappings_metric_source"),
        Index("ix_bi_mappings_metric", "metric_id"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    metric_id = Column(
        String(36),
        ForeignKey("metrics.id", ondelete="CASCADE"),
        nullable=False,
    )
    # source ∈ {"looker", "tableau"} — validated at the route layer rather than
    # with a CHECK constraint so the set stays easy to extend.
    source = Column(String(32), nullable=False)
    identifier = Column(String(500), nullable=False)
    created_at = Column(DateTime, nullable=False, default=_now)


class Reconciliation(Base):
    """One reconciliation result row: a BI-tool value compared to the latest warehouse run.

    ``delta`` is stored as a proportion (``0.023`` = 2.3% drift) so the UI can
    render it however it wants without re-multiplying by 100. ``status`` is
    bucketed from ``|delta|``:

    - ``|delta| < 0.02`` → ``pass``
    - ``|delta| < 0.10`` → ``warn``
    - otherwise         → ``fail``

    A connector error is also recorded here with ``status="fail"`` and the
    exception message in ``error`` — we keep one row per attempt so the UI
    can always show the most recent state of each source.
    """

    __tablename__ = "reconciliations"
    __table_args__ = (
        Index("ix_reconciliations_metric_time", "metric_id", "recorded_at"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    metric_id = Column(
        String(36),
        ForeignKey("metrics.id", ondelete="CASCADE"),
        nullable=False,
    )
    source = Column(String(32), nullable=False)
    identifier = Column(String(500), nullable=False)
    value = Column(Numeric, nullable=True)
    delta = Column(Numeric, nullable=True)
    # status ∈ {"pass", "warn", "fail"}.
    status = Column(String(16), nullable=False)
    error = Column(Text, nullable=True)
    recorded_at = Column(DateTime, nullable=False, default=_now)


def generate_embed_token() -> str:
    return "lme_" + secrets.token_urlsafe(32)


def generate_api_key_secret() -> tuple[str, str]:
    prefix = "lmk_live_" + secrets.token_hex(4)
    secret = prefix + "_" + secrets.token_urlsafe(32)
    return prefix, secret


def ensure_default_org(session: Session, slug: str = "default") -> Org:
    org = session.query(Org).filter_by(slug=slug).one_or_none()
    if org is None:
        org = Org(slug=slug, name=slug.capitalize())
        session.add(org)
        session.flush()
    return org
