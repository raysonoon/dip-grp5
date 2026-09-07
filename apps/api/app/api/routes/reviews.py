from datetime import datetime, timezone
from typing import Annotated

from fastapi import (
    APIRouter,
    File,
    Form,
    HTTPException,
    Path,
    Query,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.api.dependencies import CurrentUser, DbSession
from app.core.image_storage import resolve_image_path
from app.models import Review, ReviewImage, Vendor
from app.schemas import (
    ReviewCreate,
    ReviewDetailRead,
    ReviewImageRead,
    ReviewListRead,
    ReviewRead,
    ReviewUpdate,
    ReviewUserRead,
    ReviewVendorRead,
)


router = APIRouter(prefix="/reviews", tags=["reviews"])

MAX_REVIEW_IMAGES = 5
MAX_REVIEW_IMAGE_SIZE_BYTES = 5 * 1024 * 1024


def _review_image_read(image: ReviewImage) -> ReviewImageRead:
    return ReviewImageRead(
        id=image.id,
        image_url=image.image_url,
        mime_type=image.mime_type,
        file_size_bytes=image.file_size_bytes,
        display_order=image.display_order,
    )


def _detect_image_type(contents: bytes) -> tuple[str, str] | None:
    if contents.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", ".jpg"
    if contents.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", ".png"
    return None


async def _read_review_image_file(
    file: UploadFile,
) -> tuple[bytes, str, str]:
    try:
        contents = await file.read(MAX_REVIEW_IMAGE_SIZE_BYTES + 1)
    finally:
        await file.close()

    if not contents:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Image file cannot be empty",
        )
    if len(contents) > MAX_REVIEW_IMAGE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Image file must not exceed 5 MB",
        )

    detected_type = _detect_image_type(contents)
    if detected_type is None:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only JPEG and PNG images are supported",
        )
    mime_type, extension = detected_type
    if file.content_type not in {mime_type, "application/octet-stream"}:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Uploaded content does not match its media type",
        )
    return contents, mime_type, extension


def _review_detail(review: Review) -> ReviewDetailRead:
    return ReviewDetailRead(
        id=review.id,
        rating=review.rating_half_steps / 2,
        comment=review.comment,
        created_at=review.created_at,
        updated_at=review.updated_at,
        is_edited=review.updated_at is not None,
        user=ReviewUserRead(
            id=review.user.id,
            display_name=review.user.display_name,
            affiliation=review.user.affiliation,
        ),
        vendor=ReviewVendorRead(
            id=review.vendor.id,
            name=review.vendor.name,
            location=review.vendor.location,
            image_url=(
                review.vendor.images[0].image_url
                if review.vendor.images
                else None
            ),
            category=review.vendor.category,
            opening_hours=review.vendor.opening_hours,
        ),
        images=[
            _review_image_read(image)
            for image in review.images
        ],
    )


def _review_read(review: Review) -> ReviewRead:
    return ReviewRead(
        id=review.id,
        user_id=review.user_id,
        vendor_id=review.vendor_id,
        rating=review.rating_half_steps / 2,
        comment=review.comment,
        created_at=review.created_at,
        updated_at=review.updated_at,
        is_edited=review.updated_at is not None,
    )


@router.get("", response_model=ReviewListRead)
def list_reviews(
    session: DbSession,
    vendor_id: Annotated[int | None, Query(gt=0)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ReviewListRead:
    filters = []
    if vendor_id is not None:
        filters.append(Review.vendor_id == vendor_id)

    total = session.scalar(
        select(func.count(Review.id)).where(*filters)
    )
    reviews = session.scalars(
        select(Review)
        .options(
            selectinload(Review.user),
            selectinload(Review.vendor).selectinload(Vendor.images),
            selectinload(Review.images),
        )
        .where(*filters)
        .order_by(Review.created_at.desc(), Review.id.desc())
        .offset(offset)
        .limit(limit)
    ).all()

    return ReviewListRead(
        items=[_review_detail(review) for review in reviews],
        total=total or 0,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{review_id}/images/{image_id}",
    response_class=FileResponse,
)
def get_review_image_file(
    review_id: Annotated[int, Path(gt=0)],
    image_id: Annotated[int, Path(gt=0)],
    session: DbSession,
) -> FileResponse:
    image = session.scalar(
        select(ReviewImage).where(
            ReviewImage.id == image_id,
            ReviewImage.review_id == review_id,
        )
    )
    if image is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Review image not found",
        )

    try:
        image_path, media_type = resolve_image_path(
            image.image_url,
            collection="review_images",
            owner_id=review_id,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Stored review image path is invalid",
        ) from error
    if media_type != image.mime_type:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Stored review image type does not match its path",
        )
    if not image_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Review image file not found",
        )

    return FileResponse(image_path, media_type=media_type)


