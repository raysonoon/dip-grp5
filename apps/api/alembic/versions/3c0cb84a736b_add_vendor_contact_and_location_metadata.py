"""add vendor contact and location metadata

Revision ID: 3c0cb84a736b
Revises: b1c3d5e7f9a2
Create Date: 2026-10-03 14:18:15.301007

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geometry


# revision identifiers, used by Alembic.
revision: str = "3c0cb84a736b"
down_revision: Union[str, Sequence[str], None] = "b1c3d5e7f9a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add vendor contact and location metadata."""

    bind = op.get_bind()

    if bind.dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

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
                "map_coordinates",
                Geometry(
                    geometry_type="POINT",
                    srid=4326,
                ),
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

    else:
        # SQLite test fallback
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
                "map_coordinates",
                sa.Text(),
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
    op.drop_column("vendors", "map_coordinates")
    op.drop_column("vendors", "phone_number")
    op.drop_column("vendors", "website_url")