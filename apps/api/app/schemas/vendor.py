from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class VendorImageCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    image_url: str = Field(min_length=1, max_length=2048)
    display_order: int | None = Field(default=None, ge=1, le=32767)

    @field_validator("image_url")
    @classmethod
    def normalize_image_url(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("image_url cannot be empty")
        return normalized


class VendorImageUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    image_url: str | None = Field(default=None, min_length=1, max_length=2048)
    display_order: int | None = Field(default=None, ge=1, le=32767)

    @field_validator("image_url")
    @classmethod
    def normalize_image_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("image_url cannot be empty")
        return normalized

    @model_validator(mode="after")
    def require_an_update(self) -> "VendorImageUpdate":
        editable_fields = self.model_fields_set & {"image_url", "display_order"}
        if not editable_fields:
            raise ValueError("at least one image field must be provided")
        if "image_url" in editable_fields and self.image_url is None:
            raise ValueError("image_url cannot be null")
        if "display_order" in editable_fields and self.display_order is None:
            raise ValueError("display_order cannot be null")
        return self


class VendorImageRead(BaseModel):
    id: int
    vendor_id: int
    image_url: str
    display_order: int
    created_at: datetime


class VendorListItem(BaseModel):
    id: int
    name: str
    location: str | None
    level_unit: str | None
    image_url: str | None
    category: str | None
    opening_hours: str | None
    price_range: str | None
    halal: bool | None
    vegetarian: bool | None
    average_google_rating: float | None
    google_place_id: str | None
    google_name: str | None
    google_review_count: int | None
    google_price_range: str | None
    google_address: str | None
    google_main_category: str | None
    google_categories: list[str] | None
    website_url: str | None
    phone_number: str | None
    google_hours: list[dict[str, Any]] | None
    google_status: str | None
    is_temporarily_closed: bool | None
    is_permanently_closed: bool | None
    google_maps_url: str | None
    google_search_query: str | None
    created_at: datetime
    updated_at: datetime
    average_rating: float | None
    review_count: int
    images: list[VendorImageRead]


class VendorListRead(BaseModel):
    items: list[VendorListItem]
    total: int
    limit: int
    offset: int
