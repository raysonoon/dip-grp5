from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core import image_storage
from app.models import Review, ReviewImage, User, Vendor, VendorImage


JPEG_BYTES = b"\xff\xd8\xff\xe0test-jpeg\xff\xd9"
PNG_BYTES = b"\x89PNG\r\n\x1a\ntest-png"


def test_vendor_and_review_image_gets_resolve_database_paths(
    client: TestClient,
    session: Session,
    tmp_path: Path,
    monkeypatch,
) -> None:
    uploads_root = tmp_path / "uploads"
    monkeypatch.setattr(image_storage, "UPLOADS_ROOT", uploads_root)

    user = User(
        display_name="Image Owner",
        email_address="image-owner@example.com",
        password_hash="test-hash",
        role="user",
    )
    vendor = Vendor(name="Image File Stall")
    session.add_all([user, vendor])
    session.flush()

    review = Review(
        user_id=user.id,
        vendor_id=vendor.id,
        rating_half_steps=8,
        comment="Image test",
    )
    session.add(review)
    session.flush()

    vendor_image = VendorImage(
        vendor_id=vendor.id,
        image_url=f"/media/vendor_images/{vendor.id}/sample.jpg",
        display_order=1,
    )
    review_image = ReviewImage(
        review_id=review.id,
        image_url=f"/media/review_images/{review.id}/sample.png",
        mime_type="image/png",
        file_size_bytes=len(PNG_BYTES),
        display_order=1,
    )
    session.add_all([vendor_image, review_image])
    session.commit()

    vendor_file = uploads_root / "vendor_images" / str(vendor.id) / "sample.jpg"
    vendor_file.parent.mkdir(parents=True)
    vendor_file.write_bytes(JPEG_BYTES)
    review_file = uploads_root / "review_images" / str(review.id) / "sample.png"
    review_file.parent.mkdir(parents=True)
    review_file.write_bytes(PNG_BYTES)

    vendor_response = client.get(
        f"/vendors/{vendor.id}/images/{vendor_image.id}"
    )
    assert vendor_response.status_code == 200
    assert vendor_response.headers["content-type"] == "image/jpeg"
    assert vendor_response.content == JPEG_BYTES

    review_response = client.get(
        f"/reviews/{review.id}/images/{review_image.id}"
    )
    assert review_response.status_code == 200
    assert review_response.headers["content-type"] == "image/png"
    assert review_response.content == PNG_BYTES


def test_image_get_rejects_missing_or_wrong_owner_files(
    client: TestClient,
    session: Session,
) -> None:
    vendor = Vendor(name="Missing Image Stall")
    session.add(vendor)
    session.flush()
    image = VendorImage(
        vendor_id=vendor.id,
        image_url=f"/media/vendor_images/{vendor.id}/missing.jpg",
        display_order=1,
    )
    session.add(image)
    session.commit()

    missing_file = client.get(f"/vendors/{vendor.id}/images/{image.id}")
    assert missing_file.status_code == 404

    wrong_owner = client.get(f"/vendors/{vendor.id + 1}/images/{image.id}")
    assert wrong_owner.status_code == 404
