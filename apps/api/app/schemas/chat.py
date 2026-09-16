from pydantic import BaseModel, ConfigDict, Field, field_validator


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=2000)

    @field_validator("question")
    @classmethod
    def question_not_blank(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("question cannot be empty")
        return normalized


class ChatSource(BaseModel):
    source_type: str
    source_id: str | None = None
    vendor_id: int | None = None
    vendor_name: str | None = None
    excerpt: str | None = None
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