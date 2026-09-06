"""add Google review metadata

Revision ID: j0d2f4a6b8e9
Revises: i9c1e3f5a7d8
Create Date: 2026-09-06 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "j0d2f4a6b8e9"
down_revision: Union[str, Sequence[str], None] = "i9c1e3f5a7d8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add optional fields sourced from ntu_detailed_reviews_final.csv."""
    op.add_column("google_reviews", sa.Column("review_link", sa.Text(), nullable=True))
    op.add_column(
        "google_reviews",
        sa.Column("reviewer_name", sa.String(length=200), nullable=True),
    )
    op.add_column(
        "google_reviews",
        sa.Column("reviewer_id", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "google_reviews",
        sa.Column("reviewer_profile_url", sa.Text(), nullable=True),
    )
    op.add_column(
        "google_reviews",
        sa.Column("original_language", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "google_reviews",
        sa.Column("translated_comment", sa.Text(), nullable=True),
    )
    op.add_column(
        "google_reviews",
        sa.Column("translated_language", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "google_reviews",
        sa.Column("published_at_text", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "google_reviews",
        sa.Column("owner_response_text", sa.Text(), nullable=True),
    )
    op.add_column(
        "google_reviews",
        sa.Column("owner_response_age_text", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "google_reviews",
        sa.Column("owner_response_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "google_reviews",
        sa.Column("owner_response_translated_text", sa.Text(), nullable=True),
    )
    op.add_column(
        "google_reviews",
        sa.Column("reviewer_avatar_url", sa.Text(), nullable=True),
    )
    op.add_column(
        "google_reviews",
        sa.Column("reviewer_review_count", sa.Integer(), nullable=True),
    )
    op.add_column(
        "google_reviews",
        sa.Column("reviewer_photo_count", sa.Integer(), nullable=True),
    )
    op.add_column(
        "google_reviews",
        sa.Column("is_local_guide", sa.Boolean(), nullable=True),
    )
    op.add_column(
        "google_reviews",
        sa.Column("experience_details", sa.JSON(), nullable=True),
    )
    op.add_column(
        "google_reviews",
        sa.Column("review_photos", sa.JSON(), nullable=True),
    )
    op.add_column(
        "google_reviews",
        sa.Column("review_origin", sa.String(length=50), nullable=True),
    )
    op.create_check_constraint(
        op.f("ck_google_reviews_reviewer_review_count_nonnegative"),
        "google_reviews",
        "reviewer_review_count IS NULL OR reviewer_review_count >= 0",
    )
    op.create_check_constraint(
        op.f("ck_google_reviews_reviewer_photo_count_nonnegative"),
        "google_reviews",
        "reviewer_photo_count IS NULL OR reviewer_photo_count >= 0",
    )
    op.create_index(
        "ix_google_reviews_reviewer_id",
        "google_reviews",
        ["reviewer_id"],
        unique=False,
    )


def downgrade() -> None:
    """Remove fields sourced from ntu_detailed_reviews_final.csv."""
    op.drop_index("ix_google_reviews_reviewer_id", table_name="google_reviews")
    op.drop_constraint(
        op.f("ck_google_reviews_reviewer_photo_count_nonnegative"),
        "google_reviews",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_google_reviews_reviewer_review_count_nonnegative"),
        "google_reviews",
        type_="check",
    )
    op.drop_column("google_reviews", "review_origin")
    op.drop_column("google_reviews", "review_photos")
    op.drop_column("google_reviews", "experience_details")
    op.drop_column("google_reviews", "is_local_guide")
    op.drop_column("google_reviews", "reviewer_photo_count")
    op.drop_column("google_reviews", "reviewer_review_count")
    op.drop_column("google_reviews", "reviewer_avatar_url")
    op.drop_column("google_reviews", "owner_response_translated_text")
    op.drop_column("google_reviews", "owner_response_at")
    op.drop_column("google_reviews", "owner_response_age_text")
    op.drop_column("google_reviews", "owner_response_text")
    op.drop_column("google_reviews", "published_at_text")
    op.drop_column("google_reviews", "translated_language")
    op.drop_column("google_reviews", "translated_comment")
    op.drop_column("google_reviews", "original_language")
    op.drop_column("google_reviews", "reviewer_profile_url")
    op.drop_column("google_reviews", "reviewer_id")
    op.drop_column("google_reviews", "reviewer_name")
    op.drop_column("google_reviews", "review_link")
