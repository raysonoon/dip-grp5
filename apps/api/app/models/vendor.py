from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Computed,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.google_review import GoogleReview
    from app.models.reddit_comment import RedditComment
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
            "average_rating IS NULL OR average_rating BETWEEN 0 AND 5",
            name="average_rating_range",
        ),
        Index(
            "ix_vendors_search_document_fts",
            text("to_tsvector('simple', search_document)"),
            postgresql_using="gin",
        ).ddl_if(dialect="postgresql"),
        Index(
            "ix_vendors_search_document_trgm",
            "search_document",
            postgresql_using="gin",
            postgresql_ops={"search_document": "gin_trgm_ops"},
        ).ddl_if(dialect="postgresql"),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    directory_id: Mapped[str | None] = mapped_column(
        String(10),
        nullable=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    unit_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    opening_hours: Mapped[str | None] = mapped_column(String(255), nullable=True)
    price_range: Mapped[str | None] = mapped_column(String(20), nullable=True)
    halal: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    vegetarian: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    average_google_rating: Mapped[float | None] = mapped_column(
        Numeric(2, 1),
        nullable=True,
    )
    average_rating: Mapped[float | None] = mapped_column(
        Numeric(2, 1),
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
    search_document: Mapped[str] = mapped_column(
        Text,
        Computed(
            "lower(trim("
            "coalesce(name, '') || ' ' || "
            "coalesce(unit_code, '') || ' ' || "
            "coalesce(category, '') || ' ' || "
            "coalesce(location, '')"
            "))",
            persisted=True,
        ),
        nullable=False,
    )

    reviews: Mapped[list["Review"]] = relationship(back_populates="vendor")
    google_reviews: Mapped[list["GoogleReview"]] = relationship(
        back_populates="vendor"
    )

    reddit_comments: Mapped[list["RedditComment"]] = relationship(
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
    mime_type: Mapped[str] = mapped_column(String(20), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    display_order: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    vendor: Mapped[Vendor] = relationship(back_populates="images")

