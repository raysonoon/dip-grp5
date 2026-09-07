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
    google_profile: Mapped["VendorGoogleProfile | None"] = relationship(
        back_populates="vendor",
        cascade="all, delete-orphan",
        passive_deletes=True,
        uselist=False,
    )
    images: Mapped[list["VendorImage"]] = relationship(
        back_populates="vendor",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="VendorImage.display_order",
    )


class VendorGoogleProfile(Base):
    __tablename__ = "vendor_google_profiles"
    __table_args__ = (
        CheckConstraint(
            "rating IS NULL OR rating BETWEEN 0 AND 5",
            name="rating_range",
        ),
        CheckConstraint(
            "review_count IS NULL OR review_count >= 0",
            name="review_count_nonnegative",
        ),
        Index("ix_vendor_google_profiles_place_id", "place_id"),
    )

    vendor_id: Mapped[int] = mapped_column(
        ForeignKey("vendors.id", ondelete="CASCADE"),
        primary_key=True,
    )
    place_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    display_name: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )
    rating: Mapped[float | None] = mapped_column(Numeric(2, 1), nullable=True)
    review_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    price_range: Mapped[str | None] = mapped_column(String(20), nullable=True)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    categories: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    website_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    phone_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    hours: Mapped[list[dict[str, object]] | None] = mapped_column(
        JSON,
        nullable=True,
    )
    status: Mapped[str | None] = mapped_column(String(100), nullable=True)
    maps_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    search_query: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    vendor: Mapped[Vendor] = relationship(back_populates="google_profile")


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

