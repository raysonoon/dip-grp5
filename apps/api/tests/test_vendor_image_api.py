from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import User, Vendor


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
) -> None:
    admin, normal_user, vendor = _seed_users_and_vendor(session)
    admin_headers = {"X-Dev-User-Id": str(admin.id)}

    empty_list = client.get(f"/vendors/{vendor.id}/images")
    assert empty_list.status_code == 200
    assert empty_list.json() == []

    forbidden = client.post(
        f"/vendors/{vendor.id}/images",
        headers={"X-Dev-User-Id": str(normal_user.id)},
        json={"image_url": "https://example.com/not-allowed.jpg"},
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["detail"] == "Administrator access required"

    first = client.post(
        f"/vendors/{vendor.id}/images",
        headers=admin_headers,
        json={
            "image_url": f" /media/vendor_images/{vendor.id}/first.jpg "
        },
    )
    assert first.status_code == 201
    assert first.json()["display_order"] == 1
    assert first.json()["image_url"] == (
        f"/media/vendor_images/{vendor.id}/first.jpg"
    )

    second = client.post(
        f"/vendors/{vendor.id}/images",
        headers=admin_headers,
        json={
            "image_url": f"/media/vendor_images/{vendor.id}/second.jpg"
        },
    )
    assert second.status_code == 201
    assert second.json()["display_order"] == 2

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
        f"/vendors/{vendor.id}/images/{first.json()['id']}",
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


def test_vendor_image_api_validates_vendor_and_request_body(
    client: TestClient,
    session: Session,
) -> None:
    admin, _, vendor = _seed_users_and_vendor(session)
    headers = {"X-Dev-User-Id": str(admin.id)}

    missing_vendor = client.post(
        "/vendors/9999/images",
        headers=headers,
        json={"image_url": "/media/vendor_images/9999/image.jpg"},
    )
    assert missing_vendor.status_code == 404

    blank_url = client.post(
        f"/vendors/{vendor.id}/images",
        headers=headers,
        json={"image_url": "   "},
    )
    assert blank_url.status_code == 422

    absolute_url = client.post(
        f"/vendors/{vendor.id}/images",
        headers=headers,
        json={"image_url": "https://example.com/image.jpg"},
    )
    assert absolute_url.status_code == 422

    empty_update = client.patch(
        f"/vendors/{vendor.id}/images/9999",
        headers=headers,
        json={},
    )
    assert empty_update.status_code == 422
