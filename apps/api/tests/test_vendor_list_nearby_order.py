"""GET /vendors?sort=recommended: recommended -> nearest-first -> A-Z.

Validation tests run on the default SQLite test database. The ordering tests
need PostGIS (ST_Distance on geography), so they follow the same pattern as
test_vector_search.py: they are skipped unless TEST_DATABASE_URL points at a
dedicated Postgres/PostGIS test database.
"""

import os
from collections.abc import Iterator
from typing import get_args

import pytest
from fastapi.testclient import TestClient
from geoalchemy2 import WKTElement
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.api.dependencies import DbSession
from app.main import app
from app.models import Vendor

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

requires_postgis = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is not set; skipping PostGIS vendor ordering test",
)

# User standing at the NTU Innovation Centre.
USER = {"lat": 1.3483, "lng": 103.6817}


# --------------------------------------------------------------------------
# Validation: no database rows needed, runs on SQLite.
# --------------------------------------------------------------------------


def test_lat_without_lng_is_rejected(client) -> None:
    response = client.get("/vendors", params={"lat": USER["lat"]})

    assert response.status_code == 422


def test_lng_without_lat_is_rejected(client) -> None:
    response = client.get("/vendors", params={"lng": USER["lng"]})

    assert response.status_code == 422


def test_out_of_range_coordinates_are_rejected(client) -> None:
    response = client.get("/vendors", params={"lat": 91, "lng": 103.68})

    assert response.status_code == 422


# --------------------------------------------------------------------------
# Ordering: needs PostGIS.
# --------------------------------------------------------------------------


@pytest.fixture
def pg_session() -> Iterator[Session]:
    assert TEST_DATABASE_URL is not None
    if "test" not in TEST_DATABASE_URL.rsplit("/", 1)[-1]:
        pytest.fail(
            "TEST_DATABASE_URL must point at a dedicated test database "
            "(its name must contain 'test'); these tests wipe the vendors table."
        )

    engine = create_engine(TEST_DATABASE_URL)
    with engine.begin() as connection:
        for extension in ("postgis", "pg_trgm", "unaccent", "vector"):
            connection.execute(
                text(f'CREATE EXTENSION IF NOT EXISTS "{extension}"')
            )
    Vendor.metadata.create_all(engine)

    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = factory()
    session.execute(text("TRUNCATE vendors RESTART IDENTITY CASCADE"))
    session.commit()
    try:
        yield session
    finally:
        session.rollback()
        session.execute(text("TRUNCATE vendors RESTART IDENTITY CASCADE"))
        session.commit()
        session.close()
        engine.dispose()


@pytest.fixture
def pg_client(pg_session: Session) -> Iterator[TestClient]:
    # DbSession is Annotated[Session, Depends(<db dependency>)]; override that
    # dependency so the API reads from the PostGIS test database.
    db_dependency = get_args(DbSession)[1].dependency

    def _override() -> Iterator[Session]:
        yield pg_session

    app.dependency_overrides[db_dependency] = _override
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(db_dependency, None)


def _point(lat: float, lng: float) -> WKTElement:
    # WKT is (lng lat).
    return WKTElement(f"POINT({lng} {lat})", srid=4326)


def _add_vendors(session: Session) -> None:
    # Names are chosen so alphabetical order differs from distance order,
    # and inserted in neither order, so no assertion can pass by accident.
    session.add_all(
        [
            Vendor(
                name="Bravo Mid",  # ~900 m away
                map_coordinates=_point(1.3550, 103.6860),
                average_google_rating=3.0,
            ),
            Vendor(
                name="Zebra Bites",  # no coordinates
                map_coordinates=None,
                average_google_rating=5.0,
            ),
            Vendor(
                name="Alpha Far",  # ~14 km away, beyond /nearby's 5 km cap
                map_coordinates=_point(1.3000, 103.8000),
                average_google_rating=4.0,
            ),
            Vendor(
                name="Zulu Near",  # ~20 m away
                map_coordinates=_point(1.3485, 103.6817),
                average_google_rating=2.0,
            ),
            Vendor(
                name="Aardvark Cafe",  # no coordinates
                map_coordinates=None,
                average_google_rating=1.0,
            ),
        ]
    )
    session.commit()


