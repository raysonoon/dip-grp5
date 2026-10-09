from collections.abc import Iterator
from unittest.mock import patch

import pytest
from fastapi import HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.dependencies import (
    bearer_scheme,
    get_current_user,
    get_optional_current_user,
    get_review_knowledge_sync,
)
from app.db.base import Base
from app.db.session import get_db
from app.models import User
from app.main import app


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    testing_session = sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )
    with testing_session() as database_session:
        yield database_session
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def client(session: Session) -> Iterator[TestClient]:
    def override_get_db() -> Iterator[Session]:
        yield session

    def override_current_user(
        credentials: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
    ) -> User:
        if credentials is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing Bearer token",
            )
        try:
            user_id = int(credentials.credentials)
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid test bearer token",
            ) from error
        user = session.get(User, user_id)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Unknown test user",
            )
        return user

    def override_optional_current_user(
        credentials: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
    ) -> User | None:
        if credentials is None:
            return None
        return override_current_user(credentials)

    class NoopReviewKnowledgeSync:
        def sync(self, review) -> None:
            pass

        def delete(self, review_id: int) -> None:
            pass

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_current_user
    app.dependency_overrides[get_optional_current_user] = override_optional_current_user
    app.dependency_overrides[get_review_knowledge_sync] = (
        lambda: NoopReviewKnowledgeSync()
    )
    try:
        with patch("app.main.warm_intent_embeddings", return_value=0):
            with TestClient(app) as test_client:
                yield test_client
    finally:
        app.dependency_overrides.clear()
