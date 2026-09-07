from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import image_storage
from app.models import (
    Review,
    ReviewImage,
    User,
    Vendor,
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
        unit_code="N2.1-01-01",
        average_google_rating=4.6,
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
    assert "unit_code" in vendor_columns
    assert "level_unit" not in vendor_columns
    assert "average_google_rating" in vendor_columns
    assert len(vendor_columns) == 13
    google_columns = {
        column.name
        for column in vendor_columns
        if "google" in column.name
    }
    assert google_columns == {"average_google_rating"}
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
    assert item["unit_code"] == "N2.1-01-01"
    assert item["average_google_rating"] == 4.6
    assert {
        key for key in item if "google" in key
    } == {"average_google_rating"}
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


def test_review_delete_checks_ownership_and_removes_images(
    client: TestClient,
    session: Session,
    tmp_path: Path,
    monkeypatch,
) -> None:
    uploads_root = tmp_path / "uploads"
    monkeypatch.setattr(image_storage, "UPLOADS_ROOT", uploads_root)
    author, other_user, _, review = _seed_records(session)
    image = ReviewImage(
        review_id=review.id,
        image_url=f"/media/review_images/{review.id}/1.png",
        mime_type="image/png",
        file_size_bytes=8,
        display_order=1,
    )
    session.add(image)
    session.commit()
    session.refresh(image)
    image_id = image.id
    image_path = (
        uploads_root / "review_images" / str(review.id) / "1.png"
    )
    image_path.parent.mkdir(parents=True)
    image_path.write_bytes(b"test-png")

    forbidden = client.delete(
        f"/reviews/{review.id}",
        headers={"X-Dev-User-Id": str(other_user.id)},
    )
    assert forbidden.status_code == 403
    assert session.get(Review, review.id) is not None
    assert image_path.is_file()

    deleted = client.delete(
        f"/reviews/{review.id}",
        headers={"X-Dev-User-Id": str(author.id)},
    )
    assert deleted.status_code == 204
    session.expire_all()
    assert session.get(Review, review.id) is None
    assert session.get(ReviewImage, image_id) is None
    assert not image_path.exists()

    missing = client.delete(
        f"/reviews/{review.id}",
        headers={"X-Dev-User-Id": str(author.id)},
    )
    assert missing.status_code == 404
