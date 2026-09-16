from app.services.chat import ChatService, format_sql_context
from app.services.embedding import Embedder
from app.services.intent_router import IntentRouter
from app.services.retrieval import FakeKnowledgeStore, KnowledgeResult
from app.services.sql_search import PgSqlStore, SqlResult
from app.services.structured_filters import extract_structured_filters

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