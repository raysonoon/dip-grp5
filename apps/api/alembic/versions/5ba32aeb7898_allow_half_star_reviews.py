"""allow half-star reviews

Revision ID: 5ba32aeb7898
Revises: 6a5392a23743
Create Date: 2026-10-24 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '5ba32aeb7898'
down_revision: Union[str, Sequence[str], None] = '6a5392a23743'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


CONSTRAINT_NAME = "ck_reviews_rating_half_steps_range"


def upgrade() -> None:
    """Upgrade schema: allow 0.5 stars (rating_half_steps = 1)."""
    op.drop_constraint(CONSTRAINT_NAME, "reviews", type_="check")
    op.create_check_constraint(
        op.f(CONSTRAINT_NAME),
        "reviews",
        "rating_half_steps BETWEEN 1 AND 10",
    )


def downgrade() -> None:
    """Downgrade schema: restore the 1.0-star minimum.

    Existing 0.5-star reviews are raised to 1.0 star so the old constraint holds.
    """
    op.execute("UPDATE reviews SET rating_half_steps = 2 WHERE rating_half_steps = 1")
    op.drop_constraint(CONSTRAINT_NAME, "reviews", type_="check")
    op.create_check_constraint(
        op.f(CONSTRAINT_NAME),
        "reviews",
        "rating_half_steps BETWEEN 2 AND 10",
    )
