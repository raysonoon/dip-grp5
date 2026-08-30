"""preserve email spelling and add canonical identity

Revision ID: e2c4b6a8d0f1
Revises: d9e7f6a5b4c3
Create Date: 2026-08-27

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "e2c4b6a8d0f1"
down_revision: Union[str, Sequence[str], None] = "d9e7f6a5b4c3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("email_canonical", sa.String(length=320), nullable=True),
    )
    op.execute(
        """
        UPDATE users
        SET email_canonical = lower(btrim(email_address))
        """
    )
    op.alter_column("users", "email_canonical", nullable=False)
    op.create_check_constraint(
        op.f("ck_users_email_canonical_matches_address"),
        "users",
        "email_canonical = lower(trim(email_address))",
    )
    op.create_index(
        "uq_users_email_canonical",
        "users",
        ["email_canonical"],
        unique=True,
    )
    op.drop_index("uq_users_email_address_lower", table_name="users")


def downgrade() -> None:
    op.create_index(
        "uq_users_email_address_lower",
        "users",
        [sa.text("lower(email_address)")],
        unique=True,
    )
    op.drop_index("uq_users_email_canonical", table_name="users")
    op.drop_constraint(
        op.f("ck_users_email_canonical_matches_address"),
        "users",
        type_="check",
    )
    op.drop_column("users", "email_canonical")
