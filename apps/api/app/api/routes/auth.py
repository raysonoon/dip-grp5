from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload, with_parent

from app.api.dependencies import CurrentUser, DbSession
from app.models import Review, User
from app.schemas.review import MyReviewListRead, MyReviewRead, MyReviewVendorRead


router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me")
def read_current_user(current_user: CurrentUser) -> dict[str, object]:
    return {
        "id": current_user.id,
        "display_name": current_user.display_name,
        "role": current_user.role,
    }


@router.get("/me/reviews", response_model=MyReviewListRead)
def list_my_reviews(
    current_user: CurrentUser,
    session: DbSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> MyReviewListRead:
    # Page through the User.reviews relationship, most recent first.
    my_reviews = with_parent(current_user, User.reviews)

    total = session.scalar(select(func.count(Review.id)).where(my_reviews))
    reviews = session.scalars(
        select(Review)
        .options(selectinload(Review.vendor))
        .where(my_reviews)
        .order_by(Review.created_at.desc(), Review.id.desc())
        .offset(offset)
        .limit(limit)
    ).all()

    return MyReviewListRead(
        items=[
            MyReviewRead(
                id=review.id,
                rating=review.rating_half_steps / 2,
                comment=review.comment,
                created_at=review.created_at,
                vendor=MyReviewVendorRead(
                    id=review.vendor.id,
                    name=review.vendor.name,
                ),
            )
            for review in reviews
        ],
        total=total or 0,
        limit=limit,
        offset=offset,
    )
