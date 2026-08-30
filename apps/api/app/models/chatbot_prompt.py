from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Identity,
    Integer,
    String,
    Text,
    func,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, validates

from app.db.base import Base


class ChatbotPrompt(Base):
    __tablename__ = "chatbot_prompts"
    __table_args__ = (
        CheckConstraint(
            "length(trim(intent_key)) > 0",
            name="intent_key_not_blank",
        ),
        CheckConstraint(
            "length(trim(question_scope)) > 0",
            name="question_scope_not_blank",
        ),
        CheckConstraint(
            "prompt_template IS NULL OR length(trim(prompt_template)) > 0",
            name="prompt_template_not_blank",
        ),
        CheckConstraint(
            "question_text IS NULL OR length(trim(question_text)) > 0",
            name="question_text_not_blank",
        ),
        CheckConstraint(
            "search_type IS NULL OR "
            "search_type IN ('SQL', 'Vector', 'SQL + Vector')",
            name="search_type_allowed",
        ),
        CheckConstraint(
            "source_file IS NULL OR length(trim(source_file)) > 0",
            name="source_file_not_blank",
        ),
        CheckConstraint(
            "question_text IS NULL OR search_type IS NOT NULL",
            name="question_has_search_type",
        ),
        CheckConstraint(
            "question_text IS NOT NULL OR prompt_template IS NOT NULL",
            name="question_or_prompt_present",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    intent_key: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
    )
    question_scope: Mapped[str] = mapped_column(Text, nullable=False)
    question_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    search_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    source_file: Mapped[str | None] = mapped_column(String(255), nullable=True)
    prompt_template: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=true(),
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

    @validates("intent_key")
    def normalize_intent_key(self, _key: str, value: str) -> str:
        normalized = value.strip().lower()
        if not normalized:
            raise ValueError("intent_key cannot be empty")
        return normalized

    @validates("question_scope")
    def reject_blank_required_text(self, key: str, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError(f"{key} cannot be empty")
        return normalized

    @validates("question_text", "source_file", "prompt_template")
    def reject_blank_optional_text(
        self,
        key: str,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError(f"{key} cannot be empty")
        return normalized

    @validates("search_type")
    def validate_search_type(
        self,
        _key: str,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        allowed = {"SQL", "Vector", "SQL + Vector"}
        if normalized not in allowed:
            raise ValueError(f"search_type must be one of {sorted(allowed)}")
        return normalized
