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
    directory_id: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    opening_hours: Mapped[str | None] = mapped_column(String(255), nullable=True)
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