def _names(response) -> list[str]:
    assert response.status_code == 200, response.text
    return [item["name"] for item in response.json()["items"]]


@requires_postgis
def test_recommended_sort_exposes_distance_metres(
    pg_client: TestClient,
    pg_session: Session,
) -> None:
    _add_vendors(pg_session)

    response = pg_client.get("/vendors", params={"sort": "recommended", **USER})

    # /vendors now returns the same distance it sorts by, so cards can show it.
    assert response.status_code == 200, response.text
    by_name = {
        item["name"]: item["distance_m"] for item in response.json()["items"]
    }

    assert by_name["Zulu Near"] == pytest.approx(0, abs=30)
    assert by_name["Bravo Mid"] > by_name["Zulu Near"]
    assert by_name["Alpha Far"] > by_name["Bravo Mid"]
    # Vendors without map_coordinates have no distance.
    assert by_name["Zebra Bites"] is None
    assert by_name["Aardvark Cafe"] is None


@requires_postgis
def test_recommended_sort_orders_nearest_first_then_alphabetical(
    pg_client: TestClient,
    pg_session: Session,
) -> None:
    _add_vendors(pg_session)

    response = pg_client.get("/vendors", params={"sort": "recommended", **USER})

    # Nearest-first with no distance cutoff (Alpha Far is ~14 km away),
    # then vendors without map_coordinates, A-Z.
    assert _names(response) == [
        "Zulu Near",
        "Bravo Mid",
        "Alpha Far",
        "Aardvark Cafe",
        "Zebra Bites",
    ]


@requires_postgis
def test_recommended_sort_is_the_default_and_uses_location(
    pg_client: TestClient,
    pg_session: Session,
) -> None:
    _add_vendors(pg_session)

    response = pg_client.get("/vendors", params=USER)

    assert _names(response)[:3] == ["Zulu Near", "Bravo Mid", "Alpha Far"]


@requires_postgis
def test_nearby_order_survives_pagination(
    pg_client: TestClient,
    pg_session: Session,
) -> None:
    _add_vendors(pg_session)

    first = pg_client.get("/vendors", params={"limit": 2, "offset": 0, **USER})
    second = pg_client.get("/vendors", params={"limit": 2, "offset": 2, **USER})
    third = pg_client.get("/vendors", params={"limit": 2, "offset": 4, **USER})

    assert _names(first) == ["Zulu Near", "Bravo Mid"]
    assert _names(second) == ["Alpha Far", "Aardvark Cafe"]
    assert _names(third) == ["Zebra Bites"]


@requires_postgis
def test_without_location_recommended_sort_is_alphabetical(
    pg_client: TestClient,
    pg_session: Session,
) -> None:
    _add_vendors(pg_session)

    response = pg_client.get("/vendors", params={"sort": "recommended"})

    # Geolocation denied/unavailable: no nearby tier, plain A-Z.
    assert _names(response) == [
        "Aardvark Cafe",
        "Alpha Far",
        "Bravo Mid",
        "Zebra Bites",
        "Zulu Near",
    ]


@requires_postgis
def test_rating_sort_ignores_location(
    pg_client: TestClient,
    pg_session: Session,
) -> None:
    _add_vendors(pg_session)

    without = pg_client.get("/vendors", params={"sort": "rating"})
    with_location = pg_client.get("/vendors", params={"sort": "rating", **USER})

    expected = [
        "Zebra Bites",
        "Alpha Far",
        "Bravo Mid",
        "Zulu Near",
        "Aardvark Cafe",
    ]
    assert _names(without) == expected
    assert _names(with_location) == expected