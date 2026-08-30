from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Identity,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.review import Review


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    email_address: Mapped[str] = mapped_column(
        String(320),
        nullable=False,
    )
    email_canonical: Mapped[str] = mapped_column(
        String(320),
        nullable=False,
    )
    __table_args__ = (
        CheckConstraint(
            "role IN ('user', 'admin')",
            name="role_allowed",
        ),
        CheckConstraint(
            "email_canonical = lower(trim(email_address))",
            name="email_canonical_matches_address",
        ),
        Index(
            "uq_users_email_canonical",
            email_canonical,
            unique=True,
        ),
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="user",
        server_default="user",
    )
    affiliation: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    reviews: Mapped[list["Review"]] = relationship(back_populates="user")

    @validates("email_address")
    def normalize_email_address(self, _key: str, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("email_address cannot be empty")
        self.email_canonical = normalized.lower()
        return normalized

