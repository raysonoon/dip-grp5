from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core import image_storage
from app.models import Review, ReviewImage, User, Vendor


JPEG_BYTES = b"\xff\xd8\xff\xe0test-jpeg\xff\xd9"
PNG_BYTES = b"\x89PNG\r\n\x1a\ntest-png"


def _seed_review(session: Session) -> tuple[User, User, Review]:
    author = User(
        display_name="Review Image Author",
        email_address="review-image-author@example.com",
        password_hash="test-hash",
        role="user",
    )
    other_user = User(
        display_name="Other Review User",
        email_address="other-review-user@example.com",
        password_hash="test-hash",
        role="user",
    )
    vendor = Vendor(name="Review Image Stall")
    session.add_all([author, other_user, vendor])
    session.flush()
    review = Review(
        user_id=author.id,
        vendor_id=vendor.id,
        rating_half_steps=8,
        comment="Upload test",
    )
    session.add(review)
    session.commit()
    session.refresh(review)
    return author, other_user, review


def test_review_author_can_upload_and_read_images(
    client: TestClient,
    session: Session,
    tmp_path: Path,
    monkeypatch,
) -> None:
    uploads_root = tmp_path / "uploads"
    monkeypatch.setattr(image_storage, "UPLOADS_ROOT", uploads_root)
    author, _, review = _seed_review(session)
    headers = {"X-Dev-User-Id": str(author.id)}

    jpeg_response = client.post(
        f"/reviews/{review.id}/images",
        headers=headers,
        files={"file": ("meal.jpeg", JPEG_BYTES, "image/jpeg")},
    )
    assert jpeg_response.status_code == 201
    jpeg = jpeg_response.json()
    assert jpeg["display_order"] == 1
    assert jpeg["mime_type"] == "image/jpeg"
    assert jpeg["file_size_bytes"] == len(JPEG_BYTES)
    assert jpeg["image_url"] == (
        f"/media/review_images/{review.id}/{jpeg['id']}.jpg"
    )

    png_response = client.post(
        f"/reviews/{review.id}/images",
        headers=headers,
        files={"file": ("meal.png", PNG_BYTES, "image/png")},
    )
    assert png_response.status_code == 201
    png = png_response.json()
    assert png["display_order"] == 2
    assert png["mime_type"] == "image/png"

    stored_jpeg = (
        uploads_root
        / "review_images"
        / str(review.id)
        / f"{jpeg['id']}.jpg"
    )
    assert stored_jpeg.read_bytes() == JPEG_BYTES

    file_response = client.get(
        f"/reviews/{review.id}/images/{png['id']}"
    )
    assert file_response.status_code == 200
    assert file_response.headers["content-type"] == "image/png"
    assert file_response.content == PNG_BYTES

    review_response = client.get(f"/reviews/{review.id}")
    assert review_response.status_code == 200
    assert [image["id"] for image in review_response.json()["images"]] == [
        jpeg["id"],
        png["id"],
    ]


def test_review_image_upload_requires_owner_and_existing_review(
    client: TestClient,
    session: Session,
) -> None:
    _, other_user, review = _seed_review(session)
    headers = {"X-Dev-User-Id": str(other_user.id)}

    forbidden = client.post(
        f"/reviews/{review.id}/images",
        headers=headers,
        files={"file": ("meal.png", PNG_BYTES, "image/png")},
    )
    assert forbidden.status_code == 403

    missing = client.post(
        "/reviews/9999/images",
        headers=headers,
        files={"file": ("meal.png", PNG_BYTES, "image/png")},
    )
    assert missing.status_code == 404


def test_review_image_upload_validates_file_and_limit(
    client: TestClient,
    session: Session,
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(image_storage, "UPLOADS_ROOT", tmp_path / "uploads")
    author, _, review = _seed_review(session)
    headers = {"X-Dev-User-Id": str(author.id)}

    empty = client.post(
        f"/reviews/{review.id}/images",
        headers=headers,
        files={"file": ("empty.png", b"", "image/png")},
    )
    assert empty.status_code == 422

    unsupported = client.post(
        f"/reviews/{review.id}/images",
        headers=headers,
        files={"file": ("fake.png", b"not-an-image", "image/png")},
    )
    assert unsupported.status_code == 415

    mismatched_type = client.post(
        f"/reviews/{review.id}/images",
        headers=headers,
        files={"file": ("fake.jpg", PNG_BYTES, "image/jpeg")},
    )
    assert mismatched_type.status_code == 415

    oversized = client.post(
        f"/reviews/{review.id}/images",
        headers=headers,
        files={
            "file": (
                "large.png",
                b"\x89PNG\r\n\x1a\n" + b"0" * (5 * 1024 * 1024),
                "image/png",
            )
        },
    )
    assert oversized.status_code == 413

    session.add_all(
        [
            ReviewImage(
                review_id=review.id,
                image_url=(
                    f"/media/review_images/{review.id}/existing-{order}.png"
                ),
                mime_type="image/png",
                file_size_bytes=len(PNG_BYTES),
                display_order=order,
            )
            for order in range(1, 6)
        ]
    )
    session.commit()

    full = client.post(
        f"/reviews/{review.id}/images",
        headers=headers,
        files={"file": ("meal.png", PNG_BYTES, "image/png")},
    )
    assert full.status_code == 409
    assert full.json()["detail"] == "A review may have at most 5 images"


def test_review_image_update_and_delete_manage_file_and_permissions(
    client: TestClient,
    session: Session,
    tmp_path: Path,
    monkeypatch,
) -> None:
    uploads_root = tmp_path / "uploads"
    monkeypatch.setattr(image_storage, "UPLOADS_ROOT", uploads_root)
    author, other_user, review = _seed_review(session)
    author_headers = {"X-Dev-User-Id": str(author.id)}
    other_headers = {"X-Dev-User-Id": str(other_user.id)}

    first_response = client.post(
        f"/reviews/{review.id}/images",
        headers=author_headers,
        files={"file": ("first.jpg", JPEG_BYTES, "image/jpeg")},
    )
    second_response = client.post(
        f"/reviews/{review.id}/images",
        headers=author_headers,
        files={"file": ("second.png", PNG_BYTES, "image/png")},
    )
    first = first_response.json()
    second = second_response.json()

    empty_update = client.patch(
        f"/reviews/{review.id}/images/{first['id']}",
        headers=author_headers,
    )
    assert empty_update.status_code == 422

    forbidden_update = client.patch(
        f"/reviews/{review.id}/images/{first['id']}",
        headers=other_headers,
        data={"display_order": "3"},
    )
    assert forbidden_update.status_code == 403

    updated = client.patch(
        f"/reviews/{review.id}/images/{first['id']}",
        headers=author_headers,
        data={"display_order": "3"},
        files={"file": ("replacement.png", PNG_BYTES, "image/png")},
    )
    assert updated.status_code == 200
    assert updated.json()["display_order"] == 3
    assert updated.json()["mime_type"] == "image/png"
    old_path = (
        uploads_root
        / "review_images"
        / str(review.id)
        / f"{first['id']}.jpg"
    )
    replacement_path = old_path.with_suffix(".png")
    assert not old_path.exists()
    assert replacement_path.read_bytes() == PNG_BYTES

    conflict = client.patch(
        f"/reviews/{review.id}/images/{second['id']}",
        headers=author_headers,
        data={"display_order": "3"},
    )
    assert conflict.status_code == 409

    forbidden_delete = client.delete(
        f"/reviews/{review.id}/images/{first['id']}",
        headers=other_headers,
    )
    assert forbidden_delete.status_code == 403
    assert replacement_path.is_file()

    deleted = client.delete(
        f"/reviews/{review.id}/images/{first['id']}",
        headers=author_headers,
    )
    assert deleted.status_code == 204
    session.expire_all()
    assert session.get(ReviewImage, first["id"]) is None
    assert not replacement_path.exists()

    missing = client.delete(
        f"/reviews/{review.id}/images/{first['id']}",
        headers=author_headers,
    )
    assert missing.status_code == 404
