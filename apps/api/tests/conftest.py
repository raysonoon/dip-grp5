from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.api.dependencies import get_review_knowledge_sync
from app.db.base import Base
from app.db.session import get_db
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
    previous_dev_auth = settings.dev_auth_enabled
    settings.dev_auth_enabled = True

    def override_get_db() -> Iterator[Session]:
        yield session

    class NoopReviewKnowledgeSync:
        def sync(self, review) -> None:
            pass

        def delete(self, review_id: int) -> None:
            pass

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_review_knowledge_sync] = (
        lambda: NoopReviewKnowledgeSync()
    )
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
        settings.dev_auth_enabled = previous_dev_auth
