"""rename allergies to dietary restrictions

Revision ID: 92807e168297
Revises: 480813a861d3
Create Date: 2026-10-19 10:54:48.471305

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '92807e168297'
down_revision: Union[str, Sequence[str], None] = '480813a861d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column(
        "user_food_preferences",
        "allergies",
        new_column_name="dietary_restrictions",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column(
        "user_food_preferences",
        "dietary_restrictions",
        new_column_name="allergies",
    )