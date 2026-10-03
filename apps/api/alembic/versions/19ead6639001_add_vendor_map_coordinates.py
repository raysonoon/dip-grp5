"""add vendor map coordinates

Revision ID: 19ead6639001
Revises: b1c3d5e7f9a2
Create Date: 2026-09-26

"""
from typing import Sequence, Union

import geoalchemy2
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "19ead6639001"
down_revision: Union[str, None] = "b1c3d5e7f9a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "vendors",
        sa.Column(
            "map_coordinates",
            geoalchemy2.Geography(
                geometry_type="POINT",
                srid=4326,
                from_text="ST_GeogFromText",
                name="geography",
            ),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("vendors", "map_coordinates")