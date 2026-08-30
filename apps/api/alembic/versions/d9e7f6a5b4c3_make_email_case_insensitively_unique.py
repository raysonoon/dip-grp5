"""make email addresses case-insensitively unique

Revision ID: d9e7f6a5b4c3
Revises: a8f1c2d3e4b5
Create Date: 2026-08-27

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "d9e7f6a5b4c3"
down_revision: Union[str, Sequence[str], None] = "a8f1c2d3e4b5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(
        op.f("uq_users_email_address"),
        "users",
        type_="unique",
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM users
                GROUP BY lower(btrim(email_address))
                HAVING count(*) > 1
            ) THEN
                RAISE EXCEPTION
                    'Cannot normalize email addresses: case-insensitive duplicates exist';
            END IF;
        END
        $$
        """
    )
    op.execute(
        """
        UPDATE users
        SET email_address = lower(btrim(email_address))
        """
    )
    op.create_index(
        "uq_users_email_address_lower",
        "users",
        [sa.text("lower(email_address)")],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_users_email_address_lower", table_name="users")
    op.create_unique_constraint(
        op.f("uq_users_email_address"),
        "users",
        ["email_address"],
    )
