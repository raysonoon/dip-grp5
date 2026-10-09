"""merge Supabase identity and review vote migration heads

Revision ID: f1a2b3c4d5e6
Revises: d7a3c2e1f4b5, efceea3e9e44
Create Date: 2026-10-08 13:20:00.000000
"""

from typing import Sequence, Union


revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, Sequence[str], None] = (
    "d7a3c2e1f4b5",
    "efceea3e9e44",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass