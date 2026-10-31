"""add vendor cuisine and include it in search document

Revision ID: f2b8d4c6a1e9
Revises: 5c49b77c3a16
Create Date: 2026-10-30 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f2b8d4c6a1e9"
down_revision: Union[str, Sequence[str], None] = "5c49b77c3a16"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SEARCH_DOCUMENT_SQL = (
    "lower(trim("
    "coalesce(name, '') || ' ' || "
    "coalesce(unit_code, '') || ' ' || "
    "coalesce(category, '') || ' ' || "
    "coalesce(cuisine, '') || ' ' || "
    "coalesce(location, '')"
    "))"
)

PREVIOUS_SEARCH_DOCUMENT_SQL = (
    "lower(trim("
    "coalesce(name, '') || ' ' || "
    "coalesce(unit_code, '') || ' ' || "
    "coalesce(category, '') || ' ' || "
    "coalesce(location, '')"
    "))"
)


def _drop_search_document() -> None:
    op.execute("DROP INDEX IF EXISTS ix_vendors_search_document_trgm")
    op.execute("DROP INDEX IF EXISTS ix_vendors_search_document_fts")
    op.drop_column("vendors", "search_document")


def _add_search_document(expression: str) -> None:
    op.add_column(
        "vendors",
        sa.Column(
            "search_document",
            sa.Text(),
            sa.Computed(expression, persisted=True),
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


def upgrade() -> None:
    """Add cuisine and rebuild the search document to include it."""
    op.add_column(
        "vendors",
        sa.Column("cuisine", sa.String(length=100), nullable=True),
    )
    _drop_search_document()
    _add_search_document(SEARCH_DOCUMENT_SQL)


def downgrade() -> None:
    """Remove cuisine and restore the previous search document."""
    _drop_search_document()
    _add_search_document(PREVIOUS_SEARCH_DOCUMENT_SQL)
    op.drop_column("vendors", "cuisine")
