from sqlalchemy.orm import Session

from app.models import Vendor


def _seed(session: Session) -> None:
    session.add_all(
        [
            Vendor(
                name="Korean Place",
                location="North Spine",
                category="Korean",
                cuisine="Korean",
            ),
            Vendor(
                name="Japanese Place",
                location="South Spine",
                category="Japanese",
                cuisine="Japanese",
            ),
            Vendor(
                name="Hall Place",
                location="Hall 14",
                category="Local",
                cuisine="Local",
            ),
        ]
    )
    session.commit()


def _names(response) -> list[str]:
    assert response.status_code == 200
    return [item["name"] for item in response.json()["items"]]


def test_multiple_categories_match_any_selected_value(
    client,
    session: Session,
) -> None:
    _seed(session)

    response = client.get(
        "/vendors",
        params=[("category", "Korean"), ("category", "Japanese")],
    )

    assert sorted(_names(response)) == ["Japanese Place", "Korean Place"]


def test_multiple_cuisines_match_any_selected_value(
    client,
    session: Session,
) -> None:
    _seed(session)

    response = client.get(
        "/vendors",
        params=[("cuisine", "Korean"), ("cuisine", "Japanese")],
    )

    assert sorted(_names(response)) == ["Japanese Place", "Korean Place"]


def test_multiple_locations_match_any_selected_value(
    client,
    session: Session,
) -> None:
    _seed(session)

    response = client.get(
        "/vendors",
        params=[("location", "North Spine"), ("location", "South Spine")],
    )

    assert sorted(_names(response)) == ["Japanese Place", "Korean Place"]


def test_hall_location_still_uses_exact_match(
    client,
    session: Session,
) -> None:
    _seed(session)

    response = client.get("/vendors", params={"location": "Hall 14"})

    assert _names(response) == ["Hall Place"]


def test_filters_across_groups_are_combined_with_and(
    client,
    session: Session,
) -> None:
    _seed(session)

    no_match = client.get(
        "/vendors",
        params={"category": "Korean", "cuisine": "Japanese"},
    )
    match = client.get(
        "/vendors",
        params={"category": "Korean", "cuisine": "Korean"},
    )

    assert _names(no_match) == []
    assert _names(match) == ["Korean Place"]
