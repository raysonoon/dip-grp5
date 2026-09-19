from datetime import UTC, datetime

from app.services.chat import ChatService, format_sql_context
from app.services.embedding import Embedder
from app.services.intent_router import IntentRouter
from app.services.retrieval import FakeKnowledgeStore, KnowledgeResult
from app.services.sql_search import PgSqlStore, SqlResult
from app.services.structured_filters import (
    StructuredFilter,
    extract_structured_filters,
)

DIMENSION = 768


def _vector(marker: float) -> list[float]:
    vector = [0.0] * DIMENSION
    vector[0] = 1.0
    vector[1] = marker
    return vector


class FakeEmbedder(Embedder):
    def embed(self, texts: list[str]) -> list[list[float]]:
        return [_vector(0.1) for _ in texts]


def _make_router(session):
    return IntentRouter(
        session,
        embedder=FakeEmbedder(),
    )


def _seed_prompt(
    session,
    *,
    intent_key: str,
    question_text: str,
    search_type: str,
) -> None:
    from app.models import ChatbotPrompt

    session.add(
        ChatbotPrompt(
            intent_key=intent_key,
            question_scope="Scope",
            question_text=question_text,
            search_type=search_type,
            source_file="DIP AI chatbot questions.xlsx",
        )
    )
    session.commit()


def test_format_sql_context_lists_attributes() -> None:
    result = SqlResult(
        vendor_id=1,
        vendor_name="Halal Nook",
        location="North Spine",
        category="Korean",
        price_range="$$",
        opening_hours="09:00 - 21:00",
        halal=True,
        vegetarian=False,
        average_google_rating=4.5,
        review_count=3,
    )
    rendered = format_sql_context([result])
    assert "[1] Halal Nook" in rendered
    assert "location=North Spine" in rendered
    assert "rating=4.5" in rendered


def test_format_sql_context_empty() -> None:
    assert format_sql_context([]) == "(no context retrieved)"


def test_format_sql_context_count() -> None:
    rendered = format_sql_context(
        [SqlResult(vendor_id=None, vendor_name=None, count=7)]
    )
    assert "[1] (count): 7" in rendered


def test_router_none_keeps_vector_only_behavior() -> None:
    store = FakeKnowledgeStore(
        items=[
            (
                _vector(0.1),
                KnowledgeResult(
                    source_type="internal_review",
                    source_id="1",
                    vendor_id=1,
                    content="great chicken rice",
                    metadata={},
                ),
            )
        ],
        vendor_names={1: "Demo Vendor 1"},
    )
    captured: dict[str, str] = {}

    def fake_generate(prompt: str) -> str:
        captured["prompt"] = prompt
        return "answer"

    service = ChatService(
        FakeEmbedder(),
        store,
        generate=fake_generate,
    )
    response = service.answer("what is the best food?")
    assert response.search_type == "Vector"
    assert response.intent is None
    assert response.sources[0].source_type == "internal_review"


def test_vector_path_filters_explicit_source_and_vendor_mentions(session) -> None:
    from app.models import Vendor

    nie = Vendor(
        name="NIE Canteen",
        location="NIE",
        category="Food court",
    )
    quad = Vendor(
        name="Quad Cafe",
        location="The Quad",
        category="Food court",
    )
    unrelated = Vendor(
        name="Another Cafe",
        location="North Spine",
        category="Cafe",
    )
    session.add_all([nie, quad, unrelated])
    session.commit()
    store = FakeKnowledgeStore(
        items=[
            (
                _vector(0.8),
                KnowledgeResult(
                    source_type="reddit",
                    source_id="reddit-nie",
                    vendor_id=nie.id,
                    content="NIE canteen has $3 noodles.",
                    metadata={},
                ),
            ),
            (
                _vector(0.7),
                KnowledgeResult(
                    source_type="reddit",
                    source_id="reddit-quad",
                    vendor_id=quad.id,
                    content="Quad Cafe has affordable chicken noodles.",
                    metadata={},
                ),
            ),
            (
                _vector(0.1),
                KnowledgeResult(
                    source_type="google_review",
                    source_id="google-unrelated",
                    vendor_id=unrelated.id,
                    content="Unrelated but more similar result.",
                    metadata={},
                ),
            ),
        ],
        vendor_names={
            nie.id: nie.name,
            quad.id: quad.name,
            unrelated.id: unrelated.name,
        },
    )
    service = ChatService(
        FakeEmbedder(),
        store,
        generate=lambda _prompt: "NIE Canteen [1] and Quad Cafe [2]",
        session=session,
    )

    response = service.answer(
        "What do Reddit users say about noodle options at NIE Canteen "
        "and Quad Cafe?"
    )

    assert [source.source_id for source in response.sources] == [
        "reddit-quad",
        "reddit-nie",
    ]
    assert {source.vendor_name for source in response.sources} == {
        "NIE Canteen",
        "Quad Cafe",
    }


def test_explicit_reddit_vendor_query_reads_comments_without_vector_chunks(
    session,
) -> None:
    from app.models import RedditComment, Vendor

    nie = Vendor(
        name="NIE Canteen",
        location="NIE",
        category="Food court",
    )
    session.add(nie)
    session.flush()
    session.add(
        RedditComment(
            reddit_comment_id="reddit-noodles",
            vendor_id=nie.id,
            subreddit="NTU",
            thread_id="thread-1",
            thread_title="Cheap food",
            comment_text="NIE canteen has $3 noodles.",
            created_at=datetime.now(UTC),
            permalink="/r/NTU/comments/thread-1/comment/reddit-noodles/",
        )
    )
    session.commit()
    store = FakeKnowledgeStore(
        items=[],
        vendor_names={nie.id: nie.name},
    )
    captured: dict[str, str] = {}

    def fake_generate(prompt: str) -> str:
        captured["prompt"] = prompt
        return "NIE Canteen has $3 noodles [1]."

    service = ChatService(
        FakeEmbedder(),
        store,
        generate=fake_generate,
        session=session,
    )

    response = service.answer(
        "What do Reddit users say about noodles at NIE Canteen?"
    )

    assert "NIE canteen has $3 noodles" in captured["prompt"]
    assert [source.source_type for source in response.sources] == ["reddit"]
    assert response.sources[0].vendor_name == "NIE Canteen"
    assert response.sources[0].permalink == (
        "/r/NTU/comments/thread-1/comment/reddit-noodles/"
    )


def test_sql_path_returns_vendor_sources(session) -> None:
    from app.models import Vendor

    session.add(
        Vendor(
            name="Halal Nook",
            location="North Spine",
            category="Korean",
            halal=True,
            vegetarian=False,
        )
    )
    session.commit()
    _seed_prompt(
        session,
        intent_key="Q001",
        question_text="Where can I find halal food?",
        search_type="SQL",
    )

    store = FakeKnowledgeStore(items=[])
    router = _make_router(session)
    sql_store = PgSqlStore(session)

    captured: dict[str, str] = {}

    def fake_generate(prompt: str) -> str:
        captured["prompt"] = prompt
        return "Try Halal Nook."

    service = ChatService(
        FakeEmbedder(),
        store,
        generate=fake_generate,
        router=router,
        sql_store=sql_store,
    )
    response = service.answer("Where can I find halal food?")

    assert response.search_type == "SQL"
    assert response.sources[0].source_type == "vendor"
    assert response.sources[0].vendor_name == "Halal Nook"


def test_empty_sql_list_falls_back_to_vector_for_dish_terms(session) -> None:
    _seed_prompt(
        session,
        intent_key="Q-NOODLE",
        question_text="noodle",
        search_type="SQL",
    )
    store = FakeKnowledgeStore(
        items=[
            (
                _vector(0.1),
                KnowledgeResult(
                    source_type="internal_review",
                    source_id="review-1",
                    vendor_id=4,
                    content="Best noodles on campus, definitely worth trying.",
                    metadata={},
                ),
            )
        ],
        vendor_names={4: "Demo Vendor 2"},
    )
    service = ChatService(
        FakeEmbedder(),
        store,
        generate=lambda _prompt: "Try Demo Vendor 2 [1]",
        router=_make_router(session),
        sql_store=PgSqlStore(session),
        filter_extractor_llm=lambda _question: StructuredFilter(
            cuisine="Noodle"
        ),
    )

    response = service.answer("noodle")

    assert response.search_type == "Vector"
    assert response.answer == "Try Demo Vendor 2 [1]"
    assert [source.vendor_name for source in response.sources] == [
        "Demo Vendor 2"
    ]


def test_hybrid_path_filters_vector_results(session) -> None:
    from app.models import Vendor

    session.add(
        Vendor(
            name="Halal Nook",
            location="North Spine",
            category="Korean",
            halal=True,
        )
    )
    session.commit()
    _seed_prompt(
        session,
        intent_key="Q039",
        question_text="Where can I get halal food that students recommend?",
        search_type="SQL + Vector",
    )

    store = FakeKnowledgeStore(
        items=[
            (
                _vector(0.9),
                KnowledgeResult(
                    source_type="internal_review",
                    source_id="1",
                    vendor_id=1,
                    content="great halal food",
                    metadata={},
                ),
            ),
            (
                _vector(0.1),
                KnowledgeResult(
                    source_type="internal_review",
                    source_id="2",
                    vendor_id=999,
                    content="other content",
                    metadata={},
                ),
            ),
        ],
        vendor_names={1: "Halal Nook"},
    )
    router = _make_router(session)
    sql_store = PgSqlStore(session)

    def fake_generate(prompt: str) -> str:
        return "Halal Nook is a good pick."

    service = ChatService(
        FakeEmbedder(),
        store,
        generate=fake_generate,
        router=router,
        sql_store=sql_store,
    )
    response = service.answer("halal food that students recommend")

    assert response.search_type == "SQL + Vector"
    assert [s.vendor_id for s in response.sources] == [1]
    assert response.sources[0].vendor_name == "Halal Nook"


def test_hybrid_filters_applied_by_fake_store() -> None:
    store = FakeKnowledgeStore(
        items=[
            (
                _vector(0.9),
                KnowledgeResult(
                    source_type="internal_review",
                    source_id="1",
                    vendor_id=1,
                    content="a",
                    metadata={},
                ),
            ),
            (
                _vector(0.1),
                KnowledgeResult(
                    source_type="internal_review",
                    source_id="2",
                    vendor_id=2,
                    content="b",
                    metadata={},
                ),
            ),
        ]
    )
    results = store.search(
        _vector(0.1),
        limit=5,
        filters={"vendor_ids": [2]},
    )
    assert [r.source_id for r in results] == ["2"]


def test_hybrid_filters_source_type() -> None:
    store = FakeKnowledgeStore(
        items=[
            (
                _vector(0.1),
                KnowledgeResult(
                    source_type="internal_review",
                    source_id="1",
                    vendor_id=1,
                    content="a",
                    metadata={},
                ),
            ),
            (
                _vector(0.9),
                KnowledgeResult(
                    source_type="google_review",
                    source_id="g1",
                    vendor_id=1,
                    content="b",
                    metadata={},
                ),
            ),
        ]
    )
    results = store.search(
        _vector(0.1),
        limit=5,
        filters={"source_type": "internal_review"},
    )
    assert [r.source_id for r in results] == ["1"]
