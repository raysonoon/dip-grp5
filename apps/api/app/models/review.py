from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.vendor import Vendor


class Review(Base):
    __tablename__ = "reviews"
    __table_args__ = (
        CheckConstraint(
            "rating_half_steps BETWEEN 2 AND 10",
            name="rating_half_steps_range",
        ),
        Index("ix_reviews_user_id", "user_id"),
        Index("ix_reviews_vendor_created_at", "vendor_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    vendor_id: Mapped[int] = mapped_column(
        ForeignKey("vendors.id", ondelete="RESTRICT"),
        nullable=False,
    )
    rating_half_steps: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    user: Mapped["User"] = relationship(back_populates="reviews")
    vendor: Mapped["Vendor"] = relationship(back_populates="reviews")
    images: Mapped[list["ReviewImage"]] = relationship(
        back_populates="review",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ReviewImage.display_order",
    )


class ReviewImage(Base):
    __tablename__ = "review_images"
    __table_args__ = (
        CheckConstraint(
            "mime_type IN ('image/jpeg', 'image/png')",
            name="mime_type_allowed",
        ),
        CheckConstraint(
            "file_size_bytes BETWEEN 1 AND 5242880",
            name="file_size_bytes_range",
        ),
        CheckConstraint(
            "display_order BETWEEN 1 AND 5",
            name="display_order_range",
        ),
        UniqueConstraint(
            "review_id",
            "display_order",
            name="uq_review_images_review_display_order",
        ),
        Index("ix_review_images_review_id", "review_id"),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    review_id: Mapped[int] = mapped_column(
        ForeignKey("reviews.id", ondelete="CASCADE"),
        nullable=False,
    )
    image_url: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(20), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    display_order: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    review: Mapped[Review] = relationship(back_populates="images")

