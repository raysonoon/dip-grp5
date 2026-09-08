from datetime import datetime, timezone
from itertools import count
from pathlib import Path as FilePath
from typing import Annotated

from fastapi import (
    APIRouter,
    File,
    HTTPException,
    Path,
    Query,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.api.dependencies import AdminUser, DbSession
from app.core.image_storage import get_storage
from app.core.image_upload import read_image_upload
from app.models import Review, Vendor, VendorImage
from app.schemas import (
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
        mime_type=image.mime_type,
        file_size_bytes=image.file_size_bytes,
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
    return get_storage().resolve(
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
                unit_code=vendor.unit_code,
                image_url=(vendor.images[0].image_url if vendor.images else None),
                category=vendor.category,
                opening_hours=vendor.opening_hours,
                price_range=vendor.price_range,
                halal=vendor.halal,
                vegetarian=vendor.vegetarian,
                average_google_rating=(
                    None
                    if vendor.average_google_rating is None
                    else float(vendor.average_google_rating)
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
                        mime_type=image.mime_type,
                        file_size_bytes=image.file_size_bytes,
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
async def create_vendor_image(
    vendor_id: Annotated[int, Path(gt=0)],
    session: DbSession,
    _current_admin: AdminUser,
    file: Annotated[UploadFile, File(description="JPEG or PNG image")],
) -> VendorImageRead:
    vendor = _get_vendor(vendor_id, session)
    contents, mime_type, extension = await read_image_upload(file)

    used_orders = set(
        session.scalars(
            select(VendorImage.display_order).where(
                VendorImage.vendor_id == vendor_id
            )
        ).all()
    )
    display_order = next(
        order
        for order in count(1)
        if order not in used_orders
    )

    image = VendorImage(
        vendor_id=vendor_id,
        image_url="pending",
        mime_type=mime_type,
        file_size_bytes=len(contents),
        display_order=display_order,
    )
    vendor.updated_at = datetime.now(timezone.utc)
    session.add(image)
    try:
        session.flush()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="display_order is already used for this vendor",
        ) from error

    image.image_url = (
        f"/media/vendor_images/{vendor_id}/{image.id}{extension}"
    )
    storage = get_storage()
    try:
        storage.save(
            collection="vendor_images",
            owner_id=vendor_id,
            reference=image.image_url,
            data=contents,
        )
        session.commit()
    except OSError as error:
        session.rollback()
        storage.delete(
            collection="vendor_images",
            owner_id=vendor_id,
            reference=image.image_url,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not store vendor image",
        ) from error
    except IntegrityError as error:
        session.rollback()
        storage.delete(
            collection="vendor_images",
            owner_id=vendor_id,
            reference=image.image_url,
        )
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
