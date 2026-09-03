"""Add external web fallback evidence to knowledge gaps.

Revision ID: 8f6d4e2b1a90
Revises: f62ac804a921
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "8f6d4e2b1a90"
down_revision: Union[str, Sequence[str], None] = "f62ac804a921"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "knowledge_gaps",
        sa.Column(
            "external_sources",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "knowledge_gaps",
        sa.Column(
            "external_recovery",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "knowledge_gaps",
        sa.Column(
            "ingestion_status",
            sa.String(),
            server_default="pending_review",
            nullable=False,
        ),
    )
    op.create_index(
        op.f("ix_knowledge_gaps_ingestion_status"),
        "knowledge_gaps",
        ["ingestion_status"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_knowledge_gaps_ingestion_status"),
        table_name="knowledge_gaps",
    )
    op.drop_column("knowledge_gaps", "ingestion_status")
    op.drop_column("knowledge_gaps", "external_recovery")
    op.drop_column("knowledge_gaps", "external_sources")
