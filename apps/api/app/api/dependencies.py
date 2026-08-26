from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models import User


DbSession = Annotated[Session, Depends(get_db)]


def get_current_user(
    session: DbSession,
    x_dev_user_id: Annotated[
        int | None,
        Header(alias="X-Dev-User-Id"),
    ] = None,
) -> User:
    """Resolve a seeded user from a request header during local development."""
    if not settings.dev_auth_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Development authentication is disabled",
        )

    if x_dev_user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-Dev-User-Id header",
            headers={"WWW-Authenticate": "X-Dev-User-Id"},
        )

    user = session.get(User, x_dev_user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unknown development user",
        )

    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
