from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


MAX_MESSAGES_PER_ROLE = 5


class ChatHistoryMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)

    @field_validator("content")
    @classmethod
    def content_not_blank(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("message content cannot be empty")
        return normalized


def trim_chat_history(
    history: list[ChatHistoryMessage],
) -> list[ChatHistoryMessage]:
    """Keep the newest five user and five assistant messages in order."""
    kept_indexes: set[int] = set()
    for role in ("user", "assistant"):
        role_indexes = [
            index for index, message in enumerate(history) if message.role == role
        ]
        kept_indexes.update(role_indexes[-MAX_MESSAGES_PER_ROLE:])
    return [
        message for index, message in enumerate(history) if index in kept_indexes
    ]


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str | None = Field(default=None, min_length=1, max_length=100)
    question: str = Field(min_length=1, max_length=2000)
    history: list[ChatHistoryMessage] = Field(default_factory=list, max_length=50)

    @field_validator("question")
    @classmethod
    def question_not_blank(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("question cannot be empty")
        return normalized

    @field_validator("session_id")
    @classmethod
    def session_id_not_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("session_id cannot be empty")
        return normalized

    @model_validator(mode="after")
    def cap_history_per_role(self) -> "ChatRequest":
        self.history = trim_chat_history(self.history)
        return self


class ChatSource(BaseModel):
    source_type: str
    source_id: str | None = None
    vendor_id: int | None = None
    vendor_name: str | None = None
    excerpt: str | None = None
    permalink: str | None = None
    location: str | None = None
    unit_code: str | None = None
    category: str | None = None
    price_range: str | None = None
    opening_hours: str | None = None
    rating: float | None = None
    count: int | None = None


class ChatResponse(BaseModel):
    answer: str
    sources: list[ChatSource]
    search_type: str | None = None
    intent: str | None = None
