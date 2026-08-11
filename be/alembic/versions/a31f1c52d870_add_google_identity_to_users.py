"""add Google identity to users

Revision ID: a31f1c52d870
Revises: 012cfc09516f
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a31f1c52d870"
down_revision: Union[str, Sequence[str], None] = "012cfc09516f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("google_subject", sa.String(), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("profile_picture_url", sa.Text(), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("last_login_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        op.f("ix_users_google_subject"),
        "users",
        ["google_subject"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_users_google_subject"),
        table_name="users",
    )
    op.drop_column("users", "last_login_at")
    op.drop_column("users", "profile_picture_url")
    op.drop_column("users", "google_subject")
