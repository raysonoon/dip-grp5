"""add vendor image mime type and file size

Revision ID: 9f2e4c6a8b0d
Revises: h8b0d2f4a6c7
Create Date: 2026-09-08 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9f2e4c6a8b0d"
down_revision: Union[str, Sequence[str], None] = "h8b0d2f4a6c7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add MIME type and byte size to vendor images (table is empty)."""
    op.add_column(
        "vendor_images",
        sa.Column("mime_type", sa.String(length=20), nullable=False),
    )
    op.add_column(
        "vendor_images",
        sa.Column("file_size_bytes", sa.Integer(), nullable=False),
    )


def downgrade() -> None:
    """Remove vendor image MIME type and byte size."""
    op.drop_column("vendor_images", "file_size_bytes")
    op.drop_column("vendor_images", "mime_type")