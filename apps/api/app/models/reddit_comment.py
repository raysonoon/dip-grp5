from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Identity,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.vendor import Vendor


class RedditComment(Base):
    __tablename__ = "reddit_comments"

    id: Mapped[int] = mapped_column(
        Integer,
        Identity(),
        primary_key=True,
    )

    reddit_comment_id: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        unique=True,
    )

    vendor_id: Mapped[int | None] = mapped_column(
        ForeignKey("vendors.id", ondelete="SET NULL"),
        nullable=True,
    )

    author: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    subreddit: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    thread_id: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )

    thread_title: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    comment_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    mentioned_vendors: Mapped[list[str] | None] = mapped_column(
        JSON,
        nullable=True,
    )

    permalink: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    vendor: Mapped["Vendor | None"] = relationship(
        back_populates="reddit_comments"
    )