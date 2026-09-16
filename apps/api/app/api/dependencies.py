from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models import User
from app.services.chat import ChatService
from app.services.embedding import Embedder, GoogleEmbedder
from app.services.intent_router import IntentRouter
from app.services.llm_routing import (
    build_classifier,
    build_filter_extractor,
)
from app.services.retrieval import KnowledgeStore, PgvectorKnowledgeStore
from app.services.review_knowledge import InternalReviewKnowledgeSync
from app.services.sql_search import PgSqlStore
from app.services.structured_filters import StructuredFilter


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


def _get_genai_client() -> object | None:
    if settings.gemini_api_key is None:
        return None
    from google import genai

    return genai.Client(api_key=settings.gemini_api_key.get_secret_value())


def get_intent_router(
    session: DbSession,
    embedder: Annotated[Embedder, Depends(get_embedder)],
) -> IntentRouter:
    client = _get_genai_client()
    classify_llm = (
        build_classifier(client) if client is not None else None
    )
    return IntentRouter(
        session,
        embedder=embedder,
        classify_llm=classify_llm,
    )


def get_sql_store(session: DbSession) -> PgSqlStore:
    return PgSqlStore(session)


def get_filter_extractor_llm() -> Callable[[str], StructuredFilter] | None:
    client = _get_genai_client()
    if client is None:
        return None
    return build_filter_extractor(client)


def get_chat_service(
    session: DbSession,
    embedder: Annotated[Embedder, Depends(get_embedder)],
    store: Annotated[KnowledgeStore, Depends(get_knowledge_store)],
    router: Annotated[IntentRouter, Depends(get_intent_router)],
    sql_store: Annotated[PgSqlStore, Depends(get_sql_store)],
    filter_extractor_llm: Annotated[
        Callable[[str], StructuredFilter] | None,
        Depends(get_filter_extractor_llm),
    ],
) -> ChatService:
    return ChatService(
        embedder,
        store,
        router=router,
        sql_store=sql_store,
        filter_extractor_llm=filter_extractor_llm,
    )


EmbedderDep = Annotated[Embedder, Depends(get_embedder)]
KnowledgeStoreDep = Annotated[KnowledgeStore, Depends(get_knowledge_store)]
ChatServiceDep = Annotated[ChatService, Depends(get_chat_service)]


def get_review_knowledge_sync(
    session: DbSession,
    embedder: EmbedderDep,
) -> InternalReviewKnowledgeSync:
    return InternalReviewKnowledgeSync(session, embedder)


ReviewKnowledgeSyncDep = Annotated[
    InternalReviewKnowledgeSync,
    Depends(get_review_knowledge_sync),
]


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