@router.post(
    "/{review_id}/images",
    response_model=ReviewImageRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_review_image(
    review_id: Annotated[int, Path(gt=0)],
    session: DbSession,
    current_user: CurrentUser,
    file: Annotated[UploadFile, File(description="JPEG or PNG image")],
) -> ReviewImageRead:
    review = session.get(Review, review_id)
    if review is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Review not found",
        )
    if review.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You may upload images only to your own reviews",
        )

    used_orders = set(
        session.scalars(
            select(ReviewImage.display_order).where(
                ReviewImage.review_id == review_id
            )
        ).all()
    )
    display_order = next(
        (
            order
            for order in range(1, MAX_REVIEW_IMAGES + 1)
            if order not in used_orders
        ),
        None,
    )
    if display_order is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A review may have at most 5 images",
        )

    contents, mime_type, extension = await _read_review_image_file(file)

    image = ReviewImage(
        review_id=review_id,
        image_url="pending",
        mime_type=mime_type,
        file_size_bytes=len(contents),
        display_order=display_order,
    )
    session.add(image)
    try:
        session.flush()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The review image order changed; retry the upload",
        ) from error

    image.image_url = (
        f"/media/review_images/{review_id}/{image.id}{extension}"
    )
    image_path, _ = resolve_image_path(
        image.image_url,
        collection="review_images",
        owner_id=review_id,
    )

    try:
        image_path.parent.mkdir(parents=True, exist_ok=True)
        image_path.write_bytes(contents)
        session.commit()
    except OSError as error:
        session.rollback()
        image_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not store review image",
        ) from error
    except IntegrityError as error:
        session.rollback()
        image_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The review image order changed; retry the upload",
        ) from error

    session.refresh(image)
    return _review_image_read(image)


@router.patch(
    "/{review_id}/images/{image_id}",
    response_model=ReviewImageRead,
)
async def update_review_image(
    review_id: Annotated[int, Path(gt=0)],
    image_id: Annotated[int, Path(gt=0)],
    session: DbSession,
    current_user: CurrentUser,
    file: Annotated[UploadFile | None, File()] = None,
    display_order: Annotated[int | None, Form(ge=1, le=5)] = None,
) -> ReviewImageRead:
    review = session.get(Review, review_id)
    if review is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Review not found",
        )
    if review.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You may update images only on your own reviews",
        )

    image = session.scalar(
        select(ReviewImage).where(
            ReviewImage.id == image_id,
            ReviewImage.review_id == review_id,
        )
    )
    if image is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Review image not found",
        )
    if file is None and display_order is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Provide a replacement file or display_order",
        )

    old_path = None
    new_path = None
    old_contents = None
    if file is not None:
        contents, mime_type, extension = await _read_review_image_file(file)
        try:
            old_path, _ = resolve_image_path(
                image.image_url,
                collection="review_images",
                owner_id=review_id,
            )
        except ValueError:
            old_path = None

        image.image_url = (
            f"/media/review_images/{review_id}/{image.id}{extension}"
        )
        image.mime_type = mime_type
        image.file_size_bytes = len(contents)
        new_path, _ = resolve_image_path(
            image.image_url,
            collection="review_images",
            owner_id=review_id,
        )
        new_path.parent.mkdir(parents=True, exist_ok=True)
        if old_path == new_path and old_path.is_file():
            old_contents = old_path.read_bytes()
        temporary_path = new_path.with_name(f".{new_path.name}.uploading")
        try:
            temporary_path.write_bytes(contents)
            temporary_path.replace(new_path)
        except OSError as error:
            temporary_path.unlink(missing_ok=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Could not store review image",
            ) from error

    if display_order is not None:
        image.display_order = display_order

    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        if new_path is not None:
            if old_path == new_path:
                if old_contents is None:
                    new_path.unlink(missing_ok=True)
                else:
                    new_path.write_bytes(old_contents)
            elif old_path != new_path:
                new_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="display_order is already used for this review",
        ) from error

    if old_path is not None and old_path != new_path:
        try:
            old_path.unlink(missing_ok=True)
        except OSError:
            pass
    session.refresh(image)
    return _review_image_read(image)


