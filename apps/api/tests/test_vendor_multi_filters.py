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
                price_range="$1-10",
                halal=True,
                vegetarian=False,
            ),
            Vendor(
                name="Japanese Place",
                location="South Spine",
                category="Japanese",
                cuisine="Japanese",
                price_range="$10-20",
                halal=False,
                vegetarian=True,
            ),
            Vendor(
                name="Hall Place",
                location="Hall 14",
                category="Local",
                cuisine="Local",
                price_range="$20-30",
                halal=None,
                vegetarian=None,
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


def test_multiple_price_ranges_match_any_selected_value(
    client,
    session: Session,
) -> None:
    _seed(session)

    response = client.get(
        "/vendors",
        params=[("price_range", "$1-10"), ("price_range", "$20-30")],
    )

    assert sorted(_names(response)) == ["Hall Place", "Korean Place"]


def test_halal_filter_only_matches_explicitly_halal_vendors(
    client,
    session: Session,
) -> None:
    _seed(session)

    response = client.get("/vendors", params={"halal": "true"})

    assert _names(response) == ["Korean Place"]


def test_vegetarian_filter_only_matches_explicitly_vegetarian_vendors(
    client,
    session: Session,
) -> None:
    _seed(session)

    response = client.get("/vendors", params={"vegetarian": "true"})

    assert _names(response) == ["Japanese Place"]


def test_halal_and_vegetarian_selection_matches_only_vendors_with_both(
    client,
    session: Session,
) -> None:
    session.add_all(
        [
            Vendor(name="Both Place", halal=True, vegetarian=True),
            Vendor(name="Halal Only", halal=True, vegetarian=False),
            Vendor(name="Veg Only", halal=False, vegetarian=True),
        ]
    )
    session.commit()

    response = client.get(
        "/vendors",
        params={"halal": "true", "vegetarian": "true"},
    )

    assert _names(response) == ["Both Place"]


def test_price_and_dietary_filters_combine_with_other_groups(
    client,
    session: Session,
) -> None:
    _seed(session)

    mismatch = client.get(
        "/vendors",
        params={"price_range": "$1-10", "cuisine": "Japanese"},
    )
    match = client.get(
        "/vendors",
        params={"price_range": "$1-10", "cuisine": "Korean", "halal": "true"},
    )

    assert _names(mismatch) == []
    assert _names(match) == ["Korean Place"]

