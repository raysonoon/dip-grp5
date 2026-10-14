from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.review import Review
    from app.models.user import User


class ReviewVote(Base):
    __tablename__ = "review_votes"
    __table_args__ = (
        CheckConstraint(
            "vote_type IN ('up', 'down')",
            name="vote_type_allowed",
        ),
        UniqueConstraint(
            "review_id",
            "user_id",
            name="uq_review_votes_review_user",
        ),
        Index("ix_review_votes_review_id", "review_id"),
        Index("ix_review_votes_user_id", "user_id"),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        Identity(),
        primary_key=True,
    )
    review_id: Mapped[int] = mapped_column(
        ForeignKey("reviews.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    vote_type: Mapped[str] = mapped_column(
        String(4),
        nullable=False,
    )

    review: Mapped["Review"] = relationship()
    user: Mapped["User"] = relationship()