from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from app.models import User, UserFoodPreferences, Vendor
from app.services.vendor_search import (
    build_vendor_search_plan,
    parse_vendor_search_query,
)


def _seed_search_vendors(session: Session) -> None:
    session.add_all(
        [
            Vendor(
                name="Starbucks - NTU",
                location="North Spine Plaza",
                unit_code="NS3-01-06",
                category="Coffee shop",
                halal=False,
                vegetarian=True,
            ),
            Vendor(
                name="Western Delights",
                location="Food Court 2",
                unit_code="FC2-01-01",
                category="Western restaurant",
                halal=True,
                vegetarian=False,
            ),
            Vendor(
                name="Green Leaf",
                location="South Spine",
                unit_code="SS1-01-01",
                category="Vegetarian restaurant",
                halal=False,
                vegetarian=True,
            ),
            Vendor(
                name="A Hot Hideout @ Jurong West (NTU)",
                location="60 Nanyang Cres",
                unit_code="BJH-03-02",
                category="Chinese restaurant",
                halal=False,
                vegetarian=True,
            ),
        ]
    )
    session.commit()


def test_parse_vendor_search_normalizes_aliases_and_filters() -> None:
    parsed = parse_vendor_search_query(
        "  VEG food near NorthSpine!!!  "
    )

    assert parsed.normalized_text == "vegetarian food near north spine"
    assert parsed.lexical_text == "food"
    assert parsed.vegetarian is True
    assert parsed.location_terms == ("north spine",)


def test_vendor_search_combines_keywords_and_location_aliases(
    client: TestClient,
    session: Session,
) -> None:
    _seed_search_vendors(session)

    response = client.get("/vendors", params={"q": "western canteen two"})

    assert response.status_code == 200
    assert [item["name"] for item in response.json()["items"]] == [
        "Western Delights"
    ]


def test_vendor_search_applies_dietary_filters(
    client: TestClient,
    session: Session,
) -> None:
    _seed_search_vendors(session)

    halal = client.get("/vendors", params={"q": "halal western"})
    vegetarian = client.get(
        "/vendors",
        params={"q": "vegetarian south spine"},
    )

    assert [item["name"] for item in halal.json()["items"]] == [
        "Western Delights"
    ]
    assert [item["name"] for item in vegetarian.json()["items"]] == [
        "Green Leaf"
    ]


def test_vendor_search_expands_general_synonyms(
    client: TestClient,
    session: Session,
) -> None:
    _seed_search_vendors(session)

    response = client.get("/vendors", params={"q": "kopitiam"})

    assert response.status_code == 200
    assert [item["name"] for item in response.json()["items"]] == [
        "Western Delights"
    ]


def test_western_food_is_a_category_filter_not_a_fuzzy_name_match(
    client: TestClient,
    session: Session,
) -> None:
    _seed_search_vendors(session)

    spaced = client.get("/vendors", params={"q": "western food"})
    compact = client.get("/vendors", params={"q": "westernfood"})

    assert [item["name"] for item in spaced.json()["items"]] == [
        "Western Delights"
    ]
    assert [item["name"] for item in compact.json()["items"]] == [
        "Western Delights"
    ]


def test_postgresql_fuzzy_matching_excludes_location_text(
    session: Session,
) -> None:
    original_dialect_name = session.get_bind().dialect.name
    session.get_bind().dialect.name = "postgresql"
    try:
        plan = build_vendor_search_plan(session, "Starbuks")
    finally:
        session.get_bind().dialect.name = original_dialect_name

    statement = select(Vendor.id).where(*plan.filters)
    compiled = str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )

    fuzzy_clauses = [
        clause
        for clause in compiled.split(" OR ")
        if "word_similarity" in clause
    ]
    assert fuzzy_clauses
    assert all("vendors.location" not in clause for clause in fuzzy_clauses)
    assert all("vendors.search_document" not in clause for clause in fuzzy_clauses)


def test_vendor_list_falls_back_when_recommendations_fail(
    client: TestClient,
    session: Session,
    monkeypatch,
) -> None:
    user = User(
        display_name="Recommendation User",
        email_address="recommendation@test.com",
        email_canonical="recommendation@test.com",
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
            likes=["Coffee"],
            dislikes=[],
            lifestyle=[],
            onboarding_status="completed",
        )
    )

    session.add_all(
        [
            Vendor(
                name="Older Vendor",
                location="North Spine",
                category="Cafe",
            ),
            Vendor(
                name="Newer Vendor",
                location="South Spine",
                category="Cafe",
            ),
        ]
    )
    session.commit()

    def fail_recommendation(*args, **kwargs):
        raise RuntimeError("embedding unavailable")

    monkeypatch.setattr(
        "app.api.routes.vendors.VendorRecommender.recommend",
        fail_recommendation,
    )

    response = client.get(
        "/vendors",
        headers={"Authorization": f"Bearer {user.id}"},
        params={
            "sort": "recommended",
            "limit": 1,
            "offset": 0,
        },
    )

    assert response.status_code == 200
    assert len(response.json()["items"]) == 1
    assert response.json()["items"][0]["recommended"] is False
    assert response.json()["items"][0]["name"] == "Newer Vendor"