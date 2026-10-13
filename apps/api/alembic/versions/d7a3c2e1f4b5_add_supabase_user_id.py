"""add Supabase identity link

Revision ID: d7a3c2e1f4b5
Revises: 9f2e4c6a8b0d
Create Date: 2026-10-08 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d7a3c2e1f4b5"
down_revision: Union[str, Sequence[str], None] = "3c0cb84a736b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("supabase_user_id", sa.String(length=36), nullable=True))
    op.create_unique_constraint("uq_users_supabase_user_id", "users", ["supabase_user_id"])


def downgrade() -> None:
    op.drop_constraint("uq_users_supabase_user_id", "users", type_="unique")
    op.drop_column("users", "supabase_user_id")