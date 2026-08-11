"""add structured conversation state

Revision ID: b728f46a901d
Revises: a31f1c52d870
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "b728f46a901d"
down_revision: Union[str, Sequence[str], None] = "a31f1c52d870"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column("conversation_state", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("conversations", "conversation_state")
