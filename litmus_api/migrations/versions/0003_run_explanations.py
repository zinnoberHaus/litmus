"""run_explanations — AI-generated hypothesis for failed/errored runs

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-18

One explanation per run (UNIQUE on ``run_id``). Only written when a run's
``status`` is ``failed`` or ``error`` and the operator explicitly POSTs to
``/api/v1/runs/{id}/explain``. Re-triggering with ``?regenerate=true`` upserts
the existing row.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "run_explanations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("hypothesis", sa.Text(), nullable=False),
        sa.Column("suggested_action", sa.Text(), nullable=False),
        sa.Column("model_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", name="uq_run_explanations_run_id"),
    )


def downgrade() -> None:
    op.drop_table("run_explanations")
