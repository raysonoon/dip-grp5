"""add user, vendor image, and review edit fields

Revision ID: a8f1c2d3e4b5
Revises: 66ba667f797c
Create Date: 2026-08-27

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "a8f1c2d3e4b5"
down_revision: Union[str, Sequence[str], None] = "66ba667f797c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("display_name", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("email_address", sa.String(length=320), nullable=True),
    )
    op.execute(
        """
        UPDATE users
        SET display_name = username,
            email_address = CASE
                WHEN username = 'admin' THEN 'admin@local.invalid'
                WHEN username = 'test_user' THEN 'test-user@local.invalid'
                ELSE 'legacy-' || id::text || '@local.invalid'
            END
        """
    )
    op.alter_column("users", "display_name", nullable=False)
    op.alter_column("users", "email_address", nullable=False)
    op.create_unique_constraint(
        op.f("uq_users_email_address"),
        "users",
        ["email_address"],
    )
    op.drop_constraint(op.f("uq_users_username"), "users", type_="unique")
    op.drop_column("users", "username")

    op.add_column(
        "vendors",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_table(
        "vendor_images",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("vendor_id", sa.Integer(), nullable=False),
        sa.Column("image_url", sa.Text(), nullable=False),
        sa.Column("display_order", sa.SmallInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "display_order >= 1",
            name=op.f("ck_vendor_images_display_order_positive"),
        ),
        sa.ForeignKeyConstraint(
            ["vendor_id"],
            ["vendors.id"],
            name=op.f("fk_vendor_images_vendor_id_vendors"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_vendor_images")),
        sa.UniqueConstraint(
            "vendor_id",
            "display_order",
            name="uq_vendor_images_vendor_display_order",
        ),
    )
    op.create_index(
        "ix_vendor_images_vendor_id",
        "vendor_images",
        ["vendor_id"],
        unique=False,
    )
    op.execute(
        """
        INSERT INTO vendor_images (vendor_id, image_url, display_order, created_at)
        SELECT id, image_url, 1, created_at
        FROM vendors
        WHERE image_url IS NOT NULL AND btrim(image_url) <> ''
        """
    )
    op.drop_column("vendors", "image_url")

    op.add_column(
        "reviews",
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("reviews", "updated_at")

    op.add_column("vendors", sa.Column("image_url", sa.Text(), nullable=True))
    op.execute(
        """
        UPDATE vendors AS vendor
        SET image_url = first_image.image_url
        FROM (
            SELECT DISTINCT ON (vendor_id) vendor_id, image_url
            FROM vendor_images
            ORDER BY vendor_id, display_order, id
        ) AS first_image
        WHERE first_image.vendor_id = vendor.id
        """
    )
    op.drop_index("ix_vendor_images_vendor_id", table_name="vendor_images")
    op.drop_table("vendor_images")
    op.drop_column("vendors", "updated_at")

    op.add_column(
        "users",
        sa.Column("username", sa.String(length=50), nullable=True),
    )
    op.execute(
        """
        UPDATE users
        SET username = CASE
            WHEN email_address = 'admin@local.invalid' THEN 'admin'
            WHEN email_address = 'test-user@local.invalid' THEN 'test_user'
            ELSE left(display_name, 35) || '_' || id::text
        END
        """
    )
    op.alter_column("users", "username", nullable=False)
    op.create_unique_constraint(
        op.f("uq_users_username"),
        "users",
        ["username"],
    )
    op.drop_constraint(
        op.f("uq_users_email_address"),
        "users",
        type_="unique",
    )
    op.drop_column("users", "email_address")
    op.drop_column("users", "display_name")
