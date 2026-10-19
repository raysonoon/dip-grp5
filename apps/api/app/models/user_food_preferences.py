from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

preference_list_type = JSON().with_variant(
    ARRAY(String()),
    "postgresql",
)

class UserFoodPreferences(Base):
    __tablename__ = "user_food_preferences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    dietary_restrictions: Mapped[list[str]] = mapped_column(
        preference_list_type,
        nullable=False,
        default=list,
    )

    cuisines: Mapped[list[str]] = mapped_column(
        preference_list_type,
        nullable=False,
        default=list,
    )

    locations: Mapped[list[str]] = mapped_column(
        preference_list_type,
        nullable=False,
        default=list,
    )

    likes: Mapped[list[str]] = mapped_column(
        preference_list_type,
        nullable=False,
        default=list,
    )

    dislikes: Mapped[list[str]] = mapped_column(
        preference_list_type,
        nullable=False,
        default=list,
    )

    lifestyle: Mapped[list[str]] = mapped_column(
        preference_list_type,
        nullable=False,
        default=list,
    )

    onboarding_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
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

    __table_args__ = (
        CheckConstraint(
            "onboarding_status IN ('completed', 'skipped')",
            name="user_food_preferences_onboarding_status_allowed",
        ),
    )

    user = relationship("User", back_populates="food_preferences")