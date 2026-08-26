from datetime import datetime

from pydantic import BaseModel


class VendorListItem(BaseModel):
    id: int
    name: str
    location: str | None
    image_url: str | None
    category: str | None
    opening_hours: str | None
    created_at: datetime
    average_rating: float | None
    review_count: int


class VendorListRead(BaseModel):
    items: list[VendorListItem]
    total: int
    limit: int
    offset: int
