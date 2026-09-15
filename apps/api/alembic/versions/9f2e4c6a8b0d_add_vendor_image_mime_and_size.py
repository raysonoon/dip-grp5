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
    """Add MIME type and byte size, including metadata for legacy rows."""
    op.add_column(
        "vendor_images",
        sa.Column("mime_type", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "vendor_images",
        sa.Column("file_size_bytes", sa.Integer(), nullable=True),
    )
    op.execute(
        """
        UPDATE vendor_images
        SET
            mime_type = CASE
                WHEN lower(split_part(image_url, '?', 1)) LIKE '%.png'
                    THEN 'image/png'
                ELSE 'image/jpeg'
            END,
            file_size_bytes = 0
        """
    )
    op.alter_column("vendor_images", "mime_type", nullable=False)
    op.alter_column("vendor_images", "file_size_bytes", nullable=False)


def downgrade() -> None:
    """Remove vendor image MIME type and byte size."""
    op.drop_column("vendor_images", "file_size_bytes")
    op.drop_column("vendor_images", "mime_type")
