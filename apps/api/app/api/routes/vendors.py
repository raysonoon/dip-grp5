from datetime import datetime, timezone
from pathlib import Path as FilePath
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query, Response, status
from fastapi.responses import FileResponse
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.api.dependencies import AdminUser, DbSession
from app.core.image_storage import resolve_image_path
from app.models import Review, Vendor, VendorImage
from app.schemas import (
    VendorImageCreate,
    VendorImageRead,
    VendorImageUpdate,
    VendorListItem,
    VendorListRead,
)


router = APIRouter(prefix="/vendors", tags=["vendors"])


def _vendor_image_read(image: VendorImage) -> VendorImageRead:
    return VendorImageRead(
        id=image.id,
        vendor_id=image.vendor_id,
        image_url=image.image_url,
        display_order=image.display_order,
        created_at=image.created_at,
    )


def _get_vendor(vendor_id: int, session: DbSession) -> Vendor:
    vendor = session.get(Vendor, vendor_id)
    if vendor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vendor not found",
        )
    return vendor


def _resolve_vendor_image(
    image_url: str,
    *,
    vendor_id: int,
) -> tuple[FilePath, str]:
    return resolve_image_path(
        image_url,
        collection="vendor_images",
        owner_id=vendor_id,
    )


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
        .options(
            selectinload(Vendor.images),
            selectinload(Vendor.google_profile),
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
        google_profile = vendor.google_profile
        google_status = (
            google_profile.status if google_profile is not None else None
        )
        normalized_google_status = (
            google_status.casefold() if google_status is not None else None
        )
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
                level_unit=vendor.level_unit,
                image_url=(vendor.images[0].image_url if vendor.images else None),
                category=vendor.category,
                opening_hours=vendor.opening_hours,
                price_range=vendor.price_range,
                halal=vendor.halal,
                vegetarian=vendor.vegetarian,
                average_google_rating=(
                    None
                    if google_profile is None or google_profile.rating is None
                    else float(google_profile.rating)
                ),
                google_place_id=(
                    google_profile.place_id
                    if google_profile is not None
                    else None
                ),
                google_name=(
                    google_profile.display_name
                    if google_profile is not None
                    else None
                ),
                google_review_count=(
                    google_profile.review_count
                    if google_profile is not None
                    else None
                ),
                google_price_range=(
                    google_profile.price_range
                    if google_profile is not None
                    else None
                ),
                google_address=(
                    google_profile.address
                    if google_profile is not None
                    else None
                ),
                google_main_category=(
                    google_profile.categories[0]
                    if google_profile is not None
                    and google_profile.categories
                    else None
                ),
                google_categories=(
                    google_profile.categories
                    if google_profile is not None
                    else None
                ),
                website_url=(
                    google_profile.website_url
                    if google_profile is not None
                    else None
                ),
                phone_number=(
                    google_profile.phone_number
                    if google_profile is not None
                    else None
                ),
                google_hours=(
                    google_profile.hours
                    if google_profile is not None
                    else None
                ),
                google_status=google_status,
                is_temporarily_closed=(
                    None
                    if normalized_google_status is None
                    else "temporar" in normalized_google_status
                ),
                is_permanently_closed=(
                    None
                    if normalized_google_status is None
                    else (
                        "permanent" in normalized_google_status
                        or "no longer operating" in normalized_google_status
                    )
                ),
                google_maps_url=(
                    google_profile.maps_url
                    if google_profile is not None
                    else None
                ),
                google_search_query=(
                    google_profile.search_query
                    if google_profile is not None
                    else None
                ),
                created_at=vendor.created_at,
                updated_at=vendor.updated_at,
                average_rating=average_rating,
                review_count=review_count,
                images=[
                    VendorImageRead(
                        id=image.id,
                        vendor_id=image.vendor_id,
                        image_url=image.image_url,
                        display_order=image.display_order,
                        created_at=image.created_at,
                    )
                    for image in vendor.images
                ],
            )
        )

    return VendorListRead(
        items=items,
        total=total or 0,
        limit=limit,
        offset=offset,
    )


