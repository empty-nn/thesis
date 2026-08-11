"""Add knowledge gaps for unresolved travel requests.

Revision ID: d34a9c71e821
Revises: b728f46a901d
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "d34a9c71e821"
down_revision: Union[str, Sequence[str], None] = "b728f46a901d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "knowledge_gaps",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(), nullable=True),
        sa.Column("conversation_id", sa.String(), nullable=True),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("rewritten_query", sa.Text(), nullable=True),
        sa.Column(
            "missing_requirements",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "recovery_queries",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "top_evidence",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["conversations.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_knowledge_gaps_conversation_id"),
        "knowledge_gaps",
        ["conversation_id"],
    )
    op.create_index(
        op.f("ix_knowledge_gaps_status"),
        "knowledge_gaps",
        ["status"],
    )
    op.create_index(
        op.f("ix_knowledge_gaps_user_id"),
        "knowledge_gaps",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_knowledge_gaps_user_id"), table_name="knowledge_gaps")
    op.drop_index(op.f("ix_knowledge_gaps_status"), table_name="knowledge_gaps")
    op.drop_index(
        op.f("ix_knowledge_gaps_conversation_id"),
        table_name="knowledge_gaps",
    )
    op.drop_table("knowledge_gaps")
