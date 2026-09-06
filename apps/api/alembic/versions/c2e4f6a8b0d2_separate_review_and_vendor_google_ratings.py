"""separate google review rating and vendor average rating

Revision ID: c2e4f6a8b0d2
Revises: b80ac6cf803c
Create Date: 2026-09-06 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c2e4f6a8b0d2'
down_revision: Union[str, Sequence[str], None] = 'b80ac6cf803c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Move the average Google rating to vendors and keep per-review ratings.

    ``google_reviews.rating`` stores each individual review's integer
    (1-5) rating, converted from the old quantized half-step value.
    ``vendors.average_google_rating`` stores the vendor-level raw decimal
    (0-5, nullable when unrated).
    """
    op.add_column(
        "google_reviews",
        sa.Column(
            "rating",
            sa.SmallInteger(),
            nullable=True,
        ),
    )
    op.execute(
        sa.text(
            """
            UPDATE google_reviews
            SET rating = rating_half_steps / 2
            """
        )
    )
    op.alter_column(
        "google_reviews",
        "rating",
        existing_type=sa.SmallInteger(),
        nullable=False,
    )
    op.drop_column("google_reviews", "rating_half_steps")
    op.create_check_constraint(
        op.f("ck_google_reviews_rating_range"),
        "google_reviews",
        "rating BETWEEN 1 AND 5",
    )

    op.add_column(
        "vendors",
        sa.Column(
            "average_google_rating",
            sa.Numeric(2, 1),
            nullable=True,
        ),
    )
    op.create_check_constraint(
        op.f("ck_vendors_average_google_rating_range"),
        "vendors",
        "average_google_rating IS NULL "
        "OR average_google_rating BETWEEN 0 AND 5",
    )


def downgrade() -> None:
    """Restore the quantized half-step rating on google_reviews."""
    op.drop_constraint(
        op.f("ck_vendors_average_google_rating_range"),
        "vendors",
        type_="check",
    )
    op.drop_column("vendors", "average_google_rating")

    op.drop_constraint(
        op.f("ck_google_reviews_rating_range"),
        "google_reviews",
        type_="check",
    )
    op.add_column(
        "google_reviews",
        sa.Column(
            "rating_half_steps",
            sa.SmallInteger(),
            nullable=True,
        ),
    )
    op.execute(
        sa.text(
            """
            UPDATE google_reviews
            SET rating_half_steps = rating * 2
            """
        )
    )
    op.alter_column(
        "google_reviews",
        "rating_half_steps",
        existing_type=sa.SmallInteger(),
        nullable=False,
    )
    op.drop_column("google_reviews", "rating")