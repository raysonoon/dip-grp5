from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import User, Vendor
from app.services.sql_search import PgSqlStore
from app.services.structured_filters import (
    StructuredFilter,
    extract_structured_filters,
)


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
                price_range="$1-10",
                opening_hours="Mon to Fri: 10am to 8pm",
                halal=False,
                vegetarian=True,
                average_google_rating=4.0,
            ),
            Vendor(
                name="Cheap Rice",
                location="North Spine",
                unit_code="NS-03",
                category="Chinese",
                price_range="$1-10",
                opening_hours="11:00 - 22:00",
                halal=False,
                vegetarian=False,
                average_google_rating=None,
            ),
            Vendor(
                name="North Eight Cafe",
                location="North Spine",
                unit_code="NS-08",
                category="Cafe",
                price_range="$20-30",
                opening_hours="10:00 - 20:00",
                halal=False,
                vegetarian=False,
                average_google_rating=2.3,
            ),
            Vendor(
                name="Daily Cafe",
                location="Hall 14",
                unit_code="H14-01",
                category="Indian",
                price_range="$$$",
                opening_hours="Daily: 9am to 9.30pm",
                halal=False,
                vegetarian=False,
                average_google_rating=3.5,
            ),
            Vendor(
                name="Eight Thirty Cafe",
                location="Hall 10",
                unit_code="H10-01",
                category="Thai",
                price_range="$$$",
                opening_hours=(
                    "PH: Closed; School Term - Sat, Sun & PH: "
                    "10.30am to 8.30pm"
                ),
                halal=False,
                vegetarian=False,
                average_google_rating=3.0,
            ),
            Vendor(
                name="Sunday Closed Cafe",
                location="Hall 12",
                unit_code="H12-01",
                category="Thai",
                price_range="$$$$",
                opening_hours="Mon to Sat: 9am to 9pm; Sun & PH: Closed",
                halal=False,
                vegetarian=False,
                average_google_rating=2.9,
            ),
            Vendor(
                name="Sunday Brunch",
                location="Hall 11",
                unit_code="H11-01",
                category="Japanese",
                price_range="$10-20",
                opening_hours="Sunday: 9am to 2pm",
                halal=False,
                vegetarian=False,
                average_google_rating=2.8,
            ),
            Vendor(
                name="Twenty Four Cafe",
                location="NIE",
                unit_code="NIE-01",
                category="Malay",
                price_range="$$$$",
                opening_hours="Daily: 24 hours",
                halal=False,
                vegetarian=False,
                average_google_rating=2.7,
            ),
            Vendor(
                name="Always Open",
                location="Hall 16",
                unit_code="H16-01",
                category="Cafe",
                price_range="$$$",
                opening_hours="Daily: 24-hour",
                halal=False,
                vegetarian=False,
                average_google_rating=2.6,
            ),
            Vendor(
                name="Ten PM Cafe",
                location="Hall 13",
                unit_code="H13-01",
                category="Mexican",
                price_range="$$$",
                opening_hours="Daily: 10.30am to 10.30pm",
                halal=False,
                vegetarian=False,
                average_google_rating=2.5,
            ),
            Vendor(
                name="Eleven PM Cafe",
                location="Hall 15",
                unit_code="H15-01",
                category="Italian",
                price_range="$$$$",
                opening_hours="Daily: 10.30am to 11pm",
                halal=False,
                vegetarian=False,
                average_google_rating=2.4,
            ),
        ]
    )
    session.flush()


def _assert_search_and_resolve_names(
    session: Session,
    store: PgSqlStore,
    question: str,
    expected_names: set[str],
) -> None:
    filters = extract_structured_filters(question)
    search_names = {result.vendor_name for result in store.search(filters)}
    resolved_names = {
        session.get(Vendor, vendor_id).name
        for vendor_id in store.resolve_vendor_ids(filters)
    }

    assert search_names == expected_names, question
    assert resolved_names == expected_names, question


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


def test_sql_search_filters_by_vendor_ids(session: Session) -> None:
    _seed_vendors(session)
    store = PgSqlStore(session)
    halal = session.scalar(
        select(Vendor).where(Vendor.name == "Halal Nook")
    )
    filters = StructuredFilter(vendor_ids=[halal.id])

    results = store.search(filters)

    assert [result.vendor_name for result in results] == ["Halal Nook"]


