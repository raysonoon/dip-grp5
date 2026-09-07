"""normalize vendor Google profiles

Revision ID: k1e3f5a7b9c0
Revises: j0d2f4a6b8e9
Create Date: 2026-09-07 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "k1e3f5a7b9c0"
down_revision: Union[str, Sequence[str], None] = "j0d2f4a6b8e9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Move Google-only fields out of the core vendors table without data loss."""
    op.create_table(
        "vendor_google_profiles",
        sa.Column("vendor_id", sa.Integer(), nullable=False),
        sa.Column("place_id", sa.String(length=100), nullable=True),
        sa.Column("display_name", sa.String(length=200), nullable=True),
        sa.Column("rating", sa.Numeric(precision=2, scale=1), nullable=True),
        sa.Column("review_count", sa.Integer(), nullable=True),
        sa.Column("price_range", sa.String(length=20), nullable=True),
        sa.Column("address", sa.String(length=500), nullable=True),
        sa.Column("categories", sa.JSON(), nullable=True),
        sa.Column("website_url", sa.Text(), nullable=True),
        sa.Column("phone_number", sa.String(length=50), nullable=True),
        sa.Column("hours", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=100), nullable=True),
        sa.Column("maps_url", sa.Text(), nullable=True),
        sa.Column("search_query", sa.String(length=255), nullable=True),
        sa.CheckConstraint(
            "rating IS NULL OR rating BETWEEN 0 AND 5",
            name=op.f("ck_vendor_google_profiles_rating_range"),
        ),
        sa.CheckConstraint(
            "review_count IS NULL OR review_count >= 0",
            name=op.f("ck_vendor_google_profiles_review_count_nonnegative"),
        ),
        sa.ForeignKeyConstraint(
            ["vendor_id"],
            ["vendors.id"],
            name=op.f("fk_vendor_google_profiles_vendor_id_vendors"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "vendor_id",
            name=op.f("pk_vendor_google_profiles"),
        ),
    )
    op.create_index(
        "ix_vendor_google_profiles_place_id",
        "vendor_google_profiles",
        ["place_id"],
        unique=False,
    )

    op.execute(
        sa.text(
            """
            INSERT INTO vendor_google_profiles (
                vendor_id,
                place_id,
                display_name,
                rating,
                review_count,
                price_range,
                address,
                categories,
                website_url,
                phone_number,
                hours,
                status,
                maps_url,
                search_query
            )
            SELECT
                id,
                google_place_id,
                google_name,
                average_google_rating,
                google_review_count,
                google_price_range,
                google_address,
                CASE
                    WHEN google_main_category IS NULL THEN google_categories
                    WHEN google_categories IS NULL
                        THEN json_build_array(google_main_category)
                    WHEN google_categories::jsonb ->> 0 = google_main_category
                        THEN google_categories
                    ELSE (
                        jsonb_build_array(google_main_category)
                        || google_categories::jsonb
                    )::json
                END,
                website_url,
                phone_number,
                google_hours,
                CASE
                    WHEN google_status IS NOT NULL THEN google_status
                    WHEN is_permanently_closed IS TRUE
                        THEN 'permanently_closed'
                    WHEN is_temporarily_closed IS TRUE
                        THEN 'temporarily_closed'
                    WHEN is_permanently_closed IS FALSE
                        AND is_temporarily_closed IS FALSE
                        THEN 'open'
                    ELSE NULL
                END,
                google_maps_url,
                google_search_query
            FROM vendors
            WHERE
                google_place_id IS NOT NULL
                OR google_name IS NOT NULL
                OR average_google_rating IS NOT NULL
                OR google_review_count IS NOT NULL
                OR google_price_range IS NOT NULL
                OR google_address IS NOT NULL
                OR google_main_category IS NOT NULL
                OR google_categories IS NOT NULL
                OR website_url IS NOT NULL
                OR phone_number IS NOT NULL
                OR google_hours IS NOT NULL
                OR google_status IS NOT NULL
                OR is_temporarily_closed IS NOT NULL
                OR is_permanently_closed IS NOT NULL
                OR google_maps_url IS NOT NULL
                OR google_search_query IS NOT NULL
            """
        )
    )

    op.drop_index("ix_vendors_google_place_id", table_name="vendors")
    op.drop_constraint(
        op.f("ck_vendors_google_review_count_nonnegative"),
        "vendors",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_vendors_average_google_rating_range"),
        "vendors",
        type_="check",
    )
    for column_name in (
        "google_search_query",
        "google_maps_url",
        "is_permanently_closed",
        "is_temporarily_closed",
        "google_status",
        "google_hours",
        "phone_number",
        "website_url",
        "google_categories",
        "google_main_category",
        "google_address",
        "google_price_range",
        "google_review_count",
        "google_name",
        "google_place_id",
        "average_google_rating",
    ):
        op.drop_column("vendors", column_name)


def downgrade() -> None:
    """Restore the denormalized Google columns on vendors."""
    op.add_column(
        "vendors",
        sa.Column(
            "average_google_rating",
            sa.Numeric(precision=2, scale=1),
            nullable=True,
        ),
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
        sa.Column("google_price_range", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "vendors",
        sa.Column("google_address", sa.String(length=500), nullable=True),
    )
    op.add_column(
        "vendors",
        sa.Column("google_main_category", sa.String(length=100), nullable=True),
    )
    op.add_column("vendors", sa.Column("google_categories", sa.JSON(), nullable=True))
    op.add_column("vendors", sa.Column("website_url", sa.Text(), nullable=True))
    op.add_column(
        "vendors",
        sa.Column("phone_number", sa.String(length=50), nullable=True),
    )
    op.add_column("vendors", sa.Column("google_hours", sa.JSON(), nullable=True))
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
    op.add_column("vendors", sa.Column("google_maps_url", sa.Text(), nullable=True))
    op.add_column(
        "vendors",
        sa.Column("google_search_query", sa.String(length=255), nullable=True),
    )

    op.execute(
        sa.text(
            """
            UPDATE vendors AS vendor
            SET
                average_google_rating = profile.rating,
                google_place_id = profile.place_id,
                google_name = profile.display_name,
                google_review_count = profile.review_count,
                google_price_range = profile.price_range,
                google_address = profile.address,
                google_main_category = profile.categories::jsonb ->> 0,
                google_categories = profile.categories,
                website_url = profile.website_url,
                phone_number = profile.phone_number,
                google_hours = profile.hours,
                google_status = profile.status,
                is_temporarily_closed = CASE
                    WHEN lower(profile.status) = 'temporarily_closed' THEN TRUE
                    WHEN lower(profile.status) IN ('permanently_closed', 'open')
                        THEN FALSE
                    ELSE NULL
                END,
                is_permanently_closed = CASE
                    WHEN lower(profile.status) = 'permanently_closed' THEN TRUE
                    WHEN lower(profile.status) IN ('temporarily_closed', 'open')
                        THEN FALSE
                    ELSE NULL
                END,
                google_maps_url = profile.maps_url,
                google_search_query = profile.search_query
            FROM vendor_google_profiles AS profile
            WHERE profile.vendor_id = vendor.id
            """
        )
    )

    op.create_check_constraint(
        op.f("ck_vendors_average_google_rating_range"),
        "vendors",
        "average_google_rating IS NULL OR average_google_rating BETWEEN 0 AND 5",
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
    op.drop_index(
        "ix_vendor_google_profiles_place_id",
        table_name="vendor_google_profiles",
    )
    op.drop_table("vendor_google_profiles")
