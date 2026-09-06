"""add Google vendor metadata

Revision ID: h8b0d2f4a6c7
Revises: f7a9c1e3b5d6
Create Date: 2026-09-06 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "h8b0d2f4a6c7"
down_revision: Union[str, Sequence[str], None] = "f7a9c1e3b5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add optional fields sourced from ntu_food_places_final.csv."""
    op.add_column(
        "vendors",
        sa.Column("level_unit", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "vendors",
        sa.Column("google_place_id", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "vendors",
        sa.Column("google_name", sa.String(length=200), nullable=True),
    )
    op.add_column(
        "vendors",
        sa.Column("google_review_count", sa.Integer(), nullable=True),
    )
    op.add_column(
        "vendors",
        sa.Column("google_address", sa.String(length=500), nullable=True),
    )
    op.add_column(
        "vendors",
        sa.Column("google_main_category", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "vendors",
        sa.Column("google_categories", sa.JSON(), nullable=True),
    )
    op.add_column(
        "vendors",
        sa.Column("website_url", sa.Text(), nullable=True),
    )
    op.add_column(
        "vendors",
        sa.Column("phone_number", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "vendors",
        sa.Column("google_hours", sa.JSON(), nullable=True),
    )
    op.add_column(
        "vendors",
        sa.Column("google_status", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "vendors",
        sa.Column("is_temporarily_closed", sa.Boolean(), nullable=True),
    )
    op.add_column(
        "vendors",
        sa.Column("is_permanently_closed", sa.Boolean(), nullable=True),
    )
    op.add_column(
        "vendors",
        sa.Column("google_maps_url", sa.Text(), nullable=True),
    )
    op.add_column(
        "vendors",
        sa.Column("google_search_query", sa.String(length=255), nullable=True),
    )
    op.create_check_constraint(
        op.f("ck_vendors_google_review_count_nonnegative"),
        "vendors",
        "google_review_count IS NULL OR google_review_count >= 0",
    )
    op.create_index(
        "ix_vendors_google_place_id",
        "vendors",
        ["google_place_id"],
        unique=False,
    )


def downgrade() -> None:
    """Remove fields sourced from ntu_food_places_final.csv."""
    op.drop_index("ix_vendors_google_place_id", table_name="vendors")
    op.drop_constraint(
        op.f("ck_vendors_google_review_count_nonnegative"),
        "vendors",
        type_="check",
    )
    op.drop_column("vendors", "google_search_query")
    op.drop_column("vendors", "google_maps_url")
    op.drop_column("vendors", "is_permanently_closed")
    op.drop_column("vendors", "is_temporarily_closed")
    op.drop_column("vendors", "google_status")
    op.drop_column("vendors", "google_hours")
    op.drop_column("vendors", "phone_number")
    op.drop_column("vendors", "website_url")
    op.drop_column("vendors", "google_categories")
    op.drop_column("vendors", "google_main_category")
    op.drop_column("vendors", "google_address")
    op.drop_column("vendors", "google_review_count")
    op.drop_column("vendors", "google_name")
    op.drop_column("vendors", "google_place_id")
    op.drop_column("vendors", "level_unit")
