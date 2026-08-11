"""Add internal pipeline LLM telemetry.

Revision ID: f62ac804a921
Revises: d34a9c71e821
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "f62ac804a921"
down_revision: Union[str, Sequence[str], None] = "d34a9c71e821"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "pipeline_telemetry",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("request_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=True),
        sa.Column("conversation_id", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("error_type", sa.String(), nullable=True),
        sa.Column("total_latency_ms", sa.Float(), nullable=False),
        sa.Column("total_tokens", sa.Integer(), nullable=False),
        sa.Column("estimated_cost_usd", sa.Float(), nullable=True),
        sa.Column("stage_records", postgresql.JSONB(), nullable=False),
        sa.Column("token_totals", postgresql.JSONB(), nullable=False),
        sa.Column("pricing_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("request_id"),
    )
    op.create_index(op.f("ix_pipeline_telemetry_conversation_id"), "pipeline_telemetry", ["conversation_id"])
    op.create_index(op.f("ix_pipeline_telemetry_request_id"), "pipeline_telemetry", ["request_id"], unique=True)
    op.create_index(op.f("ix_pipeline_telemetry_status"), "pipeline_telemetry", ["status"])
    op.create_index(op.f("ix_pipeline_telemetry_user_id"), "pipeline_telemetry", ["user_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_pipeline_telemetry_user_id"), table_name="pipeline_telemetry")
    op.drop_index(op.f("ix_pipeline_telemetry_status"), table_name="pipeline_telemetry")
    op.drop_index(op.f("ix_pipeline_telemetry_request_id"), table_name="pipeline_telemetry")
    op.drop_index(op.f("ix_pipeline_telemetry_conversation_id"), table_name="pipeline_telemetry")
    op.drop_table("pipeline_telemetry")
