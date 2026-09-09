from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models import User
from app.services.chat import ChatService
from app.services.embedding import Embedder, GoogleEmbedder
from app.services.retrieval import KnowledgeStore, PgvectorKnowledgeStore


DbSession = Annotated[Session, Depends(get_db)]


def get_embedder() -> Embedder:
    api_key = (
        settings.gemini_api_key.get_secret_value()
        if settings.gemini_api_key is not None
        else None
    )
    return GoogleEmbedder(api_key=api_key)


def get_knowledge_store(session: DbSession) -> KnowledgeStore:
    return PgvectorKnowledgeStore(session)


def get_chat_service(
    embedder: Annotated[Embedder, Depends(get_embedder)],
    store: Annotated[KnowledgeStore, Depends(get_knowledge_store)],
) -> ChatService:
    return ChatService(embedder, store)


EmbedderDep = Annotated[Embedder, Depends(get_embedder)]
KnowledgeStoreDep = Annotated[KnowledgeStore, Depends(get_knowledge_store)]
ChatServiceDep = Annotated[ChatService, Depends(get_chat_service)]


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


def get_current_admin(current_user: CurrentUser) -> User:
    """Require the authenticated development user to have the admin role."""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator access required",
        )
    return current_user


AdminUser = Annotated[User, Depends(get_current_admin)]
