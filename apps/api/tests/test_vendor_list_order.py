from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import User, UserFoodPreferences, Vendor
from app.services.vendor_recommender import VendorRecommendation


def _stamp(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)


def _add_vendors(session: Session) -> None:
    # Inserted deliberately out of alphabetical order (and with descending
    # created_at) so the assertions below cannot pass from insertion/recency
    # order by accident.
    session.add_all(
        [
            Vendor(name="Zhao Ji Noodle House", created_at=_stamp("2024-01-01")),
            Vendor(name="ban mian corner", created_at=_stamp("2024-06-01")),
            Vendor(name="Chicken Rice Stall", created_at=_stamp("2024-03-01")),
        ]
    )
    session.commit()


def test_vendor_list_falls_back_to_alphabetical_order(
    client,
    session: Session,
) -> None:
    _add_vendors(session)

    response = client.get("/vendors")

    assert response.status_code == 200
    names = [item["name"] for item in response.json()["items"]]
    assert names == [
        "ban mian corner",
        "Chicken Rice Stall",
        "Zhao Ji Noodle House",
    ]


def test_vendor_list_alphabetical_order_survives_pagination(
    client,
    session: Session,
) -> None:
    _add_vendors(session)

    first = client.get("/vendors", params={"limit": 2, "offset": 0})
    second = client.get("/vendors", params={"limit": 2, "offset": 2})

    assert [item["name"] for item in first.json()["items"]] == [
        "ban mian corner",
        "Chicken Rice Stall",
    ]
    assert [item["name"] for item in second.json()["items"]] == [
        "Zhao Ji Noodle House"
    ]


def test_vendor_list_accepts_coordinates_and_still_orders_alphabetically(
    client,
    session: Session,
) -> None:
    # SQLite has no PostGIS, so the distance tiebreak is skipped and the
    # alphabetical fallback must still hold.
    _add_vendors(session)

    response = client.get(
        "/vendors",
        params={"lat": 1.3483, "lng": 103.6831},
    )

    assert response.status_code == 200
    names = [item["name"] for item in response.json()["items"]]
    assert names == [
        "ban mian corner",
        "Chicken Rice Stall",
        "Zhao Ji Noodle House",
    ]


def test_vendor_list_rejects_out_of_range_coordinates(client) -> None:
    assert client.get("/vendors", params={"lat": 91, "lng": 103.68}).status_code == 422
    assert client.get("/vendors", params={"lat": 1.34, "lng": 181}).status_code == 422


def test_recommended_vendors_come_first_then_alphabetical(
    client,
    session: Session,
    monkeypatch,
) -> None:
    user = User(
        display_name="Ordering User",
        email_address="ordering@test.com",
        email_canonical="ordering@test.com",
        password_hash="test",
        role="user",
    )
    session.add(user)
    session.commit()
    session.refresh(user)

    session.add(
        UserFoodPreferences(
            user_id=user.id,
            dietary_restrictions=[],
            cuisines=[],
            locations=[],
            likes=[],
            dislikes=[],
            lifestyle=[],
            onboarding_status="completed",
        )
    )

    # Inserted newest-last so a recency tiebreak would surface Zulu last.
    session.add_all(
        [
            Vendor(name="Alpha Cafe", created_at=_stamp("2024-01-01")),
            Vendor(name="Mike Cafe", created_at=_stamp("2024-02-01")),
            Vendor(name="Zulu Cafe", created_at=_stamp("2024-03-01")),
            Vendor(name="Beta Cafe", created_at=_stamp("2024-04-01")),
        ]
    )
    session.commit()

    zulu = session.query(Vendor).filter_by(name="Zulu Cafe").one()

    monkeypatch.setattr(
        "app.api.routes.vendors.VendorRecommender.recommend",
        lambda self, preferences, *, limit=6: [
            VendorRecommendation(vendor=zulu, similarity=0.9, score=0.9)
        ],
    )

    response = client.get(
        "/vendors",
        headers={"Authorization": f"Bearer {user.id}"},
        params={
            "sort": "recommended",
            "lat": 1.3483,
            "lng": 103.6831,
        },
    )

    assert response.status_code == 200
    items = response.json()["items"]
    assert [item["name"] for item in items] == [
        "Zulu Cafe",
        "Alpha Cafe",
        "Beta Cafe",
        "Mike Cafe",
    ]
    assert [item["recommended"] for item in items] == [
        True,
        False,
        False,
        False,
    ]
