from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Identity,
    Integer,
    SmallInteger,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.vendor import Vendor


class GoogleReview(Base):
    __tablename__ = "google_reviews"

    id: Mapped[int] = mapped_column(
        Integer,
        Identity(),
        primary_key=True,
    )

    vendor_id: Mapped[int] = mapped_column(
        ForeignKey("vendors.id", ondelete="RESTRICT"),
        nullable=False,
    )

    external_review_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
    )

    rating_half_steps: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
    )

    comment: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    vendor: Mapped["Vendor"] = relationship(
        back_populates="google_reviews"
    )