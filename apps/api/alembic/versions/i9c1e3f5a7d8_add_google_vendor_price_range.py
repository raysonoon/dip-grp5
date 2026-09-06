"""add Google vendor price range

Revision ID: i9c1e3f5a7d8
Revises: h8b0d2f4a6c7
Create Date: 2026-09-06 19:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "i9c1e3f5a7d8"
down_revision: Union[str, Sequence[str], None] = "h8b0d2f4a6c7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Keep Google pricing separate from the F&B directory price range."""
    op.add_column(
        "vendors",
        sa.Column("google_price_range", sa.String(length=20), nullable=True),
    )


def downgrade() -> None:
    """Remove the Google-specific price range."""
    op.drop_column("vendors", "google_price_range")
