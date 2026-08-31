from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

from app.db.base import NAMING_CONVENTION


class VectorBase(DeclarativeBase):
    """Separate metadata for pgvector-backed tables.

    Kept off the shared application ``Base`` so SQLite test schemas never try
    to create the pgvector ``vector`` column type.
    """

    metadata = MetaData(naming_convention=NAMING_CONVENTION)
