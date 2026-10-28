"""merge vendor favourites and half-star reviews

Revision ID: 5c49b77c3a16
Revises: 5ba32aeb7898, d103f25a0001
Create Date: 2026-10-27 15:25:51.091192

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5c49b77c3a16'
down_revision: Union[str, Sequence[str], None] = ('5ba32aeb7898', 'd103f25a0001')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
