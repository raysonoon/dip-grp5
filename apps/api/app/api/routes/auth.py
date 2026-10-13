from fastapi import APIRouter

from app.api.dependencies import CurrentUser


router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me")
def read_current_user(current_user: CurrentUser) -> dict[str, object]:
    return {
        "id": current_user.id,
        "display_name": current_user.display_name,
        "role": current_user.role,
    }