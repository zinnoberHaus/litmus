"""bi_mappings + reconciliations — BI tool mappings and cross-source checks

Revision ID: 0005
Revises: 0004
Create Date: 2026-04-18

Adds the scaffold for the BI reconciliation story: every metric can be linked
to its equivalent in Looker / Tableau (``bi_mappings``), and every
reconciliation attempt writes a row into ``reconciliations`` with the
BI-tool value, its delta vs. the warehouse run, and a bucketed status.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "bi_mappings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("metric_id", sa.String(length=36), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("identifier", sa.String(length=500), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["metric_id"], ["metrics.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "metric_id", "source", name="uq_bi_mappings_metric_source"
        ),
    )
    with op.batch_alter_table("bi_mappings", schema=None) as batch_op:
        batch_op.create_index(
            "ix_bi_mappings_metric", ["metric_id"], unique=False
        )

    op.create_table(
        "reconciliations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("metric_id", sa.String(length=36), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("identifier", sa.String(length=500), nullable=False),
        sa.Column("value", sa.Numeric(), nullable=True),
        sa.Column("delta", sa.Numeric(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("recorded_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["metric_id"], ["metrics.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("reconciliations", schema=None) as batch_op:
        batch_op.create_index(
            "ix_reconciliations_metric_time",
            ["metric_id", "recorded_at"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("reconciliations", schema=None) as batch_op:
        batch_op.drop_index("ix_reconciliations_metric_time")
    op.drop_table("reconciliations")

    with op.batch_alter_table("bi_mappings", schema=None) as batch_op:
        batch_op.drop_index("ix_bi_mappings_metric")
    op.drop_table("bi_mappings")
