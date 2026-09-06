from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    JSON,
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
    __table_args__ = (
        CheckConstraint(
            "rating BETWEEN 1 AND 5",
            name="rating_range",
        ),
        CheckConstraint(
            "reviewer_review_count IS NULL OR reviewer_review_count >= 0",
            name="reviewer_review_count_nonnegative",
        ),
        CheckConstraint(
            "reviewer_photo_count IS NULL OR reviewer_photo_count >= 0",
            name="reviewer_photo_count_nonnegative",
        ),
        Index("ix_google_reviews_reviewer_id", "reviewer_id"),
    )

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

    rating: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
    )

    comment: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    review_link: Mapped[str | None] = mapped_column(Text, nullable=True)

    reviewer_name: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )

    reviewer_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    reviewer_profile_url: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    original_language: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )

    translated_comment: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    translated_language: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )

    published_at_text: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    owner_response_text: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    owner_response_age_text: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    owner_response_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    owner_response_translated_text: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    reviewer_avatar_url: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    reviewer_review_count: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    reviewer_photo_count: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    is_local_guide: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
    )

    experience_details: Mapped[list[dict[str, object]] | None] = mapped_column(
        JSON,
        nullable=True,
    )

    review_photos: Mapped[list[dict[str, object]] | None] = mapped_column(
        JSON,
        nullable=True,
    )

    review_origin: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    vendor: Mapped["Vendor"] = relationship(
        back_populates="google_reviews"
    )
