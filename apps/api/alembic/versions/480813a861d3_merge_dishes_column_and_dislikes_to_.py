"""merge dishes column and dislikes to user preferences

Revision ID: 480813a861d3
Revises: 84cdc517bdbd, 8b3bd243ad4a
Create Date: 2026-10-15 22:48:09.734696

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '480813a861d3'
down_revision: Union[str, Sequence[str], None] = ('84cdc517bdbd', '8b3bd243ad4a')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
