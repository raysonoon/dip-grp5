from datetime import datetime

from pydantic import BaseModel


class FavouriteVendorRead(BaseModel):
    id: int
    name: str


class FavouriteRead(BaseModel):
    vendor: FavouriteVendorRead
    created_at: datetime


class FavouriteListRead(BaseModel):
    items: list[FavouriteRead]
    total: int
    limit: int
    offset: int


class FavouriteStateRead(BaseModel):
    vendor_id: int
    favourited: bool
    created_at: datetime | None
