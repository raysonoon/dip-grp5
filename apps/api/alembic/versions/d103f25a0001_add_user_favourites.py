"""Add per-user vendor favourites.

Revision ID: d103f25a0001
Revises: c4769c420363
"""
from alembic import op
import sqlalchemy as sa


revision = "d103f25a0001"
down_revision = "c4769c420363"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_favourites",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("vendor_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE",
            name=op.f("fk_user_favourites_user_id_users"),
        ),
        sa.ForeignKeyConstraint(
            ["vendor_id"], ["vendors.id"], ondelete="CASCADE",
            name=op.f("fk_user_favourites_vendor_id_vendors"),
        ),
        sa.PrimaryKeyConstraint("user_id", "vendor_id", name=op.f("pk_user_favourites")),
    )
    op.create_index(
        "ix_user_favourites_user_created_vendor", "user_favourites",
        ["user_id", "created_at", "vendor_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_user_favourites_user_created_vendor", table_name="user_favourites")
    op.drop_table("user_favourites")
