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
