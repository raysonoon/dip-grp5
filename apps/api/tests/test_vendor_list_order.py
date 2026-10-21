from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import Vendor


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