@router.get("/{vendor_id}/images", response_model=list[VendorImageRead])
def list_vendor_images(
    vendor_id: Annotated[int, Path(gt=0)],
    session: DbSession,
) -> list[VendorImageRead]:
    _get_vendor(vendor_id, session)
    images = session.scalars(
        select(VendorImage)
        .where(VendorImage.vendor_id == vendor_id)
        .order_by(VendorImage.display_order, VendorImage.id)
    ).all()
    return [_vendor_image_read(image) for image in images]


@router.get(
    "/{vendor_id}/images/{image_id}",
    response_class=FileResponse,
)
def get_vendor_image_file(
    vendor_id: Annotated[int, Path(gt=0)],
    image_id: Annotated[int, Path(gt=0)],
    session: DbSession,
) -> FileResponse:
    image = session.scalar(
        select(VendorImage).where(
            VendorImage.id == image_id,
            VendorImage.vendor_id == vendor_id,
        )
    )
    if image is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vendor image not found",
        )

    try:
        image_path, media_type = _resolve_vendor_image(
            image.image_url,
            vendor_id=vendor_id,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Stored vendor image path is invalid",
        ) from error
    if not image_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vendor image file not found",
        )

    return FileResponse(image_path, media_type=media_type)


@router.post(
    "/{vendor_id}/images",
    response_model=VendorImageRead,
    status_code=status.HTTP_201_CREATED,
)
def create_vendor_image(
    vendor_id: Annotated[int, Path(gt=0)],
    image_data: VendorImageCreate,
    session: DbSession,
    _current_admin: AdminUser,
) -> VendorImageRead:
    vendor = _get_vendor(vendor_id, session)
    display_order = image_data.display_order
    if display_order is None:
        highest_order = session.scalar(
            select(func.max(VendorImage.display_order)).where(
                VendorImage.vendor_id == vendor_id
            )
        )
        display_order = (highest_order or 0) + 1

    try:
        _resolve_vendor_image(
            image_data.image_url,
            vendor_id=vendor_id,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error

    image = VendorImage(
        vendor_id=vendor_id,
        image_url=image_data.image_url,
        display_order=display_order,
    )
    vendor.updated_at = datetime.now(timezone.utc)
    session.add(image)
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="display_order is already used for this vendor",
        ) from error
    session.refresh(image)
    return _vendor_image_read(image)


@router.patch(
    "/{vendor_id}/images/{image_id}",
    response_model=VendorImageRead,
)
def update_vendor_image(
    vendor_id: Annotated[int, Path(gt=0)],
    image_id: Annotated[int, Path(gt=0)],
    image_data: VendorImageUpdate,
    session: DbSession,
    _current_admin: AdminUser,
) -> VendorImageRead:
    vendor = _get_vendor(vendor_id, session)
    image = session.scalar(
        select(VendorImage).where(
            VendorImage.id == image_id,
            VendorImage.vendor_id == vendor_id,
        )
    )
    if image is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vendor image not found",
        )

    if "image_url" in image_data.model_fields_set:
        image_url = image_data.image_url
        if image_url is None:  # Defensive guard; the schema rejects this input.
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="image_url cannot be null",
            )
        try:
            _resolve_vendor_image(image_url, vendor_id=vendor_id)
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=str(error),
            ) from error
        image.image_url = image_url
    if "display_order" in image_data.model_fields_set:
        display_order = image_data.display_order
        if display_order is None:  # Defensive guard; the schema rejects this input.
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="display_order cannot be null",
            )
        image.display_order = display_order
    vendor.updated_at = datetime.now(timezone.utc)

    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="display_order is already used for this vendor",
        ) from error
    session.refresh(image)
    return _vendor_image_read(image)


@router.delete(
    "/{vendor_id}/images/{image_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_vendor_image(
    vendor_id: Annotated[int, Path(gt=0)],
    image_id: Annotated[int, Path(gt=0)],
    session: DbSession,
    _current_admin: AdminUser,
) -> Response:
    vendor = _get_vendor(vendor_id, session)
    image = session.scalar(
        select(VendorImage).where(
            VendorImage.id == image_id,
            VendorImage.vendor_id == vendor_id,
        )
    )
    if image is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vendor image not found",
        )

    vendor.updated_at = datetime.now(timezone.utc)
    session.delete(image)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