def test_negated_only_filters_apply_to_search_and_resolve(
    session: Session,
) -> None:
    _seed_vendors(session)
    store = PgSqlStore(session)
    all_names = {
        "Halal Nook",
        "Green Bowl",
        "Cheap Rice",
        "North Eight Cafe",
        "Daily Cafe",
        "Eight Thirty Cafe",
        "Sunday Closed Cafe",
        "Sunday Brunch",
        "Twenty Four Cafe",
        "Always Open",
        "Ten PM Cafe",
        "Eleven PM Cafe",
    }

    cases = (
        ("not Indian", all_names - {"Daily Cafe"}),
        ("not near Hall 14", all_names - {"Daily Cafe"}),
        (
            "not cheap",
            all_names
            - {"Halal Nook", "Green Bowl", "Cheap Rice", "Sunday Brunch"},
        ),
        (
            "not too expensive",
            {"Halal Nook", "Green Bowl", "Cheap Rice", "Sunday Brunch"},
        ),
        (
            "not open on Sunday",
            {
                "Halal Nook",
                "Green Bowl",
                "Cheap Rice",
                "North Eight Cafe",
                "Sunday Closed Cafe",
            },
        ),
    )

    for question, expected_names in cases:
        _assert_search_and_resolve_names(
            session,
            store,
            question,
            expected_names,
        )


def test_positive_and_negative_filters_compose_with_and(
    session: Session,
) -> None:
    _seed_vendors(session)
    store = PgSqlStore(session)

    _assert_search_and_resolve_names(
        session,
        store,
        "Indian food but not Chinese",
        {"Daily Cafe"},
    )
    _assert_search_and_resolve_names(
        session,
        store,
        "Indian food but not Indian",
        set(),
    )


def test_open_hours_filters_apply_to_search_and_resolve(
    session: Session,
) -> None:
    _seed_vendors(session)
    store = PgSqlStore(session)
    open_after_eight = {
        "Halal Nook",
        "Cheap Rice",
        "Daily Cafe",
        "Eight Thirty Cafe",
        "Sunday Closed Cafe",
        "Twenty Four Cafe",
        "Always Open",
        "Ten PM Cafe",
        "Eleven PM Cafe",
    }
    open_on_sunday = {
        "Daily Cafe",
        "Eight Thirty Cafe",
        "Sunday Brunch",
        "Twenty Four Cafe",
        "Always Open",
        "Ten PM Cafe",
        "Eleven PM Cafe",
    }

    for question, expected_names in (
        ("open after 8pm", open_after_eight),
        ("open late", open_after_eight),
        ("open on Sunday", open_on_sunday),
        (
            "not open after 8pm",
            {"Green Bowl", "North Eight Cafe", "Sunday Brunch"},
        ),
    ):
        _assert_search_and_resolve_names(
            session,
            store,
            question,
            expected_names,
        )


def test_q042_open_late_is_not_reduced_to_location_only(
    session: Session,
) -> None:
    _seed_vendors(session)
    store = PgSqlStore(session)

    _assert_search_and_resolve_names(
        session,
        store,
        "What's a good place near North Spine that's open late?",
        {"Halal Nook", "Cheap Rice"},
    )


def test_open_late_parses_fractional_pm_times_and_excludes_exact_eight(
    session: Session,
) -> None:
    _seed_vendors(session)
    store = PgSqlStore(session)
    filters = extract_structured_filters("open late")

    search_names = {result.vendor_name for result in store.search(filters)}
    resolved_names = {
        session.get(Vendor, vendor_id).name
        for vendor_id in store.resolve_vendor_ids(filters)
    }

    for names in (search_names, resolved_names):
        assert {
            "Eight Thirty Cafe",  # 8.30pm
            "Daily Cafe",  # 9.30pm
            "Ten PM Cafe",  # 10.30pm
            "Twenty Four Cafe",  # 24 hours
            "Always Open",  # 24-hour
        } <= names
        assert {"Green Bowl", "North Eight Cafe"}.isdisjoint(names)


def test_count_with_only_negative_filter_is_not_unfiltered(
    session: Session,
) -> None:
    _seed_vendors(session)
    store = PgSqlStore(session)

    results = store.search(extract_structured_filters("How many not Indian?"))

    assert results[0].count == 11
