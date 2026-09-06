"""separate google reviews from app reviews

Revision ID: b80ac6cf803c
Revises: 3c18912afb0a
Create Date: 2026-09-05 21:11:55.247649

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b80ac6cf803c'
down_revision: Union[str, Sequence[str], None] = '3c18912afb0a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Separate imported Google reviews from app-user reviews."""

    op.create_table(
        "google_reviews",
        sa.Column(
            "id",
            sa.Integer(),
            sa.Identity(always=False),
            nullable=False,
        ),
        sa.Column("vendor_id", sa.Integer(), nullable=False),
        sa.Column(
            "external_review_id",
            sa.String(length=255),
            nullable=False,
        ),
        sa.Column(
            "rating_half_steps",
            sa.SmallInteger(),
            nullable=False,
        ),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column(
            "published_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["vendor_id"],
            ["vendors.id"],
            name=op.f("fk_google_reviews_vendor_id_vendors"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "id",
            name=op.f("pk_google_reviews"),
        ),
        sa.UniqueConstraint(
            "external_review_id",
            name=op.f("uq_google_reviews_external_review_id"),
        ),
    )

    # Move existing imported Google reviews into the new table.
    op.execute(
        sa.text(
            """
            INSERT INTO google_reviews (
                vendor_id,
                external_review_id,
                rating_half_steps,
                comment,
                published_at
            )
            SELECT
                vendor_id,
                external_review_id,
                rating_half_steps,
                comment,
                created_at
            FROM reviews
            WHERE source = 'google'
            """
        )
    )

    # Remove Google rows from the app reviews table.
    op.execute(
        sa.text(
            """
            DELETE FROM reviews
            WHERE source = 'google'
            """
        )
    )

    # Remaining reviews are app reviews and must belong to a user.
    op.alter_column(
        "reviews",
        "user_id",
        existing_type=sa.INTEGER(),
        nullable=False,
    )

    op.drop_constraint(
        "uq_reviews_source_external_review_id",
        "reviews",
        type_="unique",
    )
    op.drop_constraint(
        "ck_reviews_review_source_allowed",
        "reviews",
        type_="check",
    )

    op.drop_column("reviews", "source")
    op.drop_column("reviews", "external_review_id")


def downgrade() -> None:
    """Restore the combined review-table design."""

    op.add_column(
        "reviews",
        sa.Column(
            "external_review_id",
            sa.String(length=255),
            nullable=True,
        ),
    )

    op.add_column(
        "reviews",
        sa.Column(
            "source",
            sa.String(length=20),
            server_default="app",
            nullable=False,
        ),
    )

    op.alter_column(
        "reviews",
        "user_id",
        existing_type=sa.INTEGER(),
        nullable=True,
    )

    # Copy Google reviews back into the combined reviews table.
    op.execute(
        sa.text(
            """
            INSERT INTO reviews (
                user_id,
                vendor_id,
                source,
                external_review_id,
                rating_half_steps,
                comment,
                created_at,
                updated_at
            )
            SELECT
                NULL,
                vendor_id,
                'google',
                external_review_id,
                rating_half_steps,
                comment,
                published_at,
                NULL
            FROM google_reviews
            """
        )
    )

    op.create_unique_constraint(
        "uq_reviews_source_external_review_id",
        "reviews",
        ["source", "external_review_id"],
    )

    op.create_check_constraint(
        "ck_reviews_review_source_allowed",
        "reviews",
        "source IN ('app', 'google')",
    )

    op.drop_table("google_reviews")

