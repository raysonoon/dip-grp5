"""GET /vendors sort options added for the Nearby / Alphabetical dropdown.

These run on the default SQLite test database. Distance ordering itself needs
PostGIS; without it (or without lat/lng) "nearby" falls back to A-Z, which is
the silent fallback the Food page relies on when location is unavailable.
"""

from sqlalchemy.orm import Session

from app.models import Vendor

USER = {"lat": 1.3483, "lng": 103.6817}


def _add_vendors(session: Session) -> None:
    # Inserted out of alphabetical order so no assertion passes by accident.
    session.add_all(
        [
            Vendor(name="Zhao Ji Noodle House"),
            Vendor(name="ban mian corner"),
            Vendor(name="Chicken Rice Stall"),
        ]
    )
    session.commit()


def _names(response) -> list[str]:
    assert response.status_code == 200, response.text
    return [item["name"] for item in response.json()["items"]]


A_TO_Z = ["ban mian corner", "Chicken Rice Stall", "Zhao Ji Noodle House"]


def test_alphabetical_sort_is_case_insensitive_a_to_z(
    client,
    session: Session,
) -> None:
    _add_vendors(session)

    response = client.get("/vendors", params={"sort": "alphabetical"})

    assert _names(response) == A_TO_Z


def test_alphabetical_sort_ignores_location(
    client,
    session: Session,
) -> None:
    _add_vendors(session)

    response = client.get("/vendors", params={"sort": "alphabetical", **USER})

    assert _names(response) == A_TO_Z


def test_nearby_sort_without_location_falls_back_to_alphabetical(
    client,
    session: Session,
) -> None:
    _add_vendors(session)

    response = client.get("/vendors", params={"sort": "nearby"})

    assert _names(response) == A_TO_Z


def test_nearby_sort_is_accepted_with_location(
    client,
    session: Session,
) -> None:
    _add_vendors(session)

    response = client.get("/vendors", params={"sort": "nearby", **USER})

    # SQLite has no PostGIS, so vendors have no distance and keep A-Z order.
    assert _names(response) == A_TO_Z


def test_unknown_sort_is_rejected(client) -> None:
    response = client.get("/vendors", params={"sort": "distance"})

    assert response.status_code == 422