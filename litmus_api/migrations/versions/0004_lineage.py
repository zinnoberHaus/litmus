"""lineage_nodes + lineage_edges — metric lineage graph

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-18

Lineage is intra-metric: each metric owns its own subgraph of nodes + edges
seeded from the dbt manifest's ``parent_map`` (up to 3 hops upstream). The
``POST /metrics/{id}/lineage`` route replaces the subgraph atomically on
every import so re-running ``litmus import-dbt --push`` stays idempotent.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "lineage_nodes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("metric_id", sa.String(length=36), nullable=True),
        sa.Column("label", sa.String(length=500), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["metric_id"], ["metrics.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("lineage_nodes", schema=None) as batch_op:
        batch_op.create_index(
            "ix_lineage_nodes_metric", ["metric_id"], unique=False
        )

    op.create_table(
        "lineage_edges",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("metric_id", sa.String(length=36), nullable=False),
        sa.Column("from_node_id", sa.String(length=36), nullable=False),
        sa.Column("to_node_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["metric_id"], ["metrics.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["from_node_id"], ["lineage_nodes.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["to_node_id"], ["lineage_nodes.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("lineage_edges", schema=None) as batch_op:
        batch_op.create_index(
            "ix_lineage_edges_metric", ["metric_id"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("lineage_edges", schema=None) as batch_op:
        batch_op.drop_index("ix_lineage_edges_metric")
    op.drop_table("lineage_edges")

    with op.batch_alter_table("lineage_nodes", schema=None) as batch_op:
        batch_op.drop_index("ix_lineage_nodes_metric")
    op.drop_table("lineage_nodes")