@router.delete(
    "/{review_id}/images/{image_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_review_image(
    review_id: Annotated[int, Path(gt=0)],
    image_id: Annotated[int, Path(gt=0)],
    session: DbSession,
    current_user: CurrentUser,
) -> Response:
    review = session.get(Review, review_id)
    if review is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Review not found",
        )
    if review.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You may delete images only from your own reviews",
        )

    image = session.scalar(
        select(ReviewImage).where(
            ReviewImage.id == image_id,
            ReviewImage.review_id == review_id,
        )
    )
    if image is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Review image not found",
        )
    try:
        image_path, _ = resolve_image_path(
            image.image_url,
            collection="review_images",
            owner_id=review_id,
        )
    except ValueError:
        image_path = None

    session.delete(image)
    session.commit()
    if image_path is not None:
        try:
            image_path.unlink(missing_ok=True)
            image_path.parent.rmdir()
        except OSError:
            pass
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{review_id}", response_model=ReviewDetailRead)
def get_review(
    review_id: Annotated[int, Path(gt=0)],
    session: DbSession,
) -> ReviewDetailRead:
    review = session.scalar(
        select(Review)
        .options(
            selectinload(Review.user),
            selectinload(Review.vendor).selectinload(Vendor.images),
            selectinload(Review.images),
        )
        .where(Review.id == review_id)
    )
    if review is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Review not found",
        )

    return _review_detail(review)


@router.patch("/{review_id}", response_model=ReviewRead)
def update_review(
    review_id: Annotated[int, Path(gt=0)],
    review_data: ReviewUpdate,
    session: DbSession,
    current_user: CurrentUser,
) -> ReviewRead:
    review = session.get(Review, review_id)
    if review is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Review not found",
        )

    if review.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You may edit only your own reviews",
        )

    if "rating" in review_data.model_fields_set:
        rating = review_data.rating
        if rating is None:  # Defensive guard; ReviewUpdate rejects this input.
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="rating cannot be null",
            )
        review.rating_half_steps = int(rating * 2)
    if "comment" in review_data.model_fields_set:
        review.comment = review_data.comment
    review.updated_at = datetime.now(timezone.utc)

    session.commit()
    session.refresh(review)
    return _review_read(review)


@router.delete("/{review_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_review(
    review_id: Annotated[int, Path(gt=0)],
    session: DbSession,
    current_user: CurrentUser,
) -> Response:
    review = session.scalar(
        select(Review)
        .options(selectinload(Review.images))
        .where(Review.id == review_id)
    )
    if review is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Review not found",
        )

    is_author = review.user_id == current_user.id
    is_admin = current_user.role == "admin"
    if not is_author and not is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You may delete only your own reviews",
        )

    image_paths = []
    for image in review.images:
        try:
            image_path, _ = resolve_image_path(
                image.image_url,
                collection="review_images",
                owner_id=review_id,
            )
        except ValueError:
            continue
        image_paths.append(image_path)

    session.delete(review)
    session.commit()

    for image_path in image_paths:
        try:
            image_path.unlink(missing_ok=True)
            image_path.parent.rmdir()
        except OSError:
            # The database deletion has succeeded; leave unrelated or locked
            # directory contents untouched.
            pass
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("", response_model=ReviewRead, status_code=status.HTTP_201_CREATED)
def create_review(
    review_data: ReviewCreate,
    session: DbSession,
    current_user: CurrentUser,
) -> ReviewRead:
    vendor = session.get(Vendor, review_data.vendor_id)
    if vendor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vendor not found",
        )

    review = Review(
        user_id=current_user.id,
        vendor_id=vendor.id,
        rating_half_steps=int(review_data.rating * 2),
        comment=review_data.comment,
    )
    session.add(review)
    session.commit()
    session.refresh(review)

    return _review_read(review)
