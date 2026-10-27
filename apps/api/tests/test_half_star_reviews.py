import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Review, User, Vendor


def create_user(session: Session, email: str) -> User:
    user = User(
        display_name="Half Star Reviewer",
        email_address=email,
        password_hash="test-hash",
        role="user",
    )
    session.add(user)
    session.flush()
    return user


def auth(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {user.id}"}


def test_create_half_star_review_is_stored_as_one_half_step(
    client: TestClient,
    session: Session,
) -> None:
    user = create_user(session, "half-create@example.com")
    vendor = Vendor(name="Half Star Stall")
    session.add(vendor)
    session.commit()

    response = client.post(
        "/reviews",
        headers=auth(user),
        json={"vendor_id": vendor.id, "rating": 0.5, "comment": "Not great"},
    )

    assert response.status_code == 201
    assert response.json()["rating"] == 0.5
    review = session.get(Review, response.json()["id"])
    session.refresh(review)
    assert review.rating_half_steps == 1


def test_update_review_to_half_star(
    client: TestClient,
    session: Session,
) -> None:
    user = create_user(session, "half-update@example.com")
    vendor = Vendor(name="Update Stall")
    session.add(vendor)
    session.commit()
    created = client.post(
        "/reviews",
        headers=auth(user),
        json={"vendor_id": vendor.id, "rating": 3},
    )

    response = client.patch(
        f"/reviews/{created.json()['id']}",
        headers=auth(user),
        json={"rating": 0.5},
    )

    assert response.status_code == 200
    assert response.json()["rating"] == 0.5
    review = session.get(Review, created.json()["id"])
    session.refresh(review)
    assert review.rating_half_steps == 1


@pytest.mark.parametrize("rating", [0, 0.25, 0.3, 0.7, 1.2, 5.5, -0.5])
def test_create_rejects_out_of_range_or_non_half_step_ratings(
    client: TestClient,
    session: Session,
    rating: float,
) -> None:
    user = create_user(session, f"bad-{rating}@example.com")
    vendor = Vendor(name=f"Bad Rating Stall {rating}")
    session.add(vendor)
    session.commit()

    response = client.post(
        "/reviews",
        headers=auth(user),
        json={"vendor_id": vendor.id, "rating": rating},
    )

    assert response.status_code == 422


@pytest.mark.parametrize("rating", [0, 0.3, 0.7])
def test_update_rejects_out_of_range_or_non_half_step_ratings(
    client: TestClient,
    session: Session,
    rating: float,
) -> None:
    user = create_user(session, f"bad-update-{rating}@example.com")
    vendor = Vendor(name=f"Bad Update Stall {rating}")
    session.add(vendor)
    session.commit()
    created = client.post(
        "/reviews",
        headers=auth(user),
        json={"vendor_id": vendor.id, "rating": 3},
    )

    response = client.patch(
        f"/reviews/{created.json()['id']}",
        headers=auth(user),
        json={"rating": rating},
    )

    assert response.status_code == 422


def test_vendor_average_includes_half_star_reviews(
    client: TestClient,
    session: Session,
) -> None:
    vendor = Vendor(name="Average Stall")
    session.add(vendor)
    session.commit()
    users = [create_user(session, f"avg-{index}@example.com") for index in range(2)]
    session.commit()

    client.post("/reviews", headers=auth(users[0]), json={"vendor_id": vendor.id, "rating": 0.5})
    # The test client shares this session; reload the trigger-updated vendor.
    session.expire_all()
    only_half_star = client.get(f"/vendors/{vendor.id}/average-rating").json()
    client.post("/reviews", headers=auth(users[1]), json={"vendor_id": vendor.id, "rating": 1.5})
    session.expire_all()
    with_second_review = client.get(f"/vendors/{vendor.id}/average-rating").json()

    assert only_half_star["average_rating"] == 0.5
    assert with_second_review["average_rating"] == 1.0


def test_check_constraint_allows_one_half_step_but_not_zero(session: Session) -> None:
    user = create_user(session, "constraint-half@example.com")
    vendor = Vendor(name="Constraint Half Stall")
    session.add(vendor)
    session.flush()

    session.add(Review(user_id=user.id, vendor_id=vendor.id, rating_half_steps=1))
    session.flush()

    other_user = create_user(session, "constraint-zero@example.com")
    session.add(Review(user_id=other_user.id, vendor_id=vendor.id, rating_half_steps=0))
    with pytest.raises(IntegrityError):
        session.flush()
