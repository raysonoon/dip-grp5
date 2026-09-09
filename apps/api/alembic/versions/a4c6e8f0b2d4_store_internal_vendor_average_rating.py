"""store and synchronize internal vendor average rating

Revision ID: a4c6e8f0b2d4
Revises: 9f2e4c6a8b0d
Create Date: 2026-09-09 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a4c6e8f0b2d4"
down_revision: Union[str, Sequence[str], None] = "9f2e4c6a8b0d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Store internal-review averages and keep them synchronized."""
    op.add_column(
        "vendors",
        sa.Column("average_rating", sa.Numeric(2, 1), nullable=True),
    )
    op.create_check_constraint(
        op.f("ck_vendors_average_rating_range"),
        "vendors",
        "average_rating IS NULL OR average_rating BETWEEN 0 AND 5",
    )

    # Populate the stored value for vendors that already have internal reviews.
    op.execute(
        sa.text(
            """
            UPDATE vendors AS vendor
            SET average_rating = review_average.average_rating
            FROM (
                SELECT
                    vendor_id,
                    ROUND(AVG(rating_half_steps::numeric) / 2, 1)
                        AS average_rating
                FROM reviews
                GROUP BY vendor_id
            ) AS review_average
            WHERE vendor.id = review_average.vendor_id
            """
        )
    )

    # Lock affected vendor rows before aggregating. This serializes concurrent
    # review writes for the same vendor so the last trigger sees all committed
    # reviews and cannot overwrite the value with a stale concurrent average.
    op.execute(
        sa.text(
            """
            CREATE FUNCTION sync_vendor_average_rating()
            RETURNS TRIGGER
            LANGUAGE plpgsql
            AS $$
            DECLARE
                affected_vendor_ids integer[];
            BEGIN
                IF TG_OP = 'INSERT' THEN
                    affected_vendor_ids := ARRAY[NEW.vendor_id];
                ELSIF TG_OP = 'DELETE' THEN
                    affected_vendor_ids := ARRAY[OLD.vendor_id];
                ELSE
                    affected_vendor_ids := ARRAY[OLD.vendor_id, NEW.vendor_id];
                END IF;

                PERFORM id
                FROM vendors
                WHERE id = ANY(affected_vendor_ids)
                ORDER BY id
                FOR NO KEY UPDATE;

                UPDATE vendors AS vendor
                SET average_rating = (
                    SELECT ROUND(
                        AVG(review.rating_half_steps::numeric) / 2,
                        1
                    )
                    FROM reviews AS review
                    WHERE review.vendor_id = vendor.id
                )
                WHERE vendor.id = ANY(affected_vendor_ids);

                RETURN NULL;
            END;
            $$
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE TRIGGER reviews_sync_vendor_average_rating
            AFTER INSERT OR UPDATE OR DELETE ON reviews
            FOR EACH ROW
            EXECUTE FUNCTION sync_vendor_average_rating()
            """
        )
    )


def downgrade() -> None:
    """Remove internal-review average synchronization and storage."""
    op.execute(
        sa.text(
            "DROP TRIGGER reviews_sync_vendor_average_rating ON reviews"
        )
    )
    op.execute(sa.text("DROP FUNCTION sync_vendor_average_rating()"))
    op.drop_constraint(
        op.f("ck_vendors_average_rating_range"),
        "vendors",
        type_="check",
    )
    op.drop_column("vendors", "average_rating")
