"""add vendor full-text and fuzzy search indexes

Revision ID: b1c3d5e7f9a2
Revises: 8761d4e9277e
Create Date: 2026-09-20 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b1c3d5e7f9a2"
down_revision: Union[str, Sequence[str], None] = "8761d4e9277e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SEARCH_DOCUMENT_SQL = (
    "lower(trim("
    "coalesce(name, '') || ' ' || "
    "coalesce(unit_code, '') || ' ' || "
    "coalesce(category, '') || ' ' || "
    "coalesce(location, '')"
    "))"
)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.add_column(
        "vendors",
        sa.Column(
            "search_document",
            sa.Text(),
            sa.Computed(SEARCH_DOCUMENT_SQL, persisted=True),
            nullable=False,
        ),
    )
    op.execute(
        "CREATE INDEX ix_vendors_search_document_fts "
        "ON vendors USING gin "
        "(to_tsvector('simple', search_document))"
    )
    op.execute(
        "CREATE INDEX ix_vendors_search_document_trgm "
        "ON vendors USING gin (search_document gin_trgm_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_vendors_search_document_trgm")
    op.execute("DROP INDEX IF EXISTS ix_vendors_search_document_fts")
    op.drop_column("vendors", "search_document")
