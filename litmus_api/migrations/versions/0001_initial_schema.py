"""initial schema — orgs, api_keys, metrics, runs, check_results, embed_keys

Revision ID: 0001
Revises:
Create Date: 2026-04-18

Captures the 0.2 catalog schema as it stood immediately before migrations
landed. Equivalent to ``Base.metadata.create_all(engine)`` against an empty
DB — on a fresh SQLite file both paths produce the same schema.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "orgs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("plan", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_table(
        "api_keys",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("prefix", sa.String(length=32), nullable=False),
        sa.Column("hash", sa.String(length=128), nullable=False),
        sa.Column("scopes", sa.JSON(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["orgs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("hash"),
    )
    op.create_table(
        "metrics",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("slug", sa.String(length=200), nullable=False),
        sa.Column("name", sa.String(length=500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("owner_email", sa.String(length=320), nullable=True),
        sa.Column("source_repo", sa.String(length=500), nullable=True),
        sa.Column("source_path", sa.String(length=500), nullable=True),
        sa.Column("source_sha", sa.String(length=64), nullable=True),
        sa.Column("spec_json", sa.JSON(), nullable=False),
        sa.Column("spec_text", sa.Text(), nullable=False),
        sa.Column("primary_table", sa.String(length=300), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["org_id"], ["orgs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("org_id", "slug", name="uq_metrics_org_slug"),
    )
    op.create_table(
        "embed_keys",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("metric_id", sa.String(length=36), nullable=False),
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["metric_id"], ["metrics.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["org_id"], ["orgs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token"),
    )
    op.create_table(
        "runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("metric_id", sa.String(length=36), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("trust_score", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("commit_sha", sa.String(length=64), nullable=True),
        sa.Column("ci_run_id", sa.String(length=64), nullable=True),
        sa.Column("triggered_by", sa.String(length=32), nullable=False),
        sa.Column("value_sum", sa.Numeric(), nullable=True),
        sa.Column("row_count", sa.Integer(), nullable=True),
        sa.Column("schema_fingerprint", sa.String(length=128), nullable=True),
        sa.Column("column_means_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["metric_id"], ["metrics.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["org_id"], ["orgs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("runs", schema=None) as batch_op:
        batch_op.create_index(
            "ix_runs_metric_time", ["metric_id", "started_at"], unique=False
        )

    op.create_table(
        "check_results",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("rule_type", sa.String(length=32), nullable=False),
        sa.Column("rule_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("actual_value", sa.Numeric(), nullable=True),
        sa.Column("threshold_value", sa.Numeric(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("check_results", schema=None) as batch_op:
        batch_op.create_index("ix_check_results_run", ["run_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("check_results", schema=None) as batch_op:
        batch_op.drop_index("ix_check_results_run")
    op.drop_table("check_results")

    with op.batch_alter_table("runs", schema=None) as batch_op:
        batch_op.drop_index("ix_runs_metric_time")
    op.drop_table("runs")

    op.drop_table("embed_keys")
    op.drop_table("metrics")
    op.drop_table("api_keys")
    op.drop_table("orgs")
