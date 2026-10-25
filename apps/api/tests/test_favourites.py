from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, func, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import User, UserFavourite, Vendor


def create_user(session: Session, email: str = "favourites@example.com") -> User:
    user = User(display_name="Favourite User", email_address=email, password_hash="test-hash")
    session.add(user)
    session.flush()
    return user


def auth(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {user.id}"}


def test_favourites_are_private_paginated_and_most_recent_first(client: TestClient, session: Session) -> None:
    user = create_user(session)
    other = create_user(session, "other-favourites@example.com")
    vendors = [Vendor(name=f"Favourite Stall {index}") for index in range(7)]
    session.add_all(vendors)
    session.flush()
    now = datetime.now(timezone.utc)
    session.add_all(
        UserFavourite(user_id=user.id, vendor_id=vendor.id, created_at=now - timedelta(days=index))
        for index, vendor in enumerate(vendors)
    )
    session.add(UserFavourite(user_id=other.id, vendor_id=vendors[-1].id, created_at=now + timedelta(days=1)))
    session.commit()

    first = client.get("/auth/me/favourites", headers=auth(user)).json()
    last = client.get("/auth/me/favourites", params={"limit": 5, "offset": 5}, headers=auth(user)).json()
    assert (first["total"], first["limit"], first["offset"]) == (7, 5, 0)
    assert [item["vendor"] for item in first["items"]] == [
        {"id": vendor.id, "name": vendor.name} for vendor in vendors[:5]
    ]
    assert [item["vendor"]["id"] for item in last["items"]] == [vendor.id for vendor in vendors[5:]]
    assert (last["total"], last["offset"]) == (7, 5)
    assert all(item["created_at"] for item in first["items"])


def test_favourite_toggle_persists_and_cannot_change_another_users_list(client: TestClient, session: Session) -> None:
    user = create_user(session)
    other = create_user(session, "separate@example.com")
    vendor = Vendor(name="Saved Stall")
    session.add(vendor)
    session.flush()
    session.add(UserFavourite(user_id=other.id, vendor_id=vendor.id))
    session.commit()
    path = f"/auth/me/favourites/{vendor.id}"

    initial = client.get(path, headers=auth(user))
    assert initial.json() == {"vendor_id": vendor.id, "favourited": False, "created_at": None}
    saved = client.put(path, headers=auth(user))
    assert saved.status_code == 200
    assert saved.json()["favourited"] is True
    assert saved.json()["created_at"]
    session.expire_all()
    assert client.get(path, headers=auth(user)).json()["favourited"] is True
    assert client.get("/auth/me/favourites", headers=auth(user)).json()["total"] == 1

    for _ in range(2):
        removed = client.delete(path, headers=auth(user))
        assert removed.status_code == 204
        assert removed.content == b""
    assert client.get(path, headers=auth(user)).json()["favourited"] is False
    assert client.get("/auth/me/favourites", headers=auth(user)).json() == {
        "items": [], "total": 0, "limit": 5, "offset": 0,
    }
    assert client.get(path, headers=auth(other)).json()["favourited"] is True
    assert client.get("/auth/me/favourites", headers=auth(other)).json()["total"] == 1


def test_duplicate_favourite_and_refavourite_move_vendor_to_top_without_duplicates(client: TestClient, session: Session) -> None:
    user = create_user(session)
    older, newer = Vendor(name="Older"), Vendor(name="Newer")
    session.add_all([older, newer])
    session.flush()
    now = datetime.now(timezone.utc)
    session.add_all([
        UserFavourite(user_id=user.id, vendor_id=older.id, created_at=now - timedelta(days=2)),
        UserFavourite(user_id=user.id, vendor_id=newer.id, created_at=now - timedelta(days=1)),
    ])
    session.commit()
    path = f"/auth/me/favourites/{older.id}"

    for _ in range(2):
        response = client.put(path, headers=auth(user))
        assert response.status_code == 200
        assert response.json()["favourited"] is True
    page = client.get("/auth/me/favourites", headers=auth(user)).json()
    assert [item["vendor"]["id"] for item in page["items"]] == [older.id, newer.id]
    assert session.scalar(select(func.count()).select_from(UserFavourite)) == 2

    assert client.delete(path, headers=auth(user)).status_code == 204
    assert client.put(path, headers=auth(user)).status_code == 200
    page = client.get("/auth/me/favourites", headers=auth(user)).json()
    assert page["total"] == 2
    assert page["items"][0]["vendor"]["id"] == older.id


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 101}, {"offset": -1}])
def test_favourites_validate_pagination(client: TestClient, session: Session, params: dict) -> None:
    user = create_user(session)
    session.commit()
    assert client.get("/auth/me/favourites", params=params, headers=auth(user)).status_code == 422


@pytest.mark.parametrize("method", ["get", "put", "delete"])
def test_favourites_reject_missing_or_invalid_vendor(client: TestClient, session: Session, method: str) -> None:
    user = create_user(session)
    session.commit()
    request = getattr(client, method)
    assert request("/auth/me/favourites/99999", headers=auth(user)).status_code == 404
    for value in ("0", "-1", "invalid"):
        assert request(f"/auth/me/favourites/{value}", headers=auth(user)).status_code == 422
    assert session.scalar(select(func.count()).select_from(UserFavourite)) == 0


def test_all_favourite_endpoints_require_sign_in(client: TestClient) -> None:
    assert client.get("/auth/me/favourites").status_code == 401
    for method in (client.get, client.put, client.delete):
        assert method("/auth/me/favourites/1").status_code == 401


def test_favourites_migration_enforces_unique_pairs_and_cascades() -> None:
    path = Path(__file__).parents[1] / "alembic/versions/d103f25a0001_add_user_favourites.py"
    spec = importlib.util.spec_from_file_location("favourites_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text("PRAGMA foreign_keys=ON"))
        connection.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY)"))
        connection.execute(text("CREATE TABLE vendors (id INTEGER PRIMARY KEY)"))
        connection.execute(text("INSERT INTO users VALUES (1), (2)"))
        connection.execute(text("INSERT INTO vendors VALUES (1), (2)"))
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        connection.execute(text("INSERT INTO user_favourites (user_id, vendor_id) VALUES (1, 1), (2, 2)"))
        with pytest.raises(IntegrityError), connection.begin_nested():
            connection.execute(text("INSERT INTO user_favourites (user_id, vendor_id) VALUES (1, 1)"))
        with pytest.raises(IntegrityError), connection.begin_nested():
            connection.execute(text("INSERT INTO user_favourites (user_id, vendor_id) VALUES (99, 1)"))
        connection.execute(text("DELETE FROM vendors WHERE id=1"))
        assert connection.scalar(text("SELECT COUNT(*) FROM user_favourites")) == 1
        connection.execute(text("DELETE FROM users WHERE id=2"))
        assert connection.scalar(text("SELECT COUNT(*) FROM user_favourites")) == 0
        migration.downgrade()
        assert not inspect(connection).has_table("user_favourites")
        assert connection.scalar(text("SELECT COUNT(*) FROM users")) == 1
        assert connection.scalar(text("SELECT COUNT(*) FROM vendors")) == 1
    engine.dispose()
