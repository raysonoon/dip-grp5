from fastapi import APIRouter

from app.api.dependencies import CurrentUser


router = APIRouter(prefix="/auth", tags=["auth"])

RECENT_REVIEWS_LIMIT = 10


@router.get("/me")
def read_current_user(current_user: CurrentUser) -> dict[str, object]:
    # Most recent first, read through the User.reviews relationship.
    recent_reviews = sorted(
        current_user.reviews,
        key=lambda review: (review.created_at, review.id),
        reverse=True,
    )[:RECENT_REVIEWS_LIMIT]

    return {
        "id": current_user.id,
        "display_name": current_user.display_name,
        "role": current_user.role,
        "recent_reviews": [
            {
                "id": review.id,
                "rating": review.rating_half_steps / 2,
                "comment": review.comment,
                "created_at": review.created_at.isoformat(),
                "vendor": {
                    "id": review.vendor.id,
                    "name": review.vendor.name,
                },
            }
            for review in recent_reviews
        ],
    }
