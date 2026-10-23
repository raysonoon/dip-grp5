from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

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


def auth(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {user.id}"}


def test_me_returns_profile_only(
    client: TestClient,
    session: Session,
) -> None:
    user = create_user(session, "profile@example.com")
    vendor = Vendor(name="Profile Stall")
    session.add(vendor)
    session.flush()
    session.add(Review(user_id=user.id, vendor_id=vendor.id, rating_half_steps=8))
    session.commit()

    response = client.get("/auth/me", headers=auth(user))

    assert response.status_code == 200
    assert response.json() == {
        "id": user.id,
        "display_name": "Account User",
        "role": "user",
    }


def test_my_reviews_lists_own_reviews_most_recent_first(
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

    response = client.get("/auth/me/reviews", headers=auth(user))

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert body["limit"] == 10
    assert body["offset"] == 0
    assert [
        (review["vendor"]["name"], review["rating"], review["comment"])
        for review in body["items"]
    ] == [
        ("Newer Stall", 5.0, None),
        ("Older Stall", 3.5, "Decent"),
    ]
    assert body["items"][0]["vendor"]["id"] == newer_vendor.id


def test_my_reviews_paginates_with_limit_and_offset(
    client: TestClient,
    session: Session,
) -> None:
    user = create_user(session, "many-reviews@example.com")
    vendors = [Vendor(name=f"Stall {index}") for index in range(13)]
    session.add_all(vendors)
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
        for index, vendor in enumerate(vendors)
    )
    session.commit()

    first_page = client.get(
        "/auth/me/reviews",
        params={"limit": 5, "offset": 0},
        headers=auth(user),
    ).json()
    last_page = client.get(
        "/auth/me/reviews",
        params={"limit": 5, "offset": 10},
        headers=auth(user),
    ).json()

    assert first_page["total"] == 13
    assert [review["comment"] for review in first_page["items"]] == [
        f"Visit {index}" for index in range(5)
    ]
    assert last_page["total"] == 13
    assert last_page["offset"] == 10
    assert [review["comment"] for review in last_page["items"]] == [
        "Visit 10",
        "Visit 11",
        "Visit 12",
    ]


def test_my_reviews_filters_by_vendor_beyond_the_first_page(
    client: TestClient,
    session: Session,
) -> None:
    user = create_user(session, "vendor-filter@example.com")
    vendors = [Vendor(name=f"Filter Stall {index}") for index in range(15)]
    session.add_all(vendors)
    session.flush()

    now = datetime.now(timezone.utc)
    session.add_all(
        Review(
            user_id=user.id,
            vendor_id=vendor.id,
            rating_half_steps=8,
            comment=f"Review {index}",
            created_at=now - timedelta(hours=index),
        )
        for index, vendor in enumerate(vendors)
    )
    session.commit()
    # The oldest review is outside the default first page of 10.
    oldest_vendor = vendors[-1]

    response = client.get(
        "/auth/me/reviews",
        params={"vendor_id": oldest_vendor.id},
        headers=auth(user),
    )
    unreviewed = client.get(
        "/auth/me/reviews",
        params={"vendor_id": 999_999},
        headers=auth(user),
    )

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["comment"] == "Review 14"
    assert response.json()["items"][0]["vendor"]["id"] == oldest_vendor.id
    assert unreviewed.json()["total"] == 0


def test_my_reviews_is_empty_without_reviews(
    client: TestClient,
    session: Session,
) -> None:
    user = create_user(session, "no-reviews@example.com")
    session.commit()

    response = client.get("/auth/me/reviews", headers=auth(user))

    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0, "limit": 10, "offset": 0}


def test_my_reviews_rejects_invalid_pagination(
    client: TestClient,
    session: Session,
) -> None:
    user = create_user(session, "bad-page@example.com")
    session.commit()

    for params in ({"limit": 0}, {"limit": 101}, {"offset": -1}, {"vendor_id": 0}):
        response = client.get("/auth/me/reviews", params=params, headers=auth(user))
        assert response.status_code == 422


def test_me_endpoints_require_sign_in(client: TestClient) -> None:
    assert client.get("/auth/me").status_code == 401
    assert client.get("/auth/me/reviews").status_code == 401
