"""add vendor embeddings

Revision ID: c4769c420363
Revises: 92807e168297
Create Date: 2026-10-19 11:18:42.031949

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision: str = 'c4769c420363'
down_revision: Union[str, Sequence[str], None] = '92807e168297'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "vendor_embeddings",
        sa.Column(
            "id",
            sa.Integer(),
            sa.Identity(always=False),
            nullable=False,
        ),
        sa.Column("vendor_id", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(768), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint(
            "id",
            name=op.f("pk_vendor_embeddings"),
        ),
        sa.UniqueConstraint(
            "vendor_id",
            name="uq_vendor_embeddings_vendor_id",
        ),
    )

    op.create_index(
        "ix_vendor_embeddings_embedding_hnsw",
        "vendor_embeddings",
        ["embedding"],
        unique=False,
        postgresql_using="hnsw",
        postgresql_ops={
            "embedding": "vector_cosine_ops",
        },
        postgresql_with={
            "m": 16,
            "ef_construction": 64,
        },
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "ix_vendor_embeddings_embedding_hnsw",
        table_name="vendor_embeddings",
        postgresql_using="hnsw",
        postgresql_ops={
            "embedding": "vector_cosine_ops",
        },
        postgresql_with={
            "m": 16,
            "ef_construction": 64,
        },
    )

    op.drop_table("vendor_embeddings")
