from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.api.dependencies import CurrentUser, DbSession
from app.models.user_food_preferences import UserFoodPreferences
from app.schemas.user_food_preferences import (
    UserFoodPreferencesResponse,
    UserFoodPreferencesUpdate,
)

router = APIRouter(prefix="/preferences", tags=["preferences"])


@router.get("/me", response_model=UserFoodPreferencesResponse | None)
def read_my_preferences(
    current_user: CurrentUser,
    session: DbSession,
):
    preferences = session.scalar(
        select(UserFoodPreferences).where(
            UserFoodPreferences.user_id == current_user.id
        )
    )

    if preferences is None:
        return None

    return preferences


@router.put("/me", response_model=UserFoodPreferencesResponse)
def update_my_preferences(
    payload: UserFoodPreferencesUpdate,
    current_user: CurrentUser,
    session: DbSession,
):
    if payload.onboarding_status not in {"completed", "skipped"}:
        raise HTTPException(
            status_code=422,
            detail="Invalid onboarding_status",
        )

    preferences = session.scalar(
        select(UserFoodPreferences).where(
            UserFoodPreferences.user_id == current_user.id
        )
    )

    if preferences is None:
        preferences = UserFoodPreferences(
            user_id=current_user.id,
            dietary_restrictions=payload.dietary_restrictions,
            cuisines=payload.cuisines,
            locations=payload.locations,
            likes=payload.likes,
            dislikes=payload.dislikes,
            lifestyle=payload.lifestyle,
            onboarding_status=payload.onboarding_status,
        )
        session.add(preferences)
    else:
        preferences.dietary_restrictions = payload.dietary_restrictions
        preferences.cuisines = payload.cuisines
        preferences.locations = payload.locations
        preferences.likes = payload.likes
        preferences.dislikes = payload.dislikes
        preferences.lifestyle = payload.lifestyle
        preferences.onboarding_status = payload.onboarding_status

    session.commit()
    session.refresh(preferences)

    return preferences