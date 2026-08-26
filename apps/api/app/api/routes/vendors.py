from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import func, or_, select

from app.api.dependencies import DbSession
from app.models import Review, Vendor
from app.schemas import VendorListItem, VendorListRead


router = APIRouter(prefix="/vendors", tags=["vendors"])


@router.get("", response_model=VendorListRead)
def list_vendors(
    session: DbSession,
    q: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> VendorListRead:
    filters = []
    if q is not None and (search_text := q.strip()):
        search_pattern = f"%{search_text}%"
        filters.append(
            or_(
                Vendor.name.ilike(search_pattern),
                Vendor.location.ilike(search_pattern),
                Vendor.category.ilike(search_pattern),
            )
        )

    total = session.scalar(
        select(func.count(Vendor.id)).where(*filters)
    )
    rows = session.execute(
        select(
            Vendor,
            func.count(Review.id).label("review_count"),
            func.avg(Review.rating_half_steps).label("average_half_steps"),
        )
        .outerjoin(Review, Review.vendor_id == Vendor.id)
        .where(*filters)
        .group_by(Vendor.id)
        .order_by(Vendor.name.asc(), Vendor.id.asc())
        .offset(offset)
        .limit(limit)
    ).all()

    items = []
    for vendor, review_count, average_half_steps in rows:
        average_rating = (
            None
            if average_half_steps is None
            else round(float(average_half_steps) / 2, 2)
        )
        items.append(
            VendorListItem(
                id=vendor.id,
                name=vendor.name,
                location=vendor.location,
                image_url=vendor.image_url,
                category=vendor.category,
                opening_hours=vendor.opening_hours,
                created_at=vendor.created_at,
                average_rating=average_rating,
                review_count=review_count,
            )
        )

    return VendorListRead(
        items=items,
        total=total or 0,
        limit=limit,
        offset=offset,
    )
