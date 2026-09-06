"""add vendor price and dietary metadata

Revision ID: f7a9c1e3b5d6
Revises: c2e4f6a8b0d2
Create Date: 2026-09-06 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f7a9c1e3b5d6"
down_revision: Union[str, Sequence[str], None] = "c2e4f6a8b0d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add optional price range and dietary metadata to vendors."""
    op.add_column(
        "vendors",
        sa.Column("price_range", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "vendors",
        sa.Column("halal", sa.Boolean(), nullable=True),
    )
    op.add_column(
        "vendors",
        sa.Column("vegetarian", sa.Boolean(), nullable=True),
    )


def downgrade() -> None:
    """Remove vendor price range and dietary metadata."""
    op.drop_column("vendors", "vegetarian")
    op.drop_column("vendors", "halal")
    op.drop_column("vendors", "price_range")
