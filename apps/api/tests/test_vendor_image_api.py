from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core import image_storage
from app.models import User, Vendor

JPEG_BYTES = b"\xff\xd8\xff\xe0test-jpeg\xff\xd9"
PNG_BYTES = b"\x89PNG\r\n\x1a\ntest-png"


def _seed_users_and_vendor(session: Session) -> tuple[User, User, Vendor]:
    admin = User(
        display_name="Image Administrator",
        email_address="image-admin@example.com",
        password_hash="test-hash",
        role="admin",
    )
    normal_user = User(
        display_name="Normal User",
        email_address="normal-user@example.com",
        password_hash="test-hash",
        role="user",
    )
    vendor = Vendor(
        name="Image Test Stall",
        location="South Spine",
    )
    session.add_all([admin, normal_user, vendor])
    session.commit()
    session.refresh(admin)
    session.refresh(normal_user)
    session.refresh(vendor)
    return admin, normal_user, vendor


def test_vendor_image_api_is_public_read_and_admin_write(
    client: TestClient,
    session: Session,
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(image_storage, "UPLOADS_ROOT", tmp_path / "uploads")
    admin, normal_user, vendor = _seed_users_and_vendor(session)
    admin_headers = {"X-Dev-User-Id": str(admin.id)}

    empty_list = client.get(f"/vendors/{vendor.id}/images")
    assert empty_list.status_code == 200
    assert empty_list.json() == []

    forbidden = client.post(
        f"/vendors/{vendor.id}/images",
        headers={"X-Dev-User-Id": str(normal_user.id)},
        files={"file": ("meal.png", PNG_BYTES, "image/png")},
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["detail"] == "Administrator access required"

    first = client.post(
        f"/vendors/{vendor.id}/images",
        headers=admin_headers,
        files={"file": ("first.png", PNG_BYTES, "image/png")},
    )
    assert first.status_code == 201
    first_data = first.json()
    assert first_data["display_order"] == 1
    assert first_data["mime_type"] == "image/png"
    assert first_data["file_size_bytes"] == len(PNG_BYTES)
    assert first_data["image_url"] == (
        f"/media/vendor_images/{vendor.id}/{first_data['id']}.png"
    )
    stored_first = (
        tmp_path
        / "uploads"
        / "vendor_images"
        / str(vendor.id)
        / f"{first_data['id']}.png"
    )
    assert stored_first.read_bytes() == PNG_BYTES

    second = client.post(
        f"/vendors/{vendor.id}/images",
        headers=admin_headers,
        files={"file": ("second.jpg", JPEG_BYTES, "image/jpeg")},
    )
    assert second.status_code == 201
    assert second.json()["display_order"] == 2
    assert second.json()["mime_type"] == "image/jpeg"

    conflict = client.patch(
        f"/vendors/{vendor.id}/images/{second.json()['id']}",
        headers=admin_headers,
        json={"display_order": 1},
    )
    assert conflict.status_code == 409

    updated = client.patch(
        f"/vendors/{vendor.id}/images/{second.json()['id']}",
        headers=admin_headers,
        json={
            "image_url": f"/media/vendor_images/{vendor.id}/updated.jpg",
            "display_order": 3,
        },
    )
    assert updated.status_code == 200
    assert updated.json()["display_order"] == 3

    deleted = client.delete(
        f"/vendors/{vendor.id}/images/{first_data['id']}",
        headers=admin_headers,
    )
    assert deleted.status_code == 204

    image_list = client.get(f"/vendors/{vendor.id}/images")
    assert image_list.status_code == 200
    assert [image["display_order"] for image in image_list.json()] == [3]

    vendor_list = client.get("/vendors")
    assert vendor_list.status_code == 200
    assert vendor_list.json()["items"][0]["image_url"] == (
        f"/media/vendor_images/{vendor.id}/updated.jpg"
    )


def test_vendor_image_api_validates_vendor_and_file(
    client: TestClient,
    session: Session,
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(image_storage, "UPLOADS_ROOT", tmp_path / "uploads")
    admin, _, vendor = _seed_users_and_vendor(session)
    headers = {"X-Dev-User-Id": str(admin.id)}

    missing_vendor = client.post(
        "/vendors/9999/images",
        headers=headers,
        files={"file": ("meal.png", PNG_BYTES, "image/png")},
    )
    assert missing_vendor.status_code == 404

    empty = client.post(
        f"/vendors/{vendor.id}/images",
        headers=headers,
        files={"file": ("empty.png", b"", "image/png")},
    )
    assert empty.status_code == 422

    unsupported = client.post(
        f"/vendors/{vendor.id}/images",
        headers=headers,
        files={"file": ("fake.png", b"not-an-image", "image/png")},
    )
    assert unsupported.status_code == 415

    empty_update = client.patch(
        f"/vendors/{vendor.id}/images/9999",
        headers=headers,
        json={},
    )
    assert empty_update.status_code == 422


def test_vendor_image_reuses_freed_display_order_slot(
    client: TestClient,
    session: Session,
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(image_storage, "UPLOADS_ROOT", tmp_path / "uploads")
    admin, _, vendor = _seed_users_and_vendor(session)
    headers = {"X-Dev-User-Id": str(admin.id)}

    first = client.post(
        f"/vendors/{vendor.id}/images",
        headers=headers,
        files={"file": ("first.png", PNG_BYTES, "image/png")},
    ).json()
    assert first["display_order"] == 1

    second = client.post(
        f"/vendors/{vendor.id}/images",
        headers=headers,
        files={"file": ("second.png", PNG_BYTES, "image/png")},
    ).json()
    assert second["display_order"] == 2

    deleted = client.delete(
        f"/vendors/{vendor.id}/images/{first['id']}",
        headers=headers,
    )
    assert deleted.status_code == 204

    refill = client.post(
        f"/vendors/{vendor.id}/images",
        headers=headers,
        files={"file": ("third.png", PNG_BYTES, "image/png")},
    ).json()
    assert refill["display_order"] == 1