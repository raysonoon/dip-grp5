from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from app.models import Vendor
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
