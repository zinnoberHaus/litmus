"""metric_revisions — append-only log of metric spec changes

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-18

One row per distinct ``spec_text`` observed for a metric. Identical re-upserts
are deduped at the route layer so the log stays meaningful. Indexed on
``(metric_id, created_at)`` so the common "last 30 revisions" query is cheap.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "metric_revisions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("metric_id", sa.String(length=36), nullable=False),
        sa.Column("spec_text", sa.Text(), nullable=False),
        sa.Column("spec_json", sa.JSON(), nullable=False),
        sa.Column("source_sha", sa.String(length=64), nullable=True),
        sa.Column("author", sa.String(length=320), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["metric_id"], ["metrics.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("metric_revisions", schema=None) as batch_op:
        batch_op.create_index(
            "ix_metric_revisions_metric_time",
            ["metric_id", "created_at"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("metric_revisions", schema=None) as batch_op:
        batch_op.drop_index("ix_metric_revisions_metric_time")
    op.drop_table("metric_revisions")
