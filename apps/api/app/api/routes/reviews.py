from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.api.dependencies import CurrentUser, DbSession
from app.models import Review, Vendor
from app.schemas import (
    ReviewCreate,
    ReviewDetailRead,
    ReviewImageRead,
    ReviewListRead,
    ReviewRead,
    ReviewUserRead,
    ReviewVendorRead,
)


router = APIRouter(prefix="/reviews", tags=["reviews"])


def _review_detail(review: Review) -> ReviewDetailRead:
    return ReviewDetailRead(
        id=review.id,
        rating=review.rating_half_steps / 2,
        comment=review.comment,
        created_at=review.created_at,
        user=ReviewUserRead(
            id=review.user.id,
            username=review.user.username,
            affiliation=review.user.affiliation,
        ),
        vendor=ReviewVendorRead(
            id=review.vendor.id,
            name=review.vendor.name,
            location=review.vendor.location,
            image_url=review.vendor.image_url,
            category=review.vendor.category,
            opening_hours=review.vendor.opening_hours,
        ),
        images=[
            ReviewImageRead(
                id=image.id,
                image_url=image.image_url,
                mime_type=image.mime_type,
                file_size_bytes=image.file_size_bytes,
                display_order=image.display_order,
            )
            for image in review.images
        ],
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
            selectinload(Review.vendor),
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


@router.get("/{review_id}", response_model=ReviewDetailRead)
def get_review(
    review_id: Annotated[int, Path(gt=0)],
    session: DbSession,
) -> ReviewDetailRead:
    review = session.scalar(
        select(Review)
        .options(
            selectinload(Review.user),
            selectinload(Review.vendor),
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


@router.delete("/{review_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_review(
    review_id: Annotated[int, Path(gt=0)],
    session: DbSession,
    current_user: CurrentUser,
) -> Response:
    review = session.get(Review, review_id)
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

    session.delete(review)
    session.commit()
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

    return ReviewRead(
        id=review.id,
        user_id=review.user_id,
        vendor_id=review.vendor_id,
        rating=review.rating_half_steps / 2,
        comment=review.comment,
        created_at=review.created_at,
    )
