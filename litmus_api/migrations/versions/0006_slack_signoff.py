"""slack sign-off columns on metric_revisions

Revision ID: 0006
Revises: 0005
Create Date: 2026-04-18

Adds the Slack sign-off workflow columns to ``metric_revisions``. All new
columns are nullable (or default False) so existing revisions are unaffected
— legacy rows carry ``signoff_required=False`` + ``signoff_status=NULL``
which the UI reads as "not part of the workflow" and renders nothing.

The ``signoff_status`` value space is documented at the model layer:
``pending | approved | rejected | auto_approved`` (plus NULL).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | Sequence[str] | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ``batch_alter_table`` is the SQLite-friendly ``ALTER TABLE`` — the same
    # pattern we use elsewhere so the OSS sqlite default and the Postgres
    # prod deploy both round-trip cleanly.
    with op.batch_alter_table("metric_revisions", schema=None) as batch_op:
        # ``server_default`` is required so the NOT NULL constraint succeeds
        # on existing rows; we keep the Python-side default in the model too
        # so new inserts that don't pass the value explicitly still work.
        batch_op.add_column(
            sa.Column(
                "signoff_required",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )
        batch_op.add_column(
            sa.Column("signoff_status", sa.String(length=16), nullable=True)
        )
        batch_op.add_column(
            sa.Column("signoff_by", sa.String(length=320), nullable=True)
        )
        batch_op.add_column(
            sa.Column("signoff_at", sa.DateTime(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("signoff_reason", sa.Text(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("slack_message_ts", sa.String(length=32), nullable=True)
        )
        batch_op.add_column(
            sa.Column("slack_channel_id", sa.String(length=32), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("metric_revisions", schema=None) as batch_op:
        batch_op.drop_column("slack_channel_id")
        batch_op.drop_column("slack_message_ts")
        batch_op.drop_column("signoff_reason")
        batch_op.drop_column("signoff_at")
        batch_op.drop_column("signoff_by")
        batch_op.drop_column("signoff_status")
        batch_op.drop_column("signoff_required")
