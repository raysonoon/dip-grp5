from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.routes.auth import RECENT_REVIEWS_LIMIT
from app.models import Review, User, Vendor


def create_user(session: Session, email: str) -> User:
    user = User(
        display_name="Account User",
        email_address=email,
        password_hash="test-hash",
        role="user",
    )
    session.add(user)
    session.flush()
    return user


def test_me_lists_recent_reviews_most_recent_first(
    client: TestClient,
    session: Session,
) -> None:
    user = create_user(session, "account@example.com")
    other_user = create_user(session, "other@example.com")
    older_vendor = Vendor(name="Older Stall")
    newer_vendor = Vendor(name="Newer Stall")
    session.add_all([older_vendor, newer_vendor])
    session.flush()

    now = datetime.now(timezone.utc)
    session.add_all(
        [
            Review(
                user_id=user.id,
                vendor_id=older_vendor.id,
                rating_half_steps=7,
                comment="Decent",
                created_at=now - timedelta(days=2),
            ),
            Review(
                user_id=user.id,
                vendor_id=newer_vendor.id,
                rating_half_steps=10,
                comment=None,
                created_at=now,
            ),
            Review(
                user_id=other_user.id,
                vendor_id=newer_vendor.id,
                rating_half_steps=2,
                comment="Not mine",
                created_at=now,
            ),
        ]
    )
    session.commit()

    response = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {user.id}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == user.id
    assert [
        (review["vendor"]["name"], review["rating"], review["comment"])
        for review in body["recent_reviews"]
    ] == [
        ("Newer Stall", 5.0, None),
        ("Older Stall", 3.5, "Decent"),
    ]
    assert body["recent_reviews"][0]["vendor"]["id"] == newer_vendor.id


def test_me_returns_empty_recent_reviews_without_reviews(
    client: TestClient,
    session: Session,
) -> None:
    user = create_user(session, "no-reviews@example.com")
    session.commit()

    response = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {user.id}"},
    )

    assert response.status_code == 200
    assert response.json()["recent_reviews"] == []


def test_me_limits_recent_reviews(
    client: TestClient,
    session: Session,
) -> None:
    user = create_user(session, "many-reviews@example.com")
    vendor = Vendor(name="Busy Stall")
    session.add(vendor)
    session.flush()

    now = datetime.now(timezone.utc)
    session.add_all(
        Review(
            user_id=user.id,
            vendor_id=vendor.id,
            rating_half_steps=8,
            comment=f"Visit {index}",
            created_at=now - timedelta(hours=index),
        )
        for index in range(RECENT_REVIEWS_LIMIT + 3)
    )
    session.commit()

    response = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {user.id}"},
    )

    reviews = response.json()["recent_reviews"]
    assert len(reviews) == RECENT_REVIEWS_LIMIT
    assert reviews[0]["comment"] == "Visit 0"


def test_me_requires_sign_in(client: TestClient) -> None:
    assert client.get("/auth/me").status_code == 401
