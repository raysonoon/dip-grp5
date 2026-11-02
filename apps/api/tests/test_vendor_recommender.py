import math

import pytest

from app.models import UserFoodPreferences, Vendor
from app.services.vendor_recommender import (
    MAX_RECOMMENDATIONS,
    VendorRecommender,
    rating_boost,
)


class FakeEmbedder:
    def __init__(self, vectors: dict[str, list[float]]) -> None:
        self.vectors = vectors
        self.calls: list[list[str]] = []

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(texts)
        return [self.vectors[text] for text in texts]


class CachingFakeEmbedder(FakeEmbedder):
    # A real embedder (GoogleEmbedder) exposes cache_key, which enables the
    # content-addressed preference vector cache.
    cache_key = ("test", "vendor-recommender-cache", 2)


def _preferences(
    *,
    dietary_restrictions: list[str] | None = None,
    cuisines: list[str] | None = None,
    locations: list[str] | None = None,
    likes: list[str] | None = None,
    dislikes: list[str] | None = None,
    lifestyle: list[str] | None = None,
) -> UserFoodPreferences:
    return UserFoodPreferences(
        user_id=1,
        dietary_restrictions=dietary_restrictions or [],
        cuisines=cuisines or [],
        locations=locations or [],
        likes=likes or [],
        dislikes=dislikes or [],
        lifestyle=lifestyle or [],
        onboarding_status="completed",
    )


@pytest.mark.parametrize(
    ("rating", "expected"),
    [
        (5.0, 1.15),
        (4.5, 1.05),
        (4.0, 1.00),
        (3.5, 0.85),
        (3.0, 0.50),
        (2.9, None),
    ],
)
def test_rating_boost_uses_required_tiers(
    rating: float,
    expected: float | None,
) -> None:
    vendor = Vendor(
        name="Test Vendor",
        average_rating=rating,
    )

    assert rating_boost(vendor) == expected


def test_rating_boost_uses_google_rating_when_internal_missing() -> None:
    vendor = Vendor(
        name="Test Vendor",
        average_rating=None,
        average_google_rating=4.5,
    )

    assert rating_boost(vendor) == 1.05


def test_rating_boost_is_neutral_when_both_ratings_missing() -> None:
    vendor = Vendor(
        name="Test Vendor",
        average_rating=None,
        average_google_rating=None,
    )

    assert rating_boost(vendor) == 1.00


def test_preference_vector_combines_positive_and_negative_signals() -> None:
    embedder = FakeEmbedder(
        {
            "Likes: spicy food": [1.0, 0.0],
            "Dislikes: sweet food": [0.0, 1.0],
        }
    )

    recommender = VendorRecommender(
        session=None,
        embedder=embedder,
    )

    preferences = _preferences(
        likes=["spicy food"],
        dislikes=["sweet food"],
    )

    vector = recommender._build_preference_vector(preferences)

    expected = 1 / math.sqrt(2)

    assert vector is not None
    assert vector[0] == pytest.approx(expected)
    assert vector[1] == pytest.approx(-expected)


def test_hard_preferences_are_semantic_fallback_when_no_soft_signals() -> None:
    embedder = FakeEmbedder(
        {
            "Preferred cuisine: Japanese": [1.0, 0.0],
        }
    )

    recommender = VendorRecommender(
        session=None,
        embedder=embedder,
    )

    preferences = _preferences(
        cuisines=["Japanese"],
    )

    vector = recommender._build_preference_vector(preferences)

    assert vector == pytest.approx([1.0, 0.0])
    assert embedder.calls == [["Preferred cuisine: Japanese"]]


def test_empty_preferences_have_no_semantic_vector() -> None:
    embedder = FakeEmbedder({})

    recommender = VendorRecommender(
        session=None,
        embedder=embedder,
    )

    vector = recommender._build_preference_vector(_preferences())

    assert vector is None
    assert embedder.calls == []


def test_preference_vector_is_cached_by_preference_content() -> None:
    embedder = CachingFakeEmbedder(
        {
            "Likes: cache probe spicy": [1.0, 0.0],
            "Likes: cache probe sweet": [0.0, 1.0],
        }
    )
    recommender = VendorRecommender(session=None, embedder=embedder)

    first = recommender._build_preference_vector(
        _preferences(likes=["cache probe spicy"])
    )
    second = recommender._build_preference_vector(
        _preferences(likes=["cache probe spicy"])
    )

    assert first == pytest.approx([1.0, 0.0])
    assert second == pytest.approx([1.0, 0.0])
    # Identical preference content is embedded once.
    assert embedder.calls == [["Likes: cache probe spicy"]]

    changed = recommender._build_preference_vector(
        _preferences(likes=["cache probe sweet"])
    )

    assert changed == pytest.approx([0.0, 1.0])
    # Changed content misses the cache and re-embeds.
    assert embedder.calls == [
        ["Likes: cache probe spicy"],
        ["Likes: cache probe sweet"],
    ]


def test_recommendation_limit_is_six() -> None:
    assert MAX_RECOMMENDATIONS == 6