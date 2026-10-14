from collections.abc import Callable
from functools import lru_cache
import logging
from typing import Annotated

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import verify_supabase_access_token
from app.db.session import SessionLocal, get_db
from app.models import User
from app.schemas.chat import ChatHistoryMessage
from app.services.chat import ChatService
from app.services.embedding import Embedder, GoogleEmbedder
from app.services.intent_router import IntentRouter
from app.services.llm_routing import (
    build_classifier,
    build_filter_extractor,
    build_question_rewriter,
)
from app.services.retrieval import KnowledgeStore, PgvectorKnowledgeStore
from app.services.review_knowledge import InternalReviewKnowledgeSync
from app.services.sql_search import PgSqlStore
from app.services.structured_filters import StructuredFilter


DbSession = Annotated[Session, Depends(get_db)]
logger = logging.getLogger(__name__)
bearer_scheme = HTTPBearer(auto_error=False)


@lru_cache(maxsize=1)
def get_embedder() -> Embedder:
    api_key = (
        settings.gemini_api_key.get_secret_value()
        if settings.gemini_api_key is not None
        else None
    )
    # Interactive requests must fail fast enough for the web client's timeout.
    # Long retry/backoff remains available to offline reindex jobs, which build
    # their own GoogleEmbedder with the configured retry count.
    return GoogleEmbedder(api_key=api_key, max_retries=1)


def get_knowledge_store(session: DbSession) -> KnowledgeStore:
    return PgvectorKnowledgeStore(session)


@lru_cache(maxsize=1)
def _get_genai_client() -> object | None:
    if settings.gemini_api_key is None:
        return None
    from google import genai

    return genai.Client(api_key=settings.gemini_api_key.get_secret_value())


def warm_intent_embeddings() -> int:
    """Warm reusable intent embeddings while keeping startup failure-tolerant."""
    if settings.gemini_api_key is None:
        logger.info("Skipping intent embedding warm-up: GEMINI_API_KEY is not set")
        return 0
    try:
        with SessionLocal() as session:
            count = IntentRouter(
                session,
                embedder=get_embedder(),
            ).warm_prompt_embeddings()
    except Exception:
        logger.warning(
            "Intent embedding warm-up failed; requests will use normal fallback",
            exc_info=True,
        )
        return 0
    logger.info("Warmed embeddings for %d intent prompt(s)", count)
    return count


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


def get_question_rewriter() -> (
    Callable[[str, list[ChatHistoryMessage]], str] | None
):
    client = _get_genai_client()
    if client is None:
        return None
    return build_question_rewriter(client)


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
    rewrite_llm: Annotated[
        Callable[[str, list[ChatHistoryMessage]], str] | None,
        Depends(get_question_rewriter),
    ],
) -> ChatService:
    return ChatService(
        embedder,
        store,
        client=_get_genai_client(),
        router=router,
        sql_store=sql_store,
        filter_extractor_llm=filter_extractor_llm,
        rewrite_llm=rewrite_llm,
        session=session,
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
    credentials: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
) -> User:
    """Resolve a local user from a verified Supabase bearer token."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return _resolve_supabase_user(session, credentials.credentials)


def get_optional_current_user(
    session: DbSession,
    credentials: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
) -> User | None:
    """Resolve the user when a valid bearer token is present."""
    if credentials is None:
        return None
    return _resolve_supabase_user(session, credentials.credentials)


def _resolve_supabase_user(session: Session, token: str) -> User:
    claims = verify_supabase_access_token(token)
    subject = claims.get("sub")
    email = claims.get("email")
    if not isinstance(subject, str) or not isinstance(email, str) or not email.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Supabase token does not identify a user",
        )

    user = session.scalar(
        select(User).where(User.supabase_user_id == subject)
    )
    if user is not None:
        return user

    email_address = email.strip()
    user = session.scalar(
        select(User).where(User.email_canonical == email_address.lower())
    )
    metadata = claims.get("user_metadata")
    display_name = metadata.get("display_name") if isinstance(metadata, dict) else None
    if user is None:
        user = User(
            display_name=(display_name.strip() if isinstance(display_name, str) and display_name.strip() else email_address.split("@", 1)[0]),
            email_address=email_address,
            email_canonical=email_address.lower(),
            supabase_user_id=subject,
            password_hash="supabase-managed",
            role="user",
        )
        session.add(user)
    else:
        user.supabase_user_id = subject
    session.commit()
    session.refresh(user)
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


OptionalCurrentUser = Annotated[
    User | None,
    Depends(get_optional_current_user),
]


def get_current_admin(current_user: CurrentUser) -> User:
    """Require the authenticated development user to have the admin role."""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator access required",
        )
    return current_user


AdminUser = Annotated[User, Depends(get_current_admin)]
