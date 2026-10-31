import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Review, User, Vendor


def create_user(session: Session, email: str) -> User:
    user = User(
        display_name="Reviewer",
        email_address=email,
        password_hash="test-hash",
        role="user",
    )
    session.add(user)
    session.flush()
    return user


def review_count(session: Session, user: User, vendor: Vendor) -> int:
    return session.scalar(
        select(func.count(Review.id)).where(
            Review.user_id == user.id,
            Review.vendor_id == vendor.id,
        )
    )


def test_second_review_for_same_vendor_returns_409(
    client: TestClient,
    session: Session,
) -> None:
    user = create_user(session, "repeat@example.com")
    vendor = Vendor(name="Repeat Stall")
    session.add(vendor)
    session.commit()
    headers = {"Authorization": f"Bearer {user.id}"}

    first = client.post(
        "/reviews",
        headers=headers,
        json={"vendor_id": vendor.id, "rating": 4, "comment": "First"},
    )
    second = client.post(
        "/reviews",
        headers=headers,
        json={"vendor_id": vendor.id, "rating": 2, "comment": "Second"},
    )

    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json()["detail"] == "You have already reviewed this vendor"
    assert review_count(session, user, vendor) == 1
    assert session.get(Review, first.json()["id"]).comment == "First"


def test_user_can_review_other_vendors_and_others_can_review_same_vendor(
    client: TestClient,
    session: Session,
) -> None:
    user = create_user(session, "first@example.com")
    other_user = create_user(session, "second@example.com")
    vendor = Vendor(name="Shared Stall")
    other_vendor = Vendor(name="Other Stall")
    session.add_all([vendor, other_vendor])
    session.commit()

    responses = [
        client.post(
            "/reviews",
            headers={"Authorization": f"Bearer {author.id}"},
            json={"vendor_id": target.id, "rating": 4},
        )
        for author, target in (
            (user, vendor),
            (user, other_vendor),
            (other_user, vendor),
        )
    ]

    assert [response.status_code for response in responses] == [201, 201, 201]


def test_user_can_review_again_after_deleting(
    client: TestClient,
    session: Session,
) -> None:
    user = create_user(session, "again@example.com")
    vendor = Vendor(name="Second Chance Stall")
    session.add(vendor)
    session.commit()
    headers = {"Authorization": f"Bearer {user.id}"}

    created = client.post(
        "/reviews",
        headers=headers,
        json={"vendor_id": vendor.id, "rating": 3},
    )
    deleted = client.delete(f"/reviews/{created.json()['id']}", headers=headers)
    recreated = client.post(
        "/reviews",
        headers=headers,
        json={"vendor_id": vendor.id, "rating": 5},
    )

    assert deleted.status_code == 204
    assert recreated.status_code == 201


def test_unique_constraint_rejects_duplicate_rows(session: Session) -> None:
    user = create_user(session, "constraint@example.com")
    vendor = Vendor(name="Constraint Stall")
    session.add(vendor)
    session.flush()

    session.add(Review(user_id=user.id, vendor_id=vendor.id, rating_half_steps=8))
    session.flush()
    session.add(Review(user_id=user.id, vendor_id=vendor.id, rating_half_steps=6))

    with pytest.raises(IntegrityError):
        session.flush()


def test_duplicate_caught_by_database_constraint_returns_409(
    client: TestClient,
    session: Session,
    monkeypatch,
) -> None:
    user = create_user(session, "race@example.com")
    vendor = Vendor(name="Race Stall")
    session.add(vendor)
    session.flush()
    session.add(Review(user_id=user.id, vendor_id=vendor.id, rating_half_steps=8))
    session.commit()
    # Simulate a concurrent request: the pre-check misses the existing review,
    # so the UNIQUE constraint is what rejects the insert.
    monkeypatch.setattr(session, "scalar", lambda *args, **kwargs: None)

    response = client.post(
        "/reviews",
        headers={"Authorization": f"Bearer {user.id}"},
        json={"vendor_id": vendor.id, "rating": 4},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "You have already reviewed this vendor"


def test_other_integrity_errors_are_not_reported_as_duplicates(
    client: TestClient,
    session: Session,
    monkeypatch,
) -> None:
    user = create_user(session, "check-fail@example.com")
    vendor = Vendor(name="Check Fail Stall")
    session.add(vendor)
    session.commit()

    def failing_flush(*args, **kwargs):
        raise IntegrityError(
            "INSERT INTO reviews",
            {},
            Exception(
                'new row for relation "reviews" violates check constraint '
                '"ck_reviews_rating_half_steps_range"'
            ),
        )

    monkeypatch.setattr(session, "flush", failing_flush)

    with pytest.raises(IntegrityError):
        client.post(
            "/reviews",
            headers={"Authorization": f"Bearer {user.id}"},
            json={"vendor_id": vendor.id, "rating": 4},
        )


def test_demo_review_seed_respects_one_review_per_vendor(session: Session) -> None:
    from app.core.config import settings
    from app.db.seed import seed_demo_reviews

    test_user = create_user(session, settings.seed_test_email_address)
    vendor_1 = Vendor(name="Demo Vendor 1")
    vendor_2 = Vendor(name="Demo Vendor 2")
    session.add_all([vendor_1, vendor_2])
    session.flush()
    # An older database may still hold a demo review with a different comment.
    session.add(
        Review(
            user_id=test_user.id,
            vendor_id=vendor_1.id,
            rating_half_steps=8,
            comment="Great chicken rice, generous portion and fast service.",
        )
    )
    session.commit()

    first_run = seed_demo_reviews(session)
    second_run = seed_demo_reviews(session)

    assert first_run == (1, 1)
    assert second_run == (0, 2)
    assert review_count(session, test_user, vendor_1) == 1
    assert review_count(session, test_user, vendor_2) == 1
