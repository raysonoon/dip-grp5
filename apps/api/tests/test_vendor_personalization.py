from types import SimpleNamespace

import pytest
from sqlalchemy import Column, Integer, MetaData, Table, literal

from app.api.dependencies import get_embedder
from app.main import app
from app.models import User, Vendor


@pytest.fixture
def personalized_catalog(client, session, monkeypatch):
    user = User(
        display_name="Preference User",
        email_address="preferences@test.com",
        email_canonical="preferences@test.com",
        password_hash="test",
        role="user",
    )
    session.add(user)
    vendors = [
        Vendor(name="A Meat", vegetarian=False, halal=False, cuisine="Chinese", location="South Spine"),
        Vendor(name="B Vegetarian", vegetarian=True, halal=False, cuisine="Chinese", location="North Spine"),
        Vendor(name="C Halal", vegetarian=False, halal=True, cuisine="Malay", location="South Spine"),
        Vendor(name="D Both", vegetarian=True, halal=True, cuisine="Malay", location="North Spine"),
        Vendor(name="E Unknown", vegetarian=None, halal=None, cuisine="Chinese", location="North Spine"),
    ]
    session.add_all(vendors)
    session.commit()

    # Exercise the real recommender's SQL filters and scoring on SQLite.
    # Substitute only pgvector storage/distance and the remote embedder:
    # every vendor is indexed with the same qualifying semantic distance.
    embeddings = Table(
        "test_vendor_embeddings",
        MetaData(),
        Column("vendor_id", Integer, primary_key=True),
    )
    embeddings.create(session.connection())
    session.execute(embeddings.insert(), [{"vendor_id": vendor.id} for vendor in vendors])
    session.commit()
    monkeypatch.setattr(
        "app.services.vendor_recommender.VendorEmbedding",
        SimpleNamespace(
            __clause_element__=lambda: embeddings,
            vendor_id=embeddings.c.vendor_id,
            embedding=SimpleNamespace(cosine_distance=lambda vector: literal(0.1)),
        ),
    )
    app.dependency_overrides[get_embedder] = lambda: SimpleNamespace(
        embed=lambda texts: [[1.0, 0.0] for text in texts],
    )
    yield {"Authorization": f"Bearer {user.id}"}
    app.dependency_overrides.pop(get_embedder, None)


def save_preferences(client, headers, **changes):
    payload = {
        "dietary_restrictions": [],
        "cuisines": [],
        "locations": [],
        "likes": ["Vegetables"],
        "dislikes": [],
        "lifestyle": [],
        "onboarding_status": "completed",
        **changes,
    }
    assert client.put("/preferences/me", headers=headers, json=payload).status_code == 200


@pytest.mark.parametrize(
    ("restriction", "names"),
    [
        ("Vegetarian", {"B Vegetarian", "D Both"}),
        ("Vegan", {"B Vegetarian", "D Both"}),
        ("Halal", {"C Halal", "D Both"}),
    ],
)
def test_saved_dietary_preferences_rank_matches_first(
    client, personalized_catalog, restriction, names,
):
    headers = personalized_catalog
    save_preferences(client, headers)
    before = client.get("/vendors", headers=headers).json()
    assert before["total"] == 5

    save_preferences(client, headers, dietary_restrictions=[restriction])
    response = client.get("/vendors?sort=recommended&limit=3", headers=headers)
    assert response.status_code == 200
    page = response.json()
    # All vendors are still returned; dietary matches are ranked first.
    assert page["total"] == 5
    assert {
        item["name"] for item in page["items"][: len(names)]
    } == names
    assert all(
        item["recommended"] for item in page["items"][: len(names)]
    )
    assert not any(
        item["recommended"] for item in page["items"][len(names):]
    )
    remaining = client.get("/vendors?offset=2", headers=headers).json()
    assert remaining["total"] == 5
    assert len(remaining["items"]) == 3
    assert all(not item["recommended"] for item in remaining["items"])


def test_cuisine_location_and_dietary_preferences_combine(client, personalized_catalog):
    save_preferences(
        client, personalized_catalog,
        dietary_restrictions=["Vegetarian", "Halal"],
        cuisines=["Malay"], locations=["North Spine"],
    )
    page = client.get("/vendors", headers=personalized_catalog).json()
    assert [item["name"] for item in page["items"]] == [
        "D Both", "A Meat", "B Vegetarian", "C Halal", "E Unknown",
    ]
    assert page["items"][0]["recommended"] is True
    assert all(not item["recommended"] for item in page["items"][1:])
    assert page["total"] == 5


def test_zero_personalized_matches_fall_back_to_full_catalog(client, personalized_catalog):
    save_preferences(client, personalized_catalog, cuisines=["No matching cuisine"])
    response = client.get("/vendors?limit=3", headers=personalized_catalog)
    assert response.status_code == 200
    page = response.json()
    assert page["total"] == 5
    assert [item["name"] for item in page["items"]] == [
        "A Meat", "B Vegetarian", "C Halal",
    ]
    assert all(not item["recommended"] for item in page["items"])


@pytest.mark.parametrize("error_type", [RuntimeError, ValueError])
def test_personalization_failure_falls_back_to_catalog(
    client, personalized_catalog, monkeypatch, error_type,
):
    save_preferences(client, personalized_catalog)

    def fail(*args, **kwargs):
        raise error_type("embedding unavailable")

    monkeypatch.setattr("app.services.vendor_recommender.VendorRecommender.recommend", fail)
    response = client.get("/vendors", headers=personalized_catalog)
    assert response.status_code == 200
    page = response.json()
    assert page["total"] == 5
    assert all(not item["recommended"] for item in page["items"])


@pytest.mark.parametrize("status", [None, "skipped"])
def test_nonpersonalized_catalog_is_unchanged(client, personalized_catalog, status):
    if status:
        save_preferences(client, personalized_catalog, onboarding_status=status)
    for headers in ({}, personalized_catalog):
        response = client.get("/vendors", headers=headers)
        assert response.status_code == 200
        page = response.json()
        assert page["total"] == 5
        assert [item["name"] for item in page["items"]] == [
            "A Meat", "B Vegetarian", "C Halal", "D Both", "E Unknown",
        ]
        assert all(not item["recommended"] for item in page["items"])


def test_explicit_catalog_sort_and_logged_out_ignore_saved_preferences(client, personalized_catalog):
    save_preferences(client, personalized_catalog, dietary_restrictions=["Vegetarian"])
    for path, headers in (
        ("/vendors", {}),
        ("/vendors?sort=rating", personalized_catalog),
        ("/vendors?sort=reviews", personalized_catalog),
    ):
        response = client.get(path, headers=headers)
        assert response.status_code == 200
        assert response.json()["total"] == 5
        assert all(not item["recommended"] for item in response.json()["items"])
