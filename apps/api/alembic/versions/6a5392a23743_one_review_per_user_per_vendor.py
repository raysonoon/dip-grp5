"""one review per user per vendor

Revision ID: 6a5392a23743
Revises: c4769c420363
Create Date: 2026-10-24 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '6a5392a23743'
down_revision: Union[str, Sequence[str], None] = 'c4769c420363'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Every review except the most recent one for each (user_id, vendor_id).
DUPLICATE_REVIEW_IDS = """
    SELECT id FROM (
        SELECT
            id,
            ROW_NUMBER() OVER (
                PARTITION BY user_id, vendor_id
                ORDER BY created_at DESC, id DESC
            ) AS position
        FROM reviews
    ) AS ranked
    WHERE position > 1
"""


def upgrade() -> None:
    """Upgrade schema."""
    # Chatbot chunks reference reviews by id without a foreign key, so remove
    # them explicitly. Review images and votes cascade with the review.
    op.execute(
        f"""
        DELETE FROM knowledge_chunks
        WHERE source_type = 'internal_review'
          AND source_id IN (
              SELECT CAST(id AS VARCHAR) FROM ({DUPLICATE_REVIEW_IDS}) AS duplicates
          )
        """
    )
    op.execute(f"DELETE FROM reviews WHERE id IN ({DUPLICATE_REVIEW_IDS})")
    op.create_unique_constraint(
        "uq_reviews_user_vendor",
        "reviews",
        ["user_id", "vendor_id"],
    )


def downgrade() -> None:
    """Downgrade schema.

    Removed duplicate reviews are not restored.
    """
    op.drop_constraint("uq_reviews_user_vendor", "reviews", type_="unique")
