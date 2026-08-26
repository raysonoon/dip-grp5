from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ReviewCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vendor_id: int = Field(gt=0)
    rating: float = Field(ge=1.0, le=5.0)
    comment: str | None = None

    @field_validator("rating")
    @classmethod
    def rating_must_use_half_star_steps(cls, value: float) -> float:
        if not (value * 2).is_integer():
            raise ValueError("rating must use 0.5-star increments")
        return value

    @field_validator("comment")
    @classmethod
    def normalize_comment(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class ReviewRead(BaseModel):
    id: int
    user_id: int
    vendor_id: int
    rating: float
    comment: str | None
    created_at: datetime


class ReviewUserRead(BaseModel):
    id: int
    username: str
    affiliation: str | None


class ReviewVendorRead(BaseModel):
    id: int
    name: str
    location: str | None
    image_url: str | None
    category: str | None
    opening_hours: str | None


class ReviewImageRead(BaseModel):
    id: int
    image_url: str
    mime_type: str
    file_size_bytes: int
    display_order: int


class ReviewDetailRead(BaseModel):
    id: int
    rating: float
    comment: str | None
    created_at: datetime
    user: ReviewUserRead
    vendor: ReviewVendorRead
    images: list[ReviewImageRead]


class ReviewListRead(BaseModel):
    items: list[ReviewDetailRead]
    total: int
    limit: int
    offset: int
