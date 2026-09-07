import pytest
from fastapi.testclient import TestClient
from sqlalchemy import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    Review,
    User,
    Vendor,
    VendorGoogleProfile,
    VendorImage,
)


def _seed_records(session: Session) -> tuple[User, User, Vendor, Review]:
    author = User(
        display_name="Review Author",
        email_address="author@example.com",
        password_hash="test-hash",
        role="user",
    )
    other_user = User(
        display_name="Other User",
        email_address="other@example.com",
        password_hash="test-hash",
        role="user",
    )
    vendor = Vendor(
        name="Test Stall",
        location="North Spine",
        category="Asian",
        opening_hours="09:00 - 18:00",
        price_range="$1-10",
        halal=True,
        vegetarian=False,
        level_unit="N2.1-01-01",
        google_profile=VendorGoogleProfile(
            place_id="google-place-1",
            display_name="Test Stall on Google",
            price_range="$10-20",
            rating=4.6,
            review_count=123,
            address="1 Test Street, Singapore",
            categories=["Restaurant", "Cafe"],
            website_url="https://example.com",
            phone_number="6123 4567",
            hours=[{"day": "Monday", "times": ["9 am-6 pm"]}],
            status="Open",
            maps_url="https://maps.example.com/test-stall",
            search_query="test stall ntu",
        ),
        images=[
            VendorImage(
                image_url="/media/vendor_images/1/second.jpg",
                display_order=2,
            ),
            VendorImage(
                image_url="/media/vendor_images/1/thumbnail.jpg",
                display_order=1,
            ),
        ],
    )
    session.add_all([author, other_user, vendor])
    session.flush()

    review = Review(
        user_id=author.id,
        vendor_id=vendor.id,
        rating_half_steps=8,
        comment="Original review",
    )
    session.add(review)
    session.commit()
    session.refresh(author)
    session.refresh(other_user)
    session.refresh(vendor)
    session.refresh(review)
    return author, other_user, vendor, review


def test_user_and_vendor_storage_follow_the_new_schema(session: Session) -> None:
    user_columns = User.__table__.columns
    vendor_columns = Vendor.__table__.columns
    google_profile_columns = VendorGoogleProfile.__table__.columns

    assert "username" not in user_columns
    assert "display_name" in user_columns
    assert "email_address" in user_columns
    assert "email_canonical" in user_columns
    assert user_columns.email_address.unique is not True
    email_indexes = {index.name: index for index in User.__table__.indexes}
    assert email_indexes["uq_users_email_canonical"].unique is True

    assert "image_url" not in vendor_columns
    assert "updated_at" in vendor_columns
    assert "price_range" in vendor_columns
    assert "halal" in vendor_columns
    assert "vegetarian" in vendor_columns
    assert len(vendor_columns) == 12
    assert "google_place_id" not in vendor_columns
    assert "google_price_range" not in vendor_columns
    assert "google_review_count" not in vendor_columns
    assert "google_categories" not in vendor_columns
    assert "google_hours" not in vendor_columns
    assert "place_id" in google_profile_columns
    assert "rating" in google_profile_columns
    assert "review_count" in google_profile_columns
    assert "categories" in google_profile_columns
    assert "hours" in google_profile_columns
    assert "is_temporarily_closed" not in google_profile_columns
    assert "is_permanently_closed" not in google_profile_columns
    assert VendorImage.__tablename__ == "vendor_images"


def test_display_names_can_repeat_and_email_is_normalized(session: Session) -> None:
    first = User(
        display_name="Same Name",
        email_address=" First@Example.COM ",
        password_hash="test-hash",
        role="user",
    )
    second = User(
        display_name="Same Name",
        email_address="second@example.com",
        password_hash="test-hash",
        role="user",
    )
    session.add_all([first, second])
    session.commit()

    assert first.display_name == second.display_name
    assert first.email_address == "First@Example.COM"
    assert first.email_canonical == "first@example.com"


def test_email_unique_index_is_case_insensitive(session: Session) -> None:
    session.execute(
        insert(User.__table__).values(
            display_name="First User",
            email_address="CaseSensitive@Example.com",
            email_canonical="casesensitive@example.com",
            password_hash="test-hash",
            role="user",
        )
    )
    session.commit()

    with pytest.raises(IntegrityError):
        session.execute(
            insert(User.__table__).values(
                display_name="Second User",
                email_address="casesensitive@example.com",
                email_canonical="casesensitive@example.com",
                password_hash="test-hash",
                role="user",
            )
        )
        session.commit()
    session.rollback()


def test_vendor_api_returns_ordered_images_and_compatibility_thumbnail(
    client: TestClient,
    session: Session,
) -> None:
    _, _, vendor, _ = _seed_records(session)

    response = client.get("/vendors")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    item = body["items"][0]
    assert item["id"] == vendor.id
    assert item["image_url"] == "/media/vendor_images/1/thumbnail.jpg"
    assert [image["display_order"] for image in item["images"]] == [1, 2]
    assert item["price_range"] == "$1-10"
    assert item["halal"] is True
    assert item["vegetarian"] is False
    assert item["level_unit"] == "N2.1-01-01"
    assert item["google_place_id"] == "google-place-1"
    assert item["google_name"] == "Test Stall on Google"
    assert item["google_price_range"] == "$10-20"
    assert item["average_google_rating"] == 4.6
    assert item["google_review_count"] == 123
    assert item["google_categories"] == ["Restaurant", "Cafe"]
    assert item["google_hours"][0]["day"] == "Monday"
    assert item["is_temporarily_closed"] is False
    assert item["is_permanently_closed"] is False
    assert item["updated_at"] is not None


def test_review_api_uses_display_name_and_reports_edit_state(
    client: TestClient,
    session: Session,
) -> None:
    author, _, _, review = _seed_records(session)

    before_edit = client.get(f"/reviews/{review.id}")
    assert before_edit.status_code == 200
    before_body = before_edit.json()
    assert before_body["user"]["display_name"] == "Review Author"
    assert "username" not in before_body["user"]
    assert before_body["is_edited"] is False
    assert before_body["updated_at"] is None

    edit_response = client.patch(
        f"/reviews/{review.id}",
        headers={"X-Dev-User-Id": str(author.id)},
        json={"rating": 4.5, "comment": "  Updated review  "},
    )

    assert edit_response.status_code == 200
    edited_body = edit_response.json()
    assert edited_body["rating"] == 4.5
    assert edited_body["comment"] == "Updated review"
    assert edited_body["is_edited"] is True
    assert edited_body["updated_at"] is not None

    after_edit = client.get(f"/reviews/{review.id}")
    assert after_edit.status_code == 200
    assert after_edit.json()["is_edited"] is True


def test_only_review_author_can_edit(
    client: TestClient,
    session: Session,
) -> None:
    _, other_user, _, review = _seed_records(session)

    response = client.patch(
        f"/reviews/{review.id}",
        headers={"X-Dev-User-Id": str(other_user.id)},
        json={"comment": "Not allowed"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "You may edit only your own reviews"


def test_review_edit_requires_at_least_one_valid_field(
    client: TestClient,
    session: Session,
) -> None:
    author, _, _, review = _seed_records(session)
    headers = {"X-Dev-User-Id": str(author.id)}

    empty_edit = client.patch(f"/reviews/{review.id}", headers=headers, json={})
    assert empty_edit.status_code == 422
    assert (
        client.patch(
            f"/reviews/{review.id}",
            headers=headers,
            json={"rating": None},
        ).status_code
        == 422
    )
