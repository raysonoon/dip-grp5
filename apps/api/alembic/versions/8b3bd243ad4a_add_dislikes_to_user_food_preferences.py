"""add dislikes to user food preferences

Revision ID: 8b3bd243ad4a
Revises: 001289c166b6
Create Date: 2026-10-12 15:43:52.998523

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '8b3bd243ad4a'
down_revision: Union[str, Sequence[str], None] = '001289c166b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "user_food_preferences",
        sa.Column(
            "dislikes",
            sa.JSON().with_variant(
                postgresql.ARRAY(sa.String()),
                "postgresql",
            ),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )
    op.alter_column(
        "user_food_preferences",
        "dislikes",
        server_default=None,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("user_food_preferences", "dislikes")

