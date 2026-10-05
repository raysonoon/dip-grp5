"""add vendor contact and location metadata

Revision ID: 3c0cb84a736b
Revises: 19ead6639001
Create Date: 2026-10-03 14:18:15.301007

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "3c0cb84a736b"
down_revision: Union[str, Sequence[str], None] = "19ead6639001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add vendor contact and location metadata."""

    op.add_column(
        "vendors",
        sa.Column(
            "website_url",
            sa.Text(),
            nullable=True,
        ),
    )

    op.add_column(
        "vendors",
        sa.Column(
            "phone_number",
            sa.String(length=50),
            nullable=True,
        ),
    )

    op.add_column(
        "vendors",
        sa.Column(
            "address",
            sa.Text(),
            nullable=True,
        ),
    )


def downgrade() -> None:
    """Remove vendor contact and location metadata."""

    op.drop_column("vendors", "address")
    op.drop_column("vendors", "phone_number")
    op.drop_column("vendors", "website_url")