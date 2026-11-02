import math
from collections import OrderedDict
from dataclasses import dataclass
from threading import Lock

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.models import UserFoodPreferences, Vendor
from app.models.vendor_embedding import VendorEmbedding
from app.services.embedding import Embedder


COSINE_RELEVANCE_FLOOR = 0.5
MAX_RECOMMENDATIONS = 6

_PREFERENCE_VECTOR_CACHE_LIMIT = 256
_preference_vector_cache: "OrderedDict[tuple, list[float] | None]" = OrderedDict()
_preference_vector_cache_lock = Lock()


def _preference_vector_cache_key(
    embedder: Embedder,
    preferences: UserFoodPreferences,
) -> tuple | None:
    """Return a content-addressed cache key, or None when uncacheable.

    Embedders without a ``cache_key`` (e.g. test doubles) are not cached, so
    unrelated instances can never accidentally share an entry.
    """
    embedder_key = getattr(embedder, "cache_key", None)
    if embedder_key is None:
        return None

    return (
        embedder_key,
        tuple(sorted(preferences.likes or [])),
        tuple(sorted(preferences.lifestyle or [])),
        tuple(sorted(preferences.dislikes or [])),
        tuple(sorted(preferences.cuisines or [])),
        tuple(sorted(preferences.locations or [])),
        tuple(sorted(preferences.dietary_restrictions or [])),
    )


@dataclass
class VendorRecommendation:
    """A vendor ranked against the user's saved food preferences."""

    vendor: Vendor
    similarity: float
    score: float


