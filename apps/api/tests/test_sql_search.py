from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import User, Vendor
from app.services.sql_search import PgSqlStore
from app.services.structured_filters import extract_structured_filters


def _seed_vendors(session: Session) -> None:
    session.add_all(
        [
            Vendor(
                name="Halal Nook",
                location="North Spine",
                unit_code="NS-01",
                category="Korean",
                price_range="$$",
                opening_hours="09:00 - 21:00",
                halal=True,
                vegetarian=False,
                average_google_rating=4.5,
            ),
            Vendor(
                name="Green Bowl",
                location="South Spine",
                unit_code="SS-02",
                category="Western",
                price_range="$",
                opening_hours="10:00 - 20:00",
                halal=False,
                vegetarian=True,
                average_google_rating=4.0,
            ),
            Vendor(
                name="Cheap Rice",
                location="North Spine",
                unit_code="NS-03",
                category="Chinese",
                price_range="$",
                opening_hours="11:00 - 22:00",
                halal=False,
                vegetarian=False,
                average_google_rating=None,
            ),
        ]
    )
    session.flush()


def test_sql_search_filters_by_dietary_and_location(
    session: Session,
) -> None:
    _seed_vendors(session)
    store = PgSqlStore(session)
    filters = extract_structured_filters(
        "Which places have halal food near North Spine?"
    )

    results = store.search(filters)

    assert [result.vendor_name for result in results] == ["Halal Nook"]


def test_sql_search_count(session: Session) -> None:
    _seed_vendors(session)
    store = PgSqlStore(session)
    filters = extract_structured_filters("How many halal places are there?")

    results = store.search(filters)

    assert len(results) == 1
    assert results[0].count == 1


def test_sql_search_rank_by_rating(session: Session) -> None:
    _seed_vendors(session)
    store = PgSqlStore(session)
    filters = extract_structured_filters("top 2 best stalls")

    results = store.search(filters)

    assert [result.vendor_name for result in results] == [
        "Halal Nook",
        "Green Bowl",
    ]


def test_sql_search_budget_cheap(session: Session) -> None:
    _seed_vendors(session)
    store = PgSqlStore(session)
    filters = extract_structured_filters("cheap food near North Spine")

    results = store.search(filters)

    assert [result.vendor_name for result in results] == [
        "Cheap Rice",
        "Halal Nook",
    ]


def test_resolve_vendor_ids(session: Session) -> None:
    _seed_vendors(session)
    store = PgSqlStore(session)
    filters = extract_structured_filters("Where can I get vegetarian food?")

    vendor_ids = store.resolve_vendor_ids(filters)

    assert len(vendor_ids) == 1
    vendor = session.get(Vendor, vendor_ids[0])
    assert vendor.name == "Green Bowl"


def test_review_count_is_aggregated(session: Session) -> None:
    _seed_vendors(session)
    user = User(
        display_name="Reviewer",
        email_address="reviewer@example.com",
        password_hash="x",
        role="user",
    )
    session.add(user)
    session.flush()
    vendor = session.scalar(
        select(Vendor).where(Vendor.name == "Halal Nook")
    )
    from app.models import Review

    session.add_all(
        [
            Review(user_id=user.id, vendor_id=vendor.id, rating_half_steps=8),
            Review(user_id=user.id, vendor_id=vendor.id, rating_half_steps=10),
        ]
    )
    session.commit()

    store = PgSqlStore(session)
    filters = extract_structured_filters("halal food")
    result = store.search(filters)[0]
    assert result.review_count == 2