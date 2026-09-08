"""add vendor unit code

Revision ID: h8b0d2f4a6c7
Revises: f7a9c1e3b5d6
Create Date: 2026-09-06 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "h8b0d2f4a6c7"
down_revision: Union[str, Sequence[str], None] = "f7a9c1e3b5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add the canonical vendor unit code."""
    op.add_column(
        "vendors",
        sa.Column("unit_code", sa.String(length=50), nullable=True),
    )


def downgrade() -> None:
    """Remove the canonical vendor unit code."""
    op.drop_column("vendors", "unit_code")
