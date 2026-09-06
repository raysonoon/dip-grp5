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
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.google_review import GoogleReview
    from app.models.review import Review


class Vendor(Base):
    __tablename__ = "vendors"

    __table_args__ = (
        UniqueConstraint(
            "directory_id",
            name="uq_vendors_directory_id",
        ),
        CheckConstraint(
            "average_google_rating IS NULL "
            "OR average_google_rating BETWEEN 0 AND 5",
            name="average_google_rating_range",
        ),
        CheckConstraint(
            "google_review_count IS NULL OR google_review_count >= 0",
            name="google_review_count_nonnegative",
        ),
        Index("ix_vendors_google_place_id", "google_place_id"),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    directory_id: Mapped[str | None] = mapped_column(
        String(10),
        nullable=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    level_unit: Mapped[str | None] = mapped_column(String(50), nullable=True)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    opening_hours: Mapped[str | None] = mapped_column(String(255), nullable=True)
    price_range: Mapped[str | None] = mapped_column(String(20), nullable=True)
    halal: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    vegetarian: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    average_google_rating: Mapped[float | None] = mapped_column(
        Numeric(2, 1),
        nullable=True,
    )
    google_place_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    google_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    google_review_count: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    google_price_range: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )
    google_address: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )
    google_main_category: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    google_categories: Mapped[list[str] | None] = mapped_column(
        JSON,
        nullable=True,
    )
    website_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    phone_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    google_hours: Mapped[list[dict[str, object]] | None] = mapped_column(
        JSON,
        nullable=True,
    )
    google_status: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    is_temporarily_closed: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
    )
    is_permanently_closed: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
    )
    google_maps_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    google_search_query: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    reviews: Mapped[list["Review"]] = relationship(back_populates="vendor")
    google_reviews: Mapped[list["GoogleReview"]] = relationship(
        back_populates="vendor"
    )
    images: Mapped[list["VendorImage"]] = relationship(
        back_populates="vendor",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="VendorImage.display_order",
    )


class VendorImage(Base):
    __tablename__ = "vendor_images"
    __table_args__ = (
        CheckConstraint(
            "display_order >= 1",
            name="display_order_positive",
        ),
        UniqueConstraint(
            "vendor_id",
            "display_order",
            name="uq_vendor_images_vendor_display_order",
        ),
        Index("ix_vendor_images_vendor_id", "vendor_id"),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    vendor_id: Mapped[int] = mapped_column(
        ForeignKey("vendors.id", ondelete="CASCADE"),
        nullable=False,
    )
    image_url: Mapped[str] = mapped_column(Text, nullable=False)
    display_order: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    vendor: Mapped[Vendor] = relationship(back_populates="images")

