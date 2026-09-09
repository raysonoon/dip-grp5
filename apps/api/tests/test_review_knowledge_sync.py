from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_review_knowledge_sync
from app.main import app
from app.models import Review, User, Vendor
from app.services.review_knowledge import (
    InternalReviewKnowledgeSync,
    KnowledgeSyncError,
)


class FakeSession:
    def __init__(self, existing=None) -> None:
        self.existing = existing
        self.added = []
        self.deleted = []

    def scalar(self, _statement):
        return self.existing

    def add(self, value) -> None:
        self.added.append(value)

    def delete(self, value) -> None:
        self.deleted.append(value)


class FakeEmbedder:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls = []

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(texts)
        if self.fail:
            raise RuntimeError("embedding unavailable")
        return [[0.25] * 768 for _ in texts]


def _review(*, comment: str | None = "Good noodles", rating_half_steps: int = 8) -> Review:
    return Review(
        id=7,
        user_id=2,
        vendor_id=3,
        rating_half_steps=rating_half_steps,
        comment=comment,
    )


def test_sync_creates_and_updates_internal_review_chunk() -> None:
    session = FakeSession()
    embedder = FakeEmbedder()
    sync = InternalReviewKnowledgeSync(session, embedder)

    sync.sync(_review())

    chunk = session.added[0]
    assert chunk.source_type == "internal_review"
    assert chunk.source_id == "7"
    assert chunk.vendor_id == 3
    assert chunk.content == "Good noodles"
    assert chunk.metadata_json == {"rating": 4.0}
    assert embedder.calls == [["Good noodles"]]

    existing = SimpleNamespace(
        vendor_id=3,
        content="Good noodles",
        metadata_json={"rating": 4.0},
        embedding=[0.25] * 768,
    )
    session.existing = existing
    sync.sync(_review(rating_half_steps=10))

    assert existing.metadata_json == {"rating": 5.0}
    assert embedder.calls == [["Good noodles"]]


def test_sync_reembeds_changed_text_and_deletes_blank_or_removed_review() -> None:
    existing = SimpleNamespace(
        vendor_id=3,
        content="Old text",
        metadata_json={"rating": 4.0},
        embedding=[0.1] * 768,
    )
    session = FakeSession(existing)
    embedder = FakeEmbedder()
    sync = InternalReviewKnowledgeSync(session, embedder)

    sync.sync(_review(comment="New text"))
    assert existing.content == "New text"
    assert existing.embedding == [0.25] * 768
    assert embedder.calls == [["New text"]]

    sync.sync(_review(comment="   "))
    assert session.deleted == [existing]

    session.deleted.clear()
    sync.delete(7)
    assert session.deleted == [existing]


def test_sync_wraps_embedding_failure() -> None:
    sync = InternalReviewKnowledgeSync(FakeSession(), FakeEmbedder(fail=True))

    with pytest.raises(KnowledgeSyncError):
        sync.sync(_review())


class RecordingSync:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.events = []

    def sync(self, review: Review) -> None:
        if self.fail:
            raise KnowledgeSyncError("unavailable")
        self.events.append(("sync", review.id, review.comment, review.rating_half_steps))

    def delete(self, review_id: int) -> None:
        self.events.append(("delete", review_id))


def _seed_user_and_vendor(session: Session) -> tuple[User, Vendor]:
    user = User(
        display_name="Reviewer",
        email_address="reviewer-sync@example.com",
        password_hash="x",
        role="user",
    )
    vendor = Vendor(name="Knowledge Sync Vendor")
    session.add_all([user, vendor])
    session.commit()
    session.refresh(user)
    session.refresh(vendor)
    return user, vendor


def test_review_endpoints_sync_create_update_and_delete(
    client: TestClient,
    session: Session,
) -> None:
    user, vendor = _seed_user_and_vendor(session)
    recorder = RecordingSync()
    app.dependency_overrides[get_review_knowledge_sync] = lambda: recorder
    headers = {"X-Dev-User-Id": str(user.id)}

    created = client.post(
        "/reviews",
        headers=headers,
        json={"vendor_id": vendor.id, "rating": 4, "comment": "Fresh review"},
    )
    assert created.status_code == 201
    review_id = created.json()["id"]

    updated = client.patch(
        f"/reviews/{review_id}",
        headers=headers,
        json={"rating": 5, "comment": "Updated review"},
    )
    assert updated.status_code == 200

    deleted = client.delete(f"/reviews/{review_id}", headers=headers)
    assert deleted.status_code == 204
    assert recorder.events == [
        ("sync", review_id, "Fresh review", 8),
        ("sync", review_id, "Updated review", 10),
        ("delete", review_id),
    ]


def test_create_rolls_back_when_embedding_sync_fails(
    client: TestClient,
    session: Session,
) -> None:
    user, vendor = _seed_user_and_vendor(session)
    app.dependency_overrides[get_review_knowledge_sync] = (
        lambda: RecordingSync(fail=True)
    )

    response = client.post(
        "/reviews",
        headers={"X-Dev-User-Id": str(user.id)},
        json={"vendor_id": vendor.id, "rating": 4, "comment": "Do not persist"},
    )

    assert response.status_code == 503
    assert session.scalar(select(Review).where(Review.vendor_id == vendor.id)) is None
