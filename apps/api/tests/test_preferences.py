from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import User


def create_user(session: Session, email: str = "preferences@test.com") -> User:
    user = User(
        display_name="Preferences User",
        email_address=email,
        email_canonical=email.lower(),
        password_hash="test",
        role="user",
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def test_preferences_are_empty_until_user_saves_them(
    client: TestClient,
    session: Session,
) -> None:
    user = create_user(session)

    response = client.get(
        "/preferences/me",
        headers={"Authorization": f"Bearer {user.id}"},
    )

    assert response.status_code == 200
    assert response.json() is None


def test_user_can_save_and_read_food_preferences(
    client: TestClient,
    session: Session,
) -> None:
    user = create_user(session)

    payload = {
        "allergies": ["Halal"],
        "cuisines": ["Japanese", "Western"],
        "locations": ["North Spine"],
        "likes": ["Coffee", "Protein"],
        "dislikes": ["Bubble tea"],
        "lifestyle": ["High protein"],
        "onboarding_status": "completed",
    }

    save_response = client.put(
        "/preferences/me",
        headers={"Authorization": f"Bearer {user.id}"},
        json=payload,
    )

    assert save_response.status_code == 200
    assert save_response.json() == payload

    read_response = client.get(
        "/preferences/me",
        headers={"Authorization": f"Bearer {user.id}"},
    )

    assert read_response.status_code == 200
    assert read_response.json() == payload


def test_user_can_skip_preferences(
    client: TestClient,
    session: Session,
) -> None:
    user = create_user(session)

    payload = {
        "allergies": [],
        "cuisines": [],
        "locations": [],
        "likes": [],
        "dislikes": [],
        "lifestyle": [],
        "onboarding_status": "skipped",
    }

    response = client.put(
        "/preferences/me",
        headers={"Authorization": f"Bearer {user.id}"},
        json=payload,
    )

    assert response.status_code == 200
    assert response.json()["onboarding_status"] == "skipped"


def test_preferences_require_authentication(
    client: TestClient,
) -> None:
    assert client.get("/preferences/me").status_code == 401
    assert client.put(
        "/preferences/me",
        json={
            "allergies": [],
            "cuisines": [],
            "locations": [],
            "likes": [],
            "dislikes": [],
            "lifestyle": [],
            "onboarding_status": "completed",
        },
    ).status_code == 401