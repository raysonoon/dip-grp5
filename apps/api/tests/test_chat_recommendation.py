"""Preference-aware vendor recommendations in the chatbot."""

import pytest

from app.models import User, UserFoodPreferences, Vendor
from app.services.chat import ChatService
from app.services.embedding import Embedder
from app.services.intent_router import IntentMatch
from app.services.retrieval import FakeKnowledgeStore, KnowledgeResult
from app.services.sql_search import PgSqlStore
from app.services.vendor_recommender import VendorRecommendation

DIMENSION = 768


def _vector(marker: float = 0.1) -> list[float]:
    vector = [0.0] * DIMENSION
    vector[0] = 1.0
    vector[1] = marker
    return vector


class FakeEmbedder(Embedder):
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        return [_vector() for _ in texts]


class StaticRouter:
    def __init__(self, search_type: str) -> None:
        self.search_type = search_type
        self.calls: list[str] = []

    def classify(self, question: str) -> IntentMatch:
        self.calls.append(question)
        return IntentMatch(
            search_type=self.search_type,
            intent_key="test-intent",
            tier=3,
        )


class RecordingRecommender:
    def __init__(
        self,
        recommendations: list[VendorRecommendation] | None = None,
        *,
        error: Exception | None = None,
    ) -> None:
        self.recommendations = recommendations or []
        self.error = error
        self.calls: list[UserFoodPreferences] = []

    def __call__(
        self,
        preferences: UserFoodPreferences,
    ) -> list[VendorRecommendation]:
        self.calls.append(preferences)
        if self.error is not None:
            raise self.error
        return self.recommendations


def _make_user(
    session,
    *,
    email: str = "recommendation@test.com",
    status: str = "completed",
    cuisines: list[str] | None = None,
    likes: list[str] | None = None,
    dietary_restrictions: list[str] | None = None,
    with_preferences: bool = True,
) -> User:
    user = User(
        display_name="Recommendation User",
        email_address=email,
        email_canonical=email,
        password_hash="test",
        role="user",
    )
    session.add(user)
    session.commit()
    session.refresh(user)

    if with_preferences:
        session.add(
            UserFoodPreferences(
                user_id=user.id,
                dietary_restrictions=dietary_restrictions or ["halal"],
                cuisines=cuisines or ["Korean"],
                locations=[],
                likes=likes or ["spicy food"],
                dislikes=[],
                lifestyle=[],
                onboarding_status=status,
            )
        )
        session.commit()

    return user


def _add_vendor(
    session,
    *,
    name: str,
    location: str = "North Spine",
    category: str = "Korean",
    halal: bool = True,
) -> Vendor:
    vendor = Vendor(
        name=name,
        location=location,
        category=category,
        halal=halal,
        price_range="$",
    )
    session.add(vendor)
    session.commit()
    session.refresh(vendor)
    return vendor


def _recommendation(vendor: Vendor) -> VendorRecommendation:
    return VendorRecommendation(
        vendor=vendor,
        similarity=0.9,
        score=1.0,
    )


def _capturing_generate(store: dict[str, str], answer: str):
    def generate(prompt: str) -> str:
        store["prompt"] = prompt
        return answer

    return generate


def test_generic_recommendation_uses_saved_preferences(session) -> None:
    user = _make_user(session)
    vendor = _add_vendor(session, name="Spicy Korean Kitchen")
    recommender = RecordingRecommender([_recommendation(vendor)])
    router = StaticRouter("Vector")
    captured: dict[str, str] = {}

    service = ChatService(
        FakeEmbedder(),
        FakeKnowledgeStore(items=[]),
        generate=_capturing_generate(captured, "Try Spicy Korean Kitchen [1]."),
        router=router,
        sql_store=PgSqlStore(session),
        session=session,
        recommend_fn=recommender,
    )

    response = service.answer("what should I eat?", current_user=user)

    assert response.search_type == "Recommendation"
    assert response.intent == "vendor_recommendation"
    assert [source.vendor_name for source in response.sources] == [
        "Spicy Korean Kitchen"
    ]
    assert response.sources[0].source_type == "vendor"
    assert recommender.calls and recommender.calls[0].user_id == user.id
    assert router.calls == []
    assert "User's saved food preferences:" in captured["prompt"]
    assert "Preferred cuisines: Korean" in captured["prompt"]
    assert "Spicy Korean Kitchen" in captured["prompt"]


def test_generic_recommendation_without_user_falls_back_to_vector(session) -> None:
    recommender = RecordingRecommender()
    router = StaticRouter("Vector")

    service = ChatService(
        FakeEmbedder(),
        FakeKnowledgeStore(items=[]),
        generate=lambda _prompt: "No preferences answer",
        router=router,
        sql_store=PgSqlStore(session),
        session=session,
        recommend_fn=recommender,
    )

    response = service.answer("what should I eat?")

    assert response.search_type == "Vector"
    assert response.answer == "No preferences answer"
    assert "could not identify" not in response.answer
    assert recommender.calls == []
    assert router.calls == ["what should I eat?"]


@pytest.mark.parametrize(
    "question",
    [
        "recommend something for me to eat",
        "recommend me something to eat",
        "recommend something to eat",
        "recommend a place for me to eat",
        "recommend a good place for a date",
        "recommend a quick lunch",
        "recommend something that is not spicy",
        "recommend a place to study at",
        "recommend a place I can study at",
        "recommend another one that's cheaper",
    ],
)
def test_generic_recommendation_phrasing_is_not_a_vendor_clarification(
    session,
    question: str,
) -> None:
    """Signed-out recommendation asks must reach retrieval, not vendor names."""

    recommender = RecordingRecommender()
    router = StaticRouter("Vector")

    service = ChatService(
        FakeEmbedder(),
        FakeKnowledgeStore(items=[]),
        generate=lambda _prompt: "Here is a recommendation.",
        router=router,
        sql_store=PgSqlStore(session),
        session=session,
        recommend_fn=recommender,
    )

    response = service.answer(question)

    assert response.search_type == "Vector"
    assert response.answer == "Here is a recommendation."
    assert "could not identify" not in response.answer
    assert recommender.calls == []
    assert router.calls == [question]


def test_generic_recommendation_with_skipped_preferences_falls_back(
    session,
) -> None:
    user = _make_user(session, status="skipped")
    recommender = RecordingRecommender()
    router = StaticRouter("Vector")

    service = ChatService(
        FakeEmbedder(),
        FakeKnowledgeStore(items=[]),
        generate=lambda _prompt: "Fallback answer",
        router=router,
        sql_store=PgSqlStore(session),
        session=session,
        recommend_fn=recommender,
    )

    response = service.answer("what should I eat?", current_user=user)

    assert response.search_type == "Vector"
    assert response.answer == "Fallback answer"
    assert "could not identify" not in response.answer
    assert recommender.calls == []
    assert router.calls == ["what should I eat?"]


def test_generic_recommendation_without_preferences_row_falls_back(
    session,
) -> None:
    user = _make_user(session, with_preferences=False)
    recommender = RecordingRecommender()
    router = StaticRouter("Vector")

    service = ChatService(
        FakeEmbedder(),
        FakeKnowledgeStore(items=[]),
        generate=lambda _prompt: "Fallback answer",
        router=router,
        sql_store=PgSqlStore(session),
        session=session,
        recommend_fn=recommender,
    )

    response = service.answer("what should I eat?", current_user=user)

    assert response.search_type == "Vector"
    assert response.answer == "Fallback answer"
    assert "could not identify" not in response.answer
    assert recommender.calls == []
    assert router.calls == ["what should I eat?"]


def test_empty_recommendations_fall_back_to_vector(session) -> None:
    user = _make_user(session)
    recommender = RecordingRecommender([])
    router = StaticRouter("Vector")

    service = ChatService(
        FakeEmbedder(),
        FakeKnowledgeStore(items=[]),
        generate=lambda _prompt: "Fallback answer",
        router=router,
        sql_store=PgSqlStore(session),
        session=session,
        recommend_fn=recommender,
    )

    response = service.answer("recommend me something", current_user=user)

    assert response.search_type == "Vector"
    assert response.answer == "Fallback answer"
    assert "could not identify" not in response.answer
    assert recommender.calls
    assert router.calls == ["recommend me something"]


def test_recommender_failure_falls_back_to_vector(session) -> None:
    user = _make_user(session)
    recommender = RecordingRecommender(error=RuntimeError("embedding unavailable"))
    router = StaticRouter("Vector")

    service = ChatService(
        FakeEmbedder(),
        FakeKnowledgeStore(items=[]),
        generate=lambda _prompt: "Fallback answer",
        router=router,
        sql_store=PgSqlStore(session),
        session=session,
        recommend_fn=recommender,
    )

    response = service.answer("what should I eat?", current_user=user)

    assert response.search_type == "Vector"
    assert recommender.calls
    assert router.calls == ["what should I eat?"]


def test_vendor_specific_recommendation_keeps_vector_path(session) -> None:
    user = _make_user(session)
    popeyes = _add_vendor(
        session,
        name="Popeyes",
        category="Western",
        halal=False,
    )
    recommender = RecordingRecommender()
    router = StaticRouter("Vector")
    store = FakeKnowledgeStore(
        items=[
            (
                _vector(),
                KnowledgeResult(
                    source_type="internal_review",
                    source_id="review-popeyes",
                    vendor_id=popeyes.id,
                    content="Students recommend the fried chicken.",
                    metadata={},
                ),
            )
        ],
        vendor_names={popeyes.id: popeyes.name},
    )

    service = ChatService(
        FakeEmbedder(),
        store,
        generate=lambda _prompt: "Students recommend the fried chicken [1].",
        router=router,
        sql_store=PgSqlStore(session),
        session=session,
        recommend_fn=recommender,
    )

    response = service.answer(
        "find recommendations for Popeyes",
        current_user=user,
    )

    assert response.search_type == "Vector"
    assert recommender.calls == []
    assert router.calls == ["find recommendations for Popeyes"]


def test_sql_path_adds_preference_alignment_note(session) -> None:
    user = _make_user(session)
    _add_vendor(session, name="Spicy Korean Kitchen")
    recommender = RecordingRecommender()
    captured: dict[str, str] = {}

    service = ChatService(
        FakeEmbedder(),
        FakeKnowledgeStore(items=[]),
        generate=_capturing_generate(captured, "Try Spicy Korean Kitchen [1]."),
        router=StaticRouter("SQL"),
        sql_store=PgSqlStore(session),
        session=session,
        recommend_fn=recommender,
    )

    response = service.answer("recommend Korean food", current_user=user)

    assert response.search_type == "SQL"
    assert recommender.calls == []
    assert "Personalisation note:" in captured["prompt"]
    assert "Preferred cuisines: Korean" in captured["prompt"]
    assert "Spicy Korean Kitchen" in captured["prompt"]


def test_hybrid_path_adds_preference_alignment_note(session) -> None:
    user = _make_user(session)
    vendor = _add_vendor(session, name="Spicy Korean Kitchen")
    recommender = RecordingRecommender()
    captured: dict[str, str] = {}
    store = FakeKnowledgeStore(
        items=[
            (
                _vector(),
                KnowledgeResult(
                    source_type="internal_review",
                    source_id="review-korean",
                    vendor_id=vendor.id,
                    content="Great Korean fried chicken.",
                    metadata={},
                ),
            )
        ],
        vendor_names={vendor.id: vendor.name},
    )

    service = ChatService(
        FakeEmbedder(),
        store,
        generate=_capturing_generate(captured, "Try Spicy Korean Kitchen [1]."),
        router=StaticRouter("SQL + Vector"),
        sql_store=PgSqlStore(session),
        session=session,
        recommend_fn=recommender,
    )

    response = service.answer(
        "Where can I get Korean food that students recommend?",
        current_user=user,
    )

    assert response.search_type == "SQL + Vector"
    assert recommender.calls == []
    assert "Personalisation note:" in captured["prompt"]
    assert "Preferred cuisines: Korean" in captured["prompt"]


def test_what_food_should_i_eat_uses_preferences_path(session) -> None:
    user = _make_user(session)
    vendor = _add_vendor(session, name="Spicy Korean Kitchen")
    recommender = RecordingRecommender([_recommendation(vendor)])
    router = StaticRouter("Vector")
    captured: dict[str, str] = {}

    service = ChatService(
        FakeEmbedder(),
        FakeKnowledgeStore(items=[]),
        generate=_capturing_generate(captured, "Try Spicy Korean Kitchen [1]."),
        router=router,
        sql_store=PgSqlStore(session),
        session=session,
        recommend_fn=recommender,
    )

    response = service.answer("what food should i eat", current_user=user)

    assert response.search_type == "Recommendation"
    assert recommender.calls
    assert router.calls == []
    assert "Spicy Korean Kitchen" in captured["prompt"]


def test_content_qualified_recommendation_uses_vector_not_preferences(
    session,
) -> None:
    user = _make_user(session)
    vendor = _add_vendor(session, name="Spicy Korean Kitchen")
    recommender = RecordingRecommender([_recommendation(vendor)])
    router = StaticRouter("Vector")
    captured: dict[str, str] = {}

    service = ChatService(
        FakeEmbedder(),
        FakeKnowledgeStore(items=[]),
        generate=_capturing_generate(captured, "Try a salad [1]."),
        router=router,
        sql_store=PgSqlStore(session),
        session=session,
        recommend_fn=recommender,
    )

    response = service.answer(
        "i need a healthy lunch recommendation",
        current_user=user,
    )

    assert response.search_type == "Vector"
    assert response.answer == "Try a salad [1]."
    assert recommender.calls == []
    assert router.calls == ["i need a healthy lunch recommendation"]
    assert "User's saved food preferences:" not in captured["prompt"]


def test_recommendation_detection_requires_generic_ask(session) -> None:
    _add_vendor(session, name="Popeyes", category="Western")
    service = ChatService(
        FakeEmbedder(),
        FakeKnowledgeStore(items=[]),
        generate=lambda _prompt: "answer",
        session=session,
    )

    assert service._is_personal_recommendation_request("what should I eat?")
    assert service._is_personal_recommendation_request("what food should i eat")
    assert service._is_personal_recommendation_request("what can I eat for lunch?")
    assert service._is_personal_recommendation_request(
        "what's a good place to eat?"
    )
    assert service._is_personal_recommendation_request(
        "recommend me something to eat"
    )
    assert service._is_personal_recommendation_request(
        "give me some recommendations"
    )
    assert not service._is_personal_recommendation_request(
        "recommend Korean food"
    )
    assert not service._is_personal_recommendation_request(
        "recommend food near North Spine"
    )
    assert not service._is_personal_recommendation_request(
        "find recommendations for Popeyes"
    )
    assert not service._is_personal_recommendation_request(
        "find recommendations for Popeys"
    )
    assert not service._is_personal_recommendation_request(
        "where is Quad Cafe?"
    )
    assert not service._is_personal_recommendation_request(
        "i need a healthy lunch recommendation"
    )
    assert not service._is_personal_recommendation_request(
        "recommend something healthy"
    )
    assert not service._is_personal_recommendation_request(
        "recommend something filling"
    )
    assert not service._is_personal_recommendation_request(
        "I'm craving something spicy. What should I eat?"
    )
    assert service._is_personal_recommendation_request(
        "what can I eat for lunch?"
    )