class VendorRecommender:
    """Rank vendors using semantic preferences and rating quality."""

    def __init__(
        self,
        session: Session,
        embedder: Embedder,
    ) -> None:
        self._session = session
        self._embedder = embedder

    def recommend(
        self,
        preferences: UserFoodPreferences,
        *,
        limit: int = MAX_RECOMMENDATIONS,
    ) -> list[VendorRecommendation]:
        limit = min(max(limit, 0), MAX_RECOMMENDATIONS)

        if limit == 0:
            return []

        query_vector = self._build_preference_vector(preferences)

        if query_vector is None:
            return []

        distance = VendorEmbedding.embedding.cosine_distance(query_vector)

        statement = (
            select(Vendor, distance.label("distance"))
            .join(
                VendorEmbedding,
                VendorEmbedding.vendor_id == Vendor.id,
            )
        )

        # Hard filter: Halal dietary restriction -> vendors.halal = true.
        dietary_restrictions = {
            value.strip().casefold()
            for value in (preferences.dietary_restrictions or [])
            if value.strip()
        }

        if "halal" in dietary_restrictions:
            statement = statement.where(Vendor.halal.is_(True))

        if (
            "vegetarian" in dietary_restrictions
            or "vegan" in dietary_restrictions
        ):
            statement = statement.where(
                Vendor.vegetarian.is_(True)
            )

        # Hard filter: selected cuisines -> vendor cuisine (falling back to
        # the establishment category for vendors without a cuisine).
        cuisines = [
            value.strip()
            for value in (preferences.cuisines or [])
            if value.strip()
        ]

        if cuisines:
            statement = statement.where(
                or_(
                    *[
                        or_(
                            Vendor.cuisine.ilike(f"%{cuisine}%"),
                            Vendor.category.ilike(f"%{cuisine}%"),
                        )
                        for cuisine in cuisines
                    ]
                )
            )

        # Hard filter: selected locations -> vendor location.
        locations = [
            value.strip()
            for value in (preferences.locations or [])
            if value.strip()
        ]

        if locations:
            statement = statement.where(
                or_(
                    *[
                        Vendor.location.ilike(f"%{location}%")
                        for location in locations
                    ]
                )
            )

        # Vendors with an explicit rating below 3.0 are excluded.
        statement = statement.where(
            or_(
                Vendor.average_rating >= 3.0,
                and_(
                    Vendor.average_rating.is_(None),
                    Vendor.average_google_rating >= 3.0,
                ),
            and_(
                Vendor.average_rating.is_(None),
                Vendor.average_google_rating.is_(None),
            ),
        )
    )

        # cosine similarity >= 0.5 means cosine distance <= 0.5.
        statement = (
            statement
            .where(distance <= 1.0 - COSINE_RELEVANCE_FLOOR)
            .order_by(distance)
        )

        rows = self._session.execute(statement).all()

        recommendations: list[VendorRecommendation] = []

        for vendor, cosine_distance in rows:
            similarity = 1.0 - float(cosine_distance)

            boost = rating_boost(vendor)

            if boost is None:
                continue

            recommendations.append(
                VendorRecommendation(
                    vendor=vendor,
                    similarity=similarity,
                    score=similarity * boost,
                )
            )

        recommendations.sort(
            key=lambda recommendation: (
                recommendation.score,
                recommendation.similarity,
            ),
            reverse=True,
        )

        return recommendations[:limit]

    def _build_preference_vector(
        self,
        preferences: UserFoodPreferences,
    ) -> list[float] | None:
        """Return the preference query vector, reusing cached work.

        The embedding call is the expensive, rate-limited step, so a vector is
        reused while the preference content and embedder stay the same.
        """
        cache_key = _preference_vector_cache_key(self._embedder, preferences)

        if cache_key is not None:
            with _preference_vector_cache_lock:
                if cache_key in _preference_vector_cache:
                    _preference_vector_cache.move_to_end(cache_key)
                    return _preference_vector_cache[cache_key]

        # Compute outside the lock so a slow embedding call does not block
        # other users. Concurrent misses may duplicate the call, which is safe.
        vector = self._compute_preference_vector(preferences)

        if cache_key is not None:
            with _preference_vector_cache_lock:
                _preference_vector_cache[cache_key] = vector
                _preference_vector_cache.move_to_end(cache_key)
                while (
                    len(_preference_vector_cache)
                    > _PREFERENCE_VECTOR_CACHE_LIMIT
                ):
                    _preference_vector_cache.popitem(last=False)

        return vector

    def _compute_preference_vector(
        self,
        preferences: UserFoodPreferences,
    ) -> list[float] | None:
        """Build one semantic vector from soft user preference signals.

        Likes and lifestyle preferences pull recommendations closer.
        Dislikes push the query vector away from matching concepts.
        """

        positive_texts = [
            *(f"Likes: {value}" for value in preferences.likes or []),
            *(
                f"Lifestyle preference: {value}"
                for value in preferences.lifestyle or []
            ),
        ]

        negative_texts = [
            f"Dislikes: {value}"
            for value in preferences.dislikes or []
        ]

        positive_texts = [
            text for text in positive_texts if text.split(":", 1)[1].strip()
        ]
        negative_texts = [
            text for text in negative_texts if text.split(":", 1)[1].strip()
        ]

        # If there are no soft signals, use the hard preferences as semantic
        # context as a fallback so users with saved preferences can still
        # receive personalised recommendations.
        if not positive_texts and not negative_texts:
            positive_texts = [
                *(
                    f"Preferred cuisine: {value}"
                    for value in preferences.cuisines or []
                    if value.strip()
                ),
                *(
                    f"Preferred location: {value}"
                    for value in preferences.locations or []
                    if value.strip()
                ),
                *(
                    f"Dietary restriction: {value}"
                    for value in preferences.dietary_restrictions or []
                    if value.strip()
                ),
            ]

        all_texts = positive_texts + negative_texts

        if not all_texts:
            return None

        vectors = self._embedder.embed(all_texts)

        positive_vectors = vectors[: len(positive_texts)]
        negative_vectors = vectors[len(positive_texts) :]

        dimensions = len(vectors[0])

        query_vector = [0.0] * dimensions

        if positive_vectors:
            for vector in positive_vectors:
                for index, value in enumerate(vector):
                    query_vector[index] += value / len(positive_vectors)

        if negative_vectors:
            for vector in negative_vectors:
                for index, value in enumerate(vector):
                    query_vector[index] -= value / len(negative_vectors)

        magnitude = math.sqrt(
            sum(value * value for value in query_vector)
        )

        if magnitude == 0.0:
            return None

        return [
            value / magnitude
            for value in query_vector
        ]


def rating_boost(vendor: Vendor) -> float | None:
    """Return the exact rating tier multiplier required by DIP-94.

    ``None`` means the vendor must be excluded.
    """

    rating = (
        vendor.average_rating
        if vendor.average_rating is not None
        else vendor.average_google_rating
    )

    # No rating from either source is neutral.
    if rating is None:
        return 1.00

    rating = float(rating)

    if rating >= 5.0:
        return 1.15

    if rating >= 4.5:
        return 1.05

    if rating >= 4.0:
        return 1.00

    if rating >= 3.5:
        return 0.85

    if rating >= 3.0:
        return 0.50

    return None