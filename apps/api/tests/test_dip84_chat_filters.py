from copy import deepcopy

import pytest

from app.models import Vendor
from app.schemas.chat import ChatHistoryMessage
from app.services.chat import ChatService
from app.services.embedding import Embedder
from app.services.intent_router import IntentMatch
from app.services.retrieval import KnowledgeResult
from app.services.sql_search import PgSqlStore, SqlResult
from app.services.structured_filters import (
    CUISINE_KEYWORDS,
    StructuredFilter,
    extract_structured_filters,
)


class NeverEmbedder(Embedder):
    """Fail loudly if a DIP-84 SQL/clarification path embeds the question."""

    def embed(self, _texts: list[str]) -> list[list[float]]:
        raise AssertionError("DIP-84 vendor lookup must not use vector embeddings")


class LocalEmbedder(Embedder):
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        return [[1.0, 0.0] for _ in texts]


class StaticRouter:
    def __init__(self, search_type: str) -> None:
        self.search_type = search_type
        self.calls: list[str] = []

    def classify(self, question: str) -> IntentMatch:
        self.calls.append(question)
        return IntentMatch(
            search_type=self.search_type,
            intent_key="dip-84-test",
            tier=3,
        )


class MatchRouter:
    def __init__(self, match: IntentMatch) -> None:
        self.match = match
        self.calls: list[str] = []

    def classify(self, question: str) -> IntentMatch:
        self.calls.append(question)
        return self.match


class CapturingMatchChatService(ChatService):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.sql_match: IntentMatch | None = None

    def _prepare_sql(self, question, match, history, retrieval_question, **kwargs):
        self.sql_match = match
        return super()._prepare_sql(
            question,
            match,
            history,
            retrieval_question,
            **kwargs,
        )


class NeverKnowledgeStore:
    """A vector store that makes an accidental broad fallback observable."""

    def __init__(self) -> None:
        self.search_calls = 0

    def search(self, *_args, **_kwargs):
        self.search_calls += 1
        raise AssertionError("DIP-84 flow must not run a broad vector search")

    def resolve_vendor_names(self, _vendor_ids: set[int]) -> dict[int, str]:
        raise AssertionError("DIP-84 flow must not resolve vector sources")


class EvidenceKnowledgeStore:
    def __init__(self, result: KnowledgeResult, vendor_name: str) -> None:
        self.result = result
        self.vendor_name = vendor_name
        self.search_calls: list[dict | None] = []

    def search(
        self,
        _query_vector: list[float],
        *,
        limit: int,
        filters: dict | None = None,
    ) -> list[KnowledgeResult]:
        assert limit > 0
        self.search_calls.append(deepcopy(filters))
        return [self.result]

    def resolve_vendor_names(self, vendor_ids: set[int]) -> dict[int, str]:
        if self.result.vendor_id in vendor_ids:
            return {self.result.vendor_id: self.vendor_name}
        return {}


class EmptyKnowledgeStore:
    """Record harmless Vector calls used by non-clarification follow-ups."""

    def __init__(self) -> None:
        self.search_calls: list[dict | None] = []

    def search(
        self,
        _query_vector: list[float],
        *,
        limit: int,
        filters: dict | None = None,
    ) -> list[KnowledgeResult]:
        assert limit > 0
        self.search_calls.append(deepcopy(filters))
        return []

    def resolve_vendor_names(self, _vendor_ids: set[int]) -> dict[int, str]:
        return {}


class RecordingSqlStore:
    def __init__(self, delegate: PgSqlStore) -> None:
        self.delegate = delegate
        self.search_calls: list[StructuredFilter] = []

    def search(self, filters: StructuredFilter) -> list[SqlResult]:
        self.search_calls.append(deepcopy(filters))
        return self.delegate.search(filters)

    def resolve_vendor_ids(self, filters: StructuredFilter) -> list[int]:
        return self.delegate.resolve_vendor_ids(filters)


class NeverSqlStore:
    def search(self, _filters: StructuredFilter) -> list[SqlResult]:
        raise AssertionError("an unresolved vendor must be clarified before SQL")

    def resolve_vendor_ids(self, _filters: StructuredFilter) -> list[int]:
        raise AssertionError("an unresolved vendor must be clarified before SQL")


class ConstrainedEmptySqlStore:
    """Return no rows, but reject any accidental full-table SQL lookup."""

    def __init__(self) -> None:
        self.search_calls: list[StructuredFilter] = []

    def search(self, filters: StructuredFilter) -> list[SqlResult]:
        self.search_calls.append(deepcopy(filters))
        if not filters.has_constraints:
            raise AssertionError("an empty LLM result must not run unfiltered SQL")
        return []

    def resolve_vendor_ids(self, _filters: StructuredFilter) -> list[int]:
        raise AssertionError("this SQL-only scenario must not resolve hybrid IDs")


class ScriptedSqlStore:
    def __init__(self, responses: list[list[SqlResult]]) -> None:
        self.responses = list(responses)
        self.search_calls: list[StructuredFilter] = []

    def search(self, filters: StructuredFilter) -> list[SqlResult]:
        self.search_calls.append(deepcopy(filters))
        if not self.responses:
            raise AssertionError("SQL retried more than once")
        return self.responses.pop(0)

    def resolve_vendor_ids(self, _filters: StructuredFilter) -> list[int]:
        raise AssertionError("this SQL-only scenario must not resolve hybrid IDs")


def _add_vendor(
    session,
    *,
    name: str,
    location: str,
    category: str = "Fast Food/Takeout",
) -> Vendor:
    vendor = Vendor(name=name, location=location, category=category)
    session.add(vendor)
    session.flush()
    return vendor


def _generated_answer(prompt: str) -> str:
    """Keep answer generation local while proving SQL context was supplied."""

    assert "Context:" in prompt
    return "Answer generated from SQL context."


def _never_generate(_prompt: str) -> str:
    raise AssertionError("a direct clarification must not invoke answer generation")


def _never_stream(_prompt: str):
    raise AssertionError("a direct clarification must not invoke stream generation")
    yield "unreachable"


def test_three_vendor_aliases_and_accents_are_resolved_together(session) -> None:
    gelare = _add_vendor(
        session,
        name="Geláre",
        location="North Spine Plaza",
        category="Desserts",
    )
    encik_tan = _add_vendor(
        session,
        name="Encik Tan",
        location="North Spine Food Court",
        category="Local",
    )
    blue_ocean = _add_vendor(
        session,
        name="Blue Ocean Kopi & Toast",
        location="South Spine",
        category="Cafe",
    )
    _add_vendor(session, name="Unrelated Cafe", location="Hall 1")
    session.commit()

    sql_store = RecordingSqlStore(PgSqlStore(session))
    service = ChatService(
        NeverEmbedder(),
        NeverKnowledgeStore(),
        generate=_generated_answer,
        router=StaticRouter("SQL"),
        sql_store=sql_store,
        session=session,
    )

    response = service.answer("where is gelare, encik tan and blue ocean?")

    expected_ids = {gelare.id, encik_tan.id, blue_ocean.id}
    assert response.search_type == "SQL"
    assert {source.vendor_id for source in response.sources} == expected_ids
    assert {source.vendor_name for source in response.sources} == {
        "Geláre",
        "Encik Tan",
        "Blue Ocean Kopi & Toast",
    }
    assert len(sql_store.search_calls) == 1
    assert set(sql_store.search_calls[0].vendor_ids or []) == expected_ids
    assert sql_store.search_calls[0].cuisine is None


def test_known_vendor_location_query_overrides_vector_router(session) -> None:
    popeyes = _add_vendor(session, name="Popeyes", location="North Spine")
    session.commit()

    router = StaticRouter("Vector")
    vector_store = NeverKnowledgeStore()
    sql_store = RecordingSqlStore(PgSqlStore(session))
    service = ChatService(
        NeverEmbedder(),
        vector_store,
        generate=_generated_answer,
        router=router,
        sql_store=sql_store,
        session=session,
    )

    response = service.answer("where is Popeyes?")

    assert router.calls == ["where is Popeyes?"]
    assert response.search_type == "SQL"
    assert [source.vendor_id for source in response.sources] == [popeyes.id]
    assert len(sql_store.search_calls) == 1
    assert sql_store.search_calls[0].vendor_ids == [popeyes.id]
    assert vector_store.search_calls == 0


def test_empty_sql_uses_one_llm_filter_retry_and_reruns_sql(session) -> None:
    popeyes = _add_vendor(session, name="Popeyes", location="North Spine")
    subway = _add_vendor(session, name="Subway", location="South Spine")
    session.commit()

    llm_calls: list[str] = []

    def corrected_filters(question: str) -> StructuredFilter:
        llm_calls.append(question)
        return StructuredFilter(
            vendor_names=["Subway"],
            cuisine="Subway",
            location="North Spine",
            budget="cheap",
            query_kind="count",
        )

    sql_store = ScriptedSqlStore([[], []])
    service = ChatService(
        NeverEmbedder(),
        NeverKnowledgeStore(),
        generate=_generated_answer,
        router=StaticRouter("SQL"),
        sql_store=sql_store,
        filter_extractor_llm=corrected_filters,
        session=session,
    )

    response = service.answer("where is Popeyes at the library?")

    assert llm_calls == ["where is Popeyes at the library?"]
    assert len(sql_store.search_calls) == 2
    first_filters, retry_filters = sql_store.search_calls
    assert first_filters.vendor_ids == [popeyes.id]
    assert first_filters.location == "Library"
    assert retry_filters.vendor_ids == [popeyes.id]
    assert retry_filters.vendor_names is None
    assert subway.id not in (retry_filters.vendor_ids or [])
    assert retry_filters.location == "Library"
    assert retry_filters.budget == "cheap"
    assert retry_filters.cuisine is None
    assert retry_filters.query_kind == "list"
    assert response.search_type == "SQL"
    assert response.sources == []
    assert "couldn't find" in response.answer


def test_misspelled_vendor_returns_direct_clarification_without_vector(
    session,
) -> None:
    _add_vendor(session, name="Popeyes", location="North Spine")
    session.commit()

    llm_calls: list[str] = []

    def unresolved_filters(question: str) -> StructuredFilter:
        llm_calls.append(question)
        return StructuredFilter(vendor_names=["Popeys"])

    vector_store = NeverKnowledgeStore()
    service = ChatService(
        NeverEmbedder(),
        vector_store,
        generate=_never_generate,
        router=StaticRouter("SQL"),
        sql_store=NeverSqlStore(),
        filter_extractor_llm=unresolved_filters,
        session=session,
    )

    response = service.answer("where is Popeys?")

    assert llm_calls == ["where is Popeys?"]
    assert "Do you mean" in response.answer
    assert "Popeyes" in response.answer
    assert response.search_type == "SQL"
    assert response.sources == []
    assert vector_store.search_calls == 0


def test_popeyes_is_sent_to_sql_as_vendor_not_cuisine(session) -> None:
    popeyes = _add_vendor(session, name="Popeyes", location="North Spine")
    _add_vendor(
        session,
        name="Seoul Kitchen",
        location="South Spine",
        category="Korean",
    )
    session.commit()

    sql_store = RecordingSqlStore(PgSqlStore(session))
    service = ChatService(
        NeverEmbedder(),
        NeverKnowledgeStore(),
        generate=_generated_answer,
        router=StaticRouter("SQL"),
        sql_store=sql_store,
        session=session,
    )

    response = service.answer("where is Popeyes in NTU?")

    filters = sql_store.search_calls[0]
    assert filters.vendor_ids == [popeyes.id]
    assert filters.vendor_names is None
    assert filters.cuisine is None
    assert [source.vendor_name for source in response.sources] == ["Popeyes"]


def test_real_cuisine_is_preserved_as_cuisine_filter(session) -> None:
    korean = _add_vendor(
        session,
        name="Seoul Kitchen",
        location="North Spine",
        category="Korean",
    )
    _add_vendor(
        session,
        name="Popeyes",
        location="North Spine",
        category="Fast Food/Takeout",
    )
    session.commit()

    sql_store = RecordingSqlStore(PgSqlStore(session))
    service = ChatService(
        NeverEmbedder(),
        NeverKnowledgeStore(),
        generate=_generated_answer,
        router=StaticRouter("SQL"),
        sql_store=sql_store,
        session=session,
    )

    response = service.answer("where can I find Korean food?")

    filters = sql_store.search_calls[0]
    assert filters.cuisine == "Korean"
    assert filters.vendor_ids is None
    assert filters.vendor_names is None
    assert [source.vendor_id for source in response.sources] == [korean.id]


def test_stream_answer_emits_direct_clarification_and_empty_sources(
    session,
) -> None:
    _add_vendor(session, name="Popeyes", location="North Spine")
    session.commit()

    vector_store = NeverKnowledgeStore()
    service = ChatService(
        NeverEmbedder(),
        vector_store,
        generate=_never_generate,
        generate_stream=_never_stream,
        router=StaticRouter("SQL"),
        sql_store=NeverSqlStore(),
        filter_extractor_llm=lambda _question: StructuredFilter(
            vendor_names=["Popeys"]
        ),
        session=session,
    )

    events = list(service.stream_answer("where is Popeys?"))

    assert len(events) == 2
    assert events[0][0] == "delta"
    assert isinstance(events[0][1], str)
    assert "Do you mean" in events[0][1]
    assert "Popeyes" in events[0][1]
    assert events[1] == ("sources", [])
    assert vector_store.search_calls == 0


def test_lookup_with_empty_initial_llm_filters_clarifies_without_search(
    session,
) -> None:
    _add_vendor(session, name="Popeyes", location="North Spine")
    session.commit()

    llm_calls: list[str] = []

    def empty_filters(question: str) -> StructuredFilter:
        llm_calls.append(question)
        return StructuredFilter()

    vector_store = NeverKnowledgeStore()
    service = ChatService(
        NeverEmbedder(),
        vector_store,
        generate=_never_generate,
        router=StaticRouter("SQL"),
        sql_store=NeverSqlStore(),
        filter_extractor_llm=empty_filters,
        session=session,
    )

    response = service.answer("where is Mystery Stall?")

    assert llm_calls == ["where is Mystery Stall?"]
    assert "Do you mean" in response.answer
    assert response.search_type == "SQL"
    assert response.sources == []
    assert vector_store.search_calls == 0


def test_empty_llm_retry_never_runs_second_unfiltered_sql_or_vector(
    session,
) -> None:
    _add_vendor(
        session,
        name="Seoul Kitchen",
        location="North Spine",
        category="Japanese",
    )
    session.commit()

    llm_calls: list[str] = []

    def empty_retry(question: str) -> StructuredFilter:
        llm_calls.append(question)
        return StructuredFilter()

    sql_store = ConstrainedEmptySqlStore()
    vector_store = NeverKnowledgeStore()
    service = ChatService(
        NeverEmbedder(),
        vector_store,
        generate=lambda _prompt: "No matching vendors found.",
        router=StaticRouter("SQL"),
        sql_store=sql_store,
        filter_extractor_llm=empty_retry,
        session=session,
    )

    response = service.answer("where can I find Korean food?")

    assert llm_calls == ["where can I find Korean food?"]
    assert len(sql_store.search_calls) == 1
    assert sql_store.search_calls[0].cuisine == "Korean"
    assert response.search_type == "SQL"
    assert response.sources == []
    assert vector_store.search_calls == 0


@pytest.mark.parametrize(
    (
        "question",
        "scope_field",
        "scope_value",
        "supplemental_field",
        "supplemental_value",
    ),
    [
        ("show me Korean food", "cuisine", "Korean", "location", "South Spine"),
        (
            "show me food in North Spine",
            "location",
            "North Spine",
            "budget",
            "cheap",
        ),
        ("show me halal food", "halal", True, "location", "South Spine"),
        (
            "show me vegetarian food",
            "vegetarian",
            True,
            "location",
            "South Spine",
        ),
        ("show me cheap food", "budget", "cheap", "location", "South Spine"),
        (
            "show me places open on Sunday",
            "open_hours",
            "sunday",
            "location",
            "South Spine",
        ),
        (
            "show me not Indian food",
            "exclude_cuisine",
            "Indian",
            "location",
            "South Spine",
        ),
        (
            "show me food not near Hall 14",
            "exclude_location",
            "Hall 14",
            "budget",
            "cheap",
        ),
        (
            "show me not expensive food",
            "exclude_budget",
            "expensive",
            "location",
            "South Spine",
        ),
        (
            "show me places not open on Sunday",
            "exclude_open_hours",
            "sunday",
            "location",
            "South Spine",
        ),
    ],
)
def test_scoped_sql_zero_after_safe_retry_never_uses_vector(
    session,
    question: str,
    scope_field: str,
    scope_value: object,
    supplemental_field: str,
    supplemental_value: object,
) -> None:
    llm_calls: list[str] = []

    def supplemental_filters(value: str) -> StructuredFilter:
        llm_calls.append(value)
        return StructuredFilter(**{supplemental_field: supplemental_value})

    sql_store = ScriptedSqlStore([[], []])
    vector_store = NeverKnowledgeStore()
    service = ChatService(
        NeverEmbedder(),
        vector_store,
        generate=_never_generate,
        router=StaticRouter("SQL"),
        sql_store=sql_store,
        filter_extractor_llm=supplemental_filters,
        session=session,
    )

    response = service.answer(question)

    assert llm_calls == [question]
    assert len(sql_store.search_calls) == 2
    initial, retry = sql_store.search_calls
    assert getattr(initial, scope_field) == scope_value
    assert getattr(retry, scope_field) == scope_value
    assert getattr(retry, supplemental_field) == supplemental_value
    assert response.search_type == "SQL"
    assert response.sources == []
    assert "couldn't find" in response.answer
    assert vector_store.search_calls == 0


def test_unknown_vendor_or_cuisine_without_suggestion_never_uses_vector(
    session,
) -> None:
    _add_vendor(session, name="Popeyes", location="North Spine")
    session.commit()

    llm_calls: list[str] = []

    def unknown_filters(question: str) -> StructuredFilter:
        llm_calls.append(question)
        return StructuredFilter(cuisine="ZXQ Mystery Cuisine")

    sql_store = ConstrainedEmptySqlStore()
    vector_store = NeverKnowledgeStore()
    service = ChatService(
        NeverEmbedder(),
        vector_store,
        generate=lambda _prompt: "No matching vendors found.",
        router=StaticRouter("SQL"),
        sql_store=sql_store,
        filter_extractor_llm=unknown_filters,
        session=session,
    )

    response = service.answer("where is ZXQ Mystery Cuisine?")

    assert llm_calls == ["where is ZXQ Mystery Cuisine?"]
    assert sql_store.search_calls == []
    assert "ZXQ Mystery Cuisine" in response.answer
    assert "clarify" in response.answer.casefold()
    assert response.search_type == "SQL"
    assert response.sources == []
    assert vector_store.search_calls == 0


def test_forced_sql_preserves_all_router_match_metadata(session) -> None:
    popeyes = _add_vendor(session, name="Popeyes", location="North Spine")
    session.commit()

    template = "ROUTED TEMPLATE\nQuestion={user_question}\nContext={context}"
    original_match = IntentMatch(
        search_type="Vector",
        intent_key="vendor-location-intent",
        question_scope="Vendor location lookup",
        prompt_template=template,
        tier=2,
        similarity=0.97,
        query_vector=[0.2, 0.3],
    )
    router = MatchRouter(original_match)
    captured_prompts: list[str] = []
    service = CapturingMatchChatService(
        NeverEmbedder(),
        NeverKnowledgeStore(),
        generate=lambda prompt: captured_prompts.append(prompt) or "North Spine.",
        router=router,
        sql_store=PgSqlStore(session),
        session=session,
    )

    response = service.answer("where is Popeyes?")

    assert response.search_type == "SQL"
    assert response.intent == "vendor-location-intent"
    assert [source.vendor_id for source in response.sources] == [popeyes.id]
    assert captured_prompts and captured_prompts[0].startswith("ROUTED TEMPLATE")
    assert service.sql_match is not None
    assert service.sql_match.search_type == "SQL"
    assert service.sql_match.intent_key == original_match.intent_key
    assert service.sql_match.question_scope == original_match.question_scope
    assert service.sql_match.prompt_template == original_match.prompt_template
    # The override itself is a deterministic tier-1 decision; every piece of
    # router-provided intent/prompt/evidence metadata must otherwise survive.
    assert service.sql_match.tier == 1
    assert service.sql_match.similarity == original_match.similarity
    assert service.sql_match.query_vector == original_match.query_vector


def test_hybrid_typo_clarifies_before_resolving_or_searching_all_vendors(
    session,
) -> None:
    _add_vendor(session, name="Popeyes", location="North Spine")
    session.commit()

    llm_calls: list[str] = []

    def typo_filters(question: str) -> StructuredFilter:
        llm_calls.append(question)
        return StructuredFilter(vendor_names=["Popeys"])

    vector_store = NeverKnowledgeStore()
    service = ChatService(
        NeverEmbedder(),
        vector_store,
        generate=_never_generate,
        router=StaticRouter("SQL + Vector"),
        sql_store=NeverSqlStore(),
        filter_extractor_llm=typo_filters,
        session=session,
    )

    response = service.answer("what do people recommend at Popeys?")

    assert llm_calls == ["what do people recommend at Popeys?"]
    assert "Do you mean" in response.answer
    assert "Popeyes" in response.answer
    assert response.sources == []
    assert vector_store.search_calls == 0


def test_hybrid_partial_known_and_unknown_vendors_joined_by_or_clarifies(
    session,
) -> None:
    _add_vendor(session, name="Popeyes", location="North Spine")
    session.commit()

    llm_calls: list[str] = []

    def partial_filters(question: str) -> StructuredFilter:
        llm_calls.append(question)
        return StructuredFilter(vendor_names=["Popeyes", "Mystery Stall"])

    vector_store = NeverKnowledgeStore()
    service = ChatService(
        NeverEmbedder(),
        vector_store,
        generate=_never_generate,
        router=StaticRouter("SQL + Vector"),
        sql_store=NeverSqlStore(),
        filter_extractor_llm=partial_filters,
        session=session,
    )

    question = "what do people recommend at Popeyes or Mystery Stall?"
    response = service.answer(question)

    assert llm_calls == [question]
    assert "Do you mean" in response.answer
    assert "Mystery Stall" in response.answer
    assert response.sources == []
    assert vector_store.search_calls == 0


def test_vendor_recommendation_request_stays_on_vector_evidence_path(
    session,
) -> None:
    popeyes = _add_vendor(session, name="Popeyes", location="North Spine")
    session.commit()

    embedder = LocalEmbedder()
    store = EvidenceKnowledgeStore(
        KnowledgeResult(
            source_type="internal_review",
            source_id="review-popeyes",
            vendor_id=popeyes.id,
            content="The fried chicken is crisp and students recommend it.",
            metadata={},
        ),
        vendor_name="Popeyes",
    )
    service = ChatService(
        embedder,
        store,
        generate=lambda _prompt: "Students recommend the fried chicken [1].",
        router=StaticRouter("Vector"),
        sql_store=NeverSqlStore(),
        session=session,
    )

    response = service.answer("find recommendations for Popeyes")

    assert response.search_type == "Vector"
    assert embedder.calls == [["find recommendations for Popeyes"]]
    assert store.search_calls == [{"vendor_ids": [popeyes.id]}]
    assert [source.source_id for source in response.sources] == [
        "review-popeyes"
    ]
    assert response.sources[0].vendor_name == "Popeyes"


@pytest.mark.parametrize(
    ("question", "expected_name"),
    [
        ("find recommendations for Popeys", "Popeyes"),
        ("Is Mystery Stall halal?", "Mystery Stall"),
        ("Does Mystery Stall have vegetarian food?", "Mystery Stall"),
    ],
)
def test_vector_unknown_vendor_clarifies_before_any_retrieval(
    session,
    question: str,
    expected_name: str,
) -> None:
    _add_vendor(session, name="Popeyes", location="North Spine")
    session.commit()

    vector_store = NeverKnowledgeStore()
    service = ChatService(
        NeverEmbedder(),
        vector_store,
        generate=_never_generate,
        router=StaticRouter("Vector"),
        sql_store=NeverSqlStore(),
        session=session,
    )

    response = service.answer(question)

    assert response.search_type == "Vector"
    assert expected_name in response.answer
    assert "clarify" in response.answer.casefold()
    assert response.sources == []
    assert vector_store.search_calls == 0


@pytest.mark.parametrize("search_type", ["SQL", "SQL + Vector", "Vector"])
@pytest.mark.parametrize(
    ("question", "expected_name"),
    [
        ("What is the price at Mystery Stall?", "Mystery Stall"),
        ("Does Mystery Stall sell halal food?", "Mystery Stall"),
        ("Is halal food available at Mystery Stall?", "Mystery Stall"),
        ("Is Mystery Stall expensive?", "Mystery Stall"),
        ("reviews for Burger King?", "Burger King"),
        ("reviews for burger king?", "burger king"),
        ("recommendations for KFC?", "KFC"),
        ("recommendations for kfc?", "kfc"),
        ("reviews for Starbucks?", "Starbucks"),
        ("reviews for starbucks?", "starbucks"),
        ("recommend Jollibee", "Jollibee"),
        ("recommend jollibee", "jollibee"),
        ("recommend Starbucks", "Starbucks"),
        ("recommend starbucks", "starbucks"),
    ],
)
def test_explicit_unknown_vendor_queries_never_broad_retrieve(
    session,
    search_type: str,
    question: str,
    expected_name: str,
) -> None:
    _add_vendor(session, name="Popeyes", location="North Spine")
    session.commit()

    vector_store = NeverKnowledgeStore()
    service = ChatService(
        NeverEmbedder(),
        vector_store,
        generate=_never_generate,
        router=StaticRouter(search_type),
        sql_store=NeverSqlStore(),
        session=session,
    )

    response = service.answer(question)

    assert response.search_type == search_type
    assert expected_name in response.answer
    assert "clarify" in response.answer.casefold()
    assert response.sources == []
    assert vector_store.search_calls == 0


@pytest.mark.parametrize(
    "question",
    [
        "recommend chicken rice and noodles",
        "recommend cheap and filling food",
        "recommend Chicken Rice and Noodles",
        "recommend Cheap and Filling Food",
        "recommendations for Chicken Rice",
        "reviews for Chicken Rice",
        "recommendations for chicken rice",
        "reviews for chicken rice",
        "reviews for Fried Rice",
        "recommendations for Beef Noodles",
        "reviews for Nasi Lemak",
        "recommendations for Laksa",
        "recommendations for laksa",
        "reviews for Mala Xiang Guo",
        "reviews for mala xiang guo",
        "recommendations for Fish Soup",
        "recommendations for fish soup",
        "recommend Chicken Rice",
        "recommend chicken rice",
        "recommend Mala Xiang Guo",
        "recommend mala xiang guo",
        "recommend something new",
        "recommend places nearby",
        "recommend some good options",
        "recommend a new restaurant near campus",
    ],
)
def test_general_food_evidence_query_is_not_treated_as_unknown_vendor(
    session,
    question: str,
) -> None:
    popeyes = _add_vendor(session, name="Popeyes", location="North Spine")
    session.commit()

    embedder = LocalEmbedder()
    store = EvidenceKnowledgeStore(
        KnowledgeResult(
            source_type="internal_review",
            source_id="general-food-result",
            vendor_id=popeyes.id,
            content="A useful general food recommendation.",
            metadata={},
        ),
        vendor_name="Popeyes",
    )
    service = ChatService(
        embedder,
        store,
        generate=lambda _prompt: "Here is a general recommendation [1].",
        router=StaticRouter("Vector"),
        sql_store=NeverSqlStore(),
        session=session,
    )

    response = service.answer(question)

    assert response.search_type == "Vector"
    assert response.answer == "Here is a general recommendation [1]."
    assert embedder.calls == [[question]]
    assert store.search_calls == [None]
    assert [source.source_id for source in response.sources] == [
        "general-food-result"
    ]


def test_vendor_match_clears_cuisine_word_embedded_in_vendor_name(
    session,
) -> None:
    thai_dynasty = _add_vendor(
        session,
        name="Thai Dynasty Express",
        location="North Spine",
        category="Café/Restaurant",
    )
    man_le = _add_vendor(
        session,
        name="Man Le Chinese Restaurant",
        location="Campus Clubhouse",
        category="Café/Restaurant",
    )
    session.commit()

    cases = [
        ("where is Thai Dynasty?", thai_dynasty.id),
        ("where is Man Le Chinese Restaurant?", man_le.id),
    ]
    for question, expected_vendor_id in cases:
        sql_store = RecordingSqlStore(PgSqlStore(session))
        service = ChatService(
            NeverEmbedder(),
            NeverKnowledgeStore(),
            generate=_generated_answer,
            router=StaticRouter("SQL"),
            sql_store=sql_store,
            session=session,
        )

        response = service.answer(question)

        assert len(sql_store.search_calls) == 1
        filters = sql_store.search_calls[0]
        assert filters.vendor_ids == [expected_vendor_id]
        assert filters.cuisine is None
        assert [source.vendor_id for source in response.sources] == [
            expected_vendor_id
        ]


def test_empty_rank_retries_llm_once_and_preserves_original_query_shape(
    session,
) -> None:
    llm_calls: list[str] = []

    def corrected_scope_with_wrong_shape(question: str) -> StructuredFilter:
        llm_calls.append(question)
        return StructuredFilter(
            cuisine="Japanese",
            location="South Spine",
            query_kind="count",
            top_n=99,
            sort="price_desc",
        )

    sql_store = ScriptedSqlStore(
        [
            [],
            [
                SqlResult(
                    vendor_id=77,
                    vendor_name="Sakura Kitchen",
                    category="Korean",
                )
            ],
        ]
    )
    service = ChatService(
        NeverEmbedder(),
        NeverKnowledgeStore(),
        generate=_generated_answer,
        router=StaticRouter("SQL"),
        sql_store=sql_store,
        filter_extractor_llm=corrected_scope_with_wrong_shape,
        session=session,
    )
    question = "top 3 highest rated Korean vendors"

    response = service.answer(question)

    assert llm_calls == [question]
    assert len(sql_store.search_calls) == 2
    initial, retry = sql_store.search_calls
    assert (initial.query_kind, initial.top_n, initial.sort) == (
        "rank",
        3,
        "rating",
    )
    assert retry.cuisine == "Korean"
    assert retry.location == "South Spine"
    assert (retry.query_kind, retry.top_n, retry.sort) == (
        "rank",
        3,
        "rating",
    )
    assert [source.vendor_id for source in response.sources] == [77]


def test_scoped_zero_count_retries_llm_once_and_preserves_count_shape(
    session,
) -> None:
    llm_calls: list[str] = []

    def corrected_scope_with_wrong_shape(question: str) -> StructuredFilter:
        llm_calls.append(question)
        return StructuredFilter(
            cuisine="Japanese",
            location="South Spine",
            query_kind="rank",
            top_n=5,
            sort="rating",
        )

    sql_store = ScriptedSqlStore(
        [
            [SqlResult(count=0)],
            [SqlResult(count=2)],
        ]
    )
    service = ChatService(
        NeverEmbedder(),
        NeverKnowledgeStore(),
        generate=_generated_answer,
        router=StaticRouter("SQL"),
        sql_store=sql_store,
        filter_extractor_llm=corrected_scope_with_wrong_shape,
        session=session,
    )
    question = "how many Korean vendors are there?"

    response = service.answer(question)

    assert llm_calls == [question]
    assert len(sql_store.search_calls) == 2
    initial, retry = sql_store.search_calls
    assert initial.cuisine == "Korean"
    assert (initial.query_kind, initial.top_n, initial.sort) == (
        "count",
        None,
        None,
    )
    assert retry.cuisine == "Korean"
    assert retry.location == "South Spine"
    assert (retry.query_kind, retry.top_n, retry.sort) == (
        "count",
        None,
        None,
    )
    assert len(response.sources) == 1
    assert response.sources[0].source_type == "count"
    assert response.sources[0].count == 2


@pytest.mark.parametrize("extractor_state", ["missing", "empty", "error"])
@pytest.mark.parametrize("separator", ["or", "、"])
def test_partial_unknown_multi_vendor_never_silently_drops_unknown(
    session,
    extractor_state: str,
    separator: str,
) -> None:
    _add_vendor(session, name="Popeyes", location="North Spine")
    session.commit()

    llm_calls: list[str] = []

    def extractor(question: str) -> StructuredFilter:
        llm_calls.append(question)
        if extractor_state == "error":
            raise RuntimeError("filter extraction unavailable")
        return StructuredFilter()

    vector_store = NeverKnowledgeStore()
    service = ChatService(
        NeverEmbedder(),
        vector_store,
        generate=_never_generate,
        router=StaticRouter("SQL"),
        sql_store=NeverSqlStore(),
        filter_extractor_llm=(None if extractor_state == "missing" else extractor),
        session=session,
    )
    question = f"where is Popeyes {separator} Mystery Stall?"

    response = service.answer(question)

    assert "Mystery Stall" in response.answer
    assert "clarify" in response.answer.casefold()
    assert response.search_type == "SQL"
    assert response.sources == []
    assert llm_calls == ([] if extractor_state == "missing" else [question])
    assert vector_store.search_calls == 0


@pytest.mark.parametrize("extractor_state", ["missing", "empty", "error"])
def test_unknown_hybrid_vendor_never_resolves_all_vendors(
    session,
    extractor_state: str,
) -> None:
    _add_vendor(session, name="Popeyes", location="North Spine")
    session.commit()

    llm_calls: list[str] = []

    def extractor(question: str) -> StructuredFilter:
        llm_calls.append(question)
        if extractor_state == "error":
            raise RuntimeError("filter extraction unavailable")
        return StructuredFilter()

    vector_store = NeverKnowledgeStore()
    service = ChatService(
        NeverEmbedder(),
        vector_store,
        generate=_never_generate,
        router=StaticRouter("SQL + Vector"),
        sql_store=NeverSqlStore(),
        filter_extractor_llm=(None if extractor_state == "missing" else extractor),
        session=session,
    )
    question = "what do people recommend at Mystery Stall?"

    response = service.answer(question)

    assert "Mystery Stall" in response.answer
    assert "clarify" in response.answer.casefold()
    assert response.search_type == "SQL + Vector"
    assert response.sources == []
    assert llm_calls == ([] if extractor_state == "missing" else [question])
    assert vector_store.search_calls == 0


@pytest.mark.parametrize(
    ("search_type", "question", "expected_name"),
    [
        (
            "SQL",
            "Where is Mystery Stall in North Spine?",
            "Mystery Stall",
        ),
        (
            "SQL + Vector",
            "recommend Mystery Stall near Hall 14",
            "Mystery Stall",
        ),
        (
            "SQL",
            "where is Mystery Stall serving Korean food?",
            "Mystery Stall",
        ),
    ],
)
def test_unknown_vendor_with_valid_scope_still_clarifies_before_retrieval(
    session,
    search_type: str,
    question: str,
    expected_name: str,
) -> None:
    _add_vendor(session, name="Popeyes", location="North Spine")
    session.commit()

    vector_store = NeverKnowledgeStore()
    service = ChatService(
        NeverEmbedder(),
        vector_store,
        generate=_never_generate,
        router=StaticRouter(search_type),
        sql_store=NeverSqlStore(),
        session=session,
    )

    response = service.answer(question)

    assert expected_name in response.answer
    assert "clarify" in response.answer.casefold()
    assert response.search_type == search_type
    assert response.sources == []
    assert vector_store.search_calls == 0


def test_plain_cuisine_and_location_remain_structured_filters(session) -> None:
    korean = _add_vendor(
        session,
        name="Seoul Kitchen",
        location="North Spine",
        category="Korean",
    )
    session.commit()

    sql_store = RecordingSqlStore(PgSqlStore(session))
    service = ChatService(
        NeverEmbedder(),
        NeverKnowledgeStore(),
        generate=_generated_answer,
        router=StaticRouter("SQL"),
        sql_store=sql_store,
        session=session,
    )

    response = service.answer("where can I find Korean food in North Spine?")

    assert [source.vendor_id for source in response.sources] == [korean.id]
    assert len(sql_store.search_calls) == 1
    filters = sql_store.search_calls[0]
    assert filters.cuisine == "Korean"
    assert filters.location == "North Spine"
    assert filters.vendor_names is None
    assert filters.vendor_ids is None


@pytest.mark.parametrize(
    ("question", "expected_names"),
    [
        ("where are Popeyes and Gelare?", {"Popeyes", "Geláre"}),
        (
            "where are Popeyes and Blue Ocean Kopi & Toast?",
            {"Popeyes", "Blue Ocean Kopi & Toast"},
        ),
        ("where is Popeyes and when does it close?", {"Popeyes"}),
        ("where is Popeyes or is it already closed?", {"Popeyes"}),
    ],
)
def test_fully_known_vendor_query_does_not_call_hallucinating_llm(
    session,
    question: str,
    expected_names: set[str],
) -> None:
    _add_vendor(session, name="Popeyes", location="North Spine")
    _add_vendor(session, name="Geláre", location="South Spine")
    _add_vendor(
        session,
        name="Blue Ocean Kopi & Toast",
        location="South Spine",
    )
    session.commit()

    llm_calls: list[str] = []

    def hallucinating_extractor(value: str) -> StructuredFilter:
        llm_calls.append(value)
        return StructuredFilter(
            vendor_names=["Popeyes", "Gelare", "Mystery Stall"]
        )

    sql_store = RecordingSqlStore(PgSqlStore(session))
    service = ChatService(
        NeverEmbedder(),
        NeverKnowledgeStore(),
        generate=_generated_answer,
        router=StaticRouter("SQL"),
        sql_store=sql_store,
        filter_extractor_llm=hallucinating_extractor,
        session=session,
    )

    response = service.answer(question)

    assert llm_calls == []
    assert {source.vendor_name for source in response.sources} == expected_names
    assert len(sql_store.search_calls) == 1
    assert sql_store.search_calls[0].vendor_names is None


@pytest.mark.parametrize("search_type", ["SQL", "SQL + Vector"])
def test_missing_sql_store_returns_safe_direct_response(search_type: str) -> None:
    vector_store = NeverKnowledgeStore()
    service = ChatService(
        NeverEmbedder(),
        vector_store,
        generate=_never_generate,
        router=StaticRouter(search_type),
        sql_store=None,
    )

    response = service.answer("list Korean food")

    assert response.search_type == search_type
    assert "temporarily unavailable" in response.answer
    assert response.sources == []
    assert vector_store.search_calls == 0


@pytest.mark.parametrize(
    "separator",
    [";", "；", "/", "+", "vs", "versus", "\n"],
)
def test_partial_known_unknown_vendor_separators_never_drop_unknown(
    session,
    separator: str,
) -> None:
    """Every coordinated-clause spelling must fail closed on unknown names."""

    _add_vendor(session, name="Amber Ladle", location="North Spine")
    session.commit()

    vector_store = NeverKnowledgeStore()
    service = ChatService(
        NeverEmbedder(),
        vector_store,
        generate=_never_generate,
        router=StaticRouter("SQL"),
        sql_store=NeverSqlStore(),
        session=session,
    )
    question = f"where are Amber Ladle {separator} Nebula Nook?"

    response = service.answer(question)

    assert "Nebula Nook" in response.answer
    assert "clarify" in response.answer.casefold()
    assert response.sources == []
    assert vector_store.search_calls == 0


def test_llm_vendor_in_cuisine_is_corrected_for_any_database_vendor(
    session,
) -> None:
    """Vendor-as-cuisine correction must resolve from DB, not a named fixture."""

    vendor = _add_vendor(
        session,
        name="Quartz Kettle",
        location="Innovation Centre",
        category="Cafe",
    )
    session.commit()
    llm_calls: list[str] = []

    def misclassified_brand(question: str) -> StructuredFilter:
        llm_calls.append(question)
        return StructuredFilter(cuisine="Quartz Kettle")

    sql_store = RecordingSqlStore(PgSqlStore(session))
    service = ChatService(
        NeverEmbedder(),
        NeverKnowledgeStore(),
        generate=_generated_answer,
        router=StaticRouter("SQL"),
        sql_store=sql_store,
        filter_extractor_llm=misclassified_brand,
        session=session,
    )
    question = "show me the place saved as my lunch option"

    response = service.answer(question)

    assert llm_calls == [question]
    assert len(sql_store.search_calls) == 1
    filters = sql_store.search_calls[0]
    assert filters.vendor_ids == [vendor.id]
    assert filters.vendor_names is None
    assert filters.cuisine is None
    assert [source.vendor_id for source in response.sources] == [vendor.id]


@pytest.mark.parametrize(
    ("keyword", "canonical"),
    [
        (keyword, canonical)
        for keyword, canonical in CUISINE_KEYWORDS.items()
        if canonical is not None
    ],
)
def test_every_positive_cuisine_taxonomy_term_remains_a_cuisine_filter(
    keyword: str,
    canonical: str,
) -> None:
    filters = extract_structured_filters(
        f"Where can I find {keyword} food?"
    )

    assert filters.cuisine == canonical
    assert filters.vendor_names is None
    assert filters.vendor_ids is None


@pytest.mark.parametrize(
    "cuisine",
    ["Vietnamese", "Middle Eastern", "South East Asian"],
)
def test_explicit_new_cuisine_food_phrase_uses_generic_sql_filter(
    session,
    cuisine: str,
) -> None:
    """New cuisine phrases must not require another hard-coded keyword."""

    matching = _add_vendor(
        session,
        name=f"{cuisine} Test Kitchen",
        location="Innovation Centre",
        category=f"{cuisine} restaurant",
    )
    _add_vendor(
        session,
        name="Unrelated Test Kitchen",
        location="Innovation Centre",
        category="Bakery",
    )
    session.commit()

    sql_store = RecordingSqlStore(PgSqlStore(session))
    service = ChatService(
        NeverEmbedder(),
        NeverKnowledgeStore(),
        generate=_generated_answer,
        router=StaticRouter("SQL"),
        sql_store=sql_store,
        session=session,
    )

    response = service.answer(f"Where can I find {cuisine} food?")

    assert len(sql_store.search_calls) == 1
    filters = sql_store.search_calls[0]
    assert filters.cuisine == cuisine
    assert filters.vendor_names is None
    assert filters.vendor_ids is None
    assert [source.vendor_id for source in response.sources] == [matching.id]


@pytest.mark.parametrize(
    "affirmation",
    ["yes", "yep", "correct", "\u5bf9", "\u6ca1\u9519"],
)
def test_single_vendor_clarification_affirmation_restores_location_intent(
    session,
    affirmation: str,
) -> None:
    """Affirmations accept a single suggestion without brand-specific code."""

    vendor = _add_vendor(
        session,
        name="luckin coffee - NTU South Spine",
        location="South Spine",
        category="Cafe",
    )
    session.commit()

    router = StaticRouter("Vector")
    sql_store = RecordingSqlStore(PgSqlStore(session))
    vector_store = NeverKnowledgeStore()
    service = ChatService(
        NeverEmbedder(),
        vector_store,
        generate=_generated_answer,
        router=router,
        sql_store=sql_store,
        session=session,
    )
    original_question = "Where is lukin coffe?"
    clarification = service.answer(original_question)
    history = [
        ChatHistoryMessage(role="user", content=original_question),
        ChatHistoryMessage(role="assistant", content=clarification.answer),
    ]

    response = service.answer(affirmation, history=history)

    assert "Do you mean luckin coffee - NTU South Spine?" in clarification.answer
    assert response.search_type == "SQL"
    assert [source.vendor_id for source in response.sources] == [vendor.id]
    assert len(sql_store.search_calls) == 1
    assert sql_store.search_calls[0].vendor_ids == [vendor.id]
    assert vector_store.search_calls == 0
    assert any(
        "luckin coffee - ntu south spine" in question.casefold()
        and "where" in question.casefold()
        for question in router.calls
    )


def test_vendor_clarification_affirmation_preserves_vector_recommendation_intent(
    session,
) -> None:
    """Accepting a typo correction must not turn a review request into SQL."""

    vendor = _add_vendor(
        session,
        name="Popeyes",
        location="North Spine",
    )
    session.commit()
    embedder = LocalEmbedder()
    store = EvidenceKnowledgeStore(
        KnowledgeResult(
            source_type="internal_review",
            source_id="review-popeyes-confirmation",
            vendor_id=vendor.id,
            content="Students recommend the fried chicken.",
            metadata={},
        ),
        vendor_name="Popeyes",
    )
    router = StaticRouter("Vector")
    service = ChatService(
        embedder,
        store,
        generate=lambda _prompt: "Students recommend the fried chicken [1].",
        router=router,
        sql_store=NeverSqlStore(),
        session=session,
    )
    original_question = "What do people recommend at Popeys?"
    clarification = service.answer(original_question)
    history = [
        ChatHistoryMessage(role="user", content=original_question),
        ChatHistoryMessage(role="assistant", content=clarification.answer),
    ]

    response = service.answer("yes", history=history)

    assert "Do you mean Popeyes?" in clarification.answer
    assert response.search_type == "Vector"
    assert store.search_calls == [{"vendor_ids": [vendor.id]}]
    assert [source.source_id for source in response.sources] == [
        "review-popeyes-confirmation"
    ]
    assert len(embedder.calls) == 1
    retrieval_question = embedder.calls[0][0].casefold()
    assert "recommend" in retrieval_question
    assert "popeyes" in retrieval_question


def test_affirming_multiple_distinct_suggestions_requires_exact_vendor_choice(
    session,
) -> None:
    """A bare yes is ambiguous when the prior clarification named brands."""

    _add_vendor(session, name="Alpha Cafe", location="North Spine")
    _add_vendor(session, name="Alfa Cafe", location="South Spine")
    session.commit()
    vector_store = NeverKnowledgeStore()
    service = ChatService(
        NeverEmbedder(),
        vector_store,
        generate=_never_generate,
        router=StaticRouter("Vector"),
        sql_store=NeverSqlStore(),
        session=session,
    )
    history = [
        ChatHistoryMessage(role="user", content="Where is Alpa Cafe?"),
        ChatHistoryMessage(
            role="assistant",
            content=(
                "Do you mean Alpha Cafe, Alfa Cafe? Please clarify which "
                "vendor you want me to look up."
            ),
        ),
    ]

    response = service.answer("yes", history=history)

    assert response.search_type == "Conversational"
    assert response.sources == []
    assert "Alpha Cafe" in response.answer
    assert "Alfa Cafe" in response.answer
    assert "vendor" in response.answer.casefold()
    assert vector_store.search_calls == 0


@pytest.mark.parametrize(
    "clarification",
    [
        (
            'I could not identify "Moonlight Noodles". Do you mean a specific '
            "NTU food vendor? Please clarify the vendor name."
        ),
        (
            "Do you mean a specific NTU food vendor? Please clarify the vendor "
            "name, cuisine, or location."
        ),
    ],
)
def test_affirming_generic_clarification_without_candidates_requires_name(
    session,
    clarification: str,
) -> None:
    """A generic clarification has no candidate that a bare yes can accept."""

    vector_store = NeverKnowledgeStore()
    service = ChatService(
        NeverEmbedder(),
        vector_store,
        generate=_never_generate,
        router=StaticRouter("Vector"),
        sql_store=NeverSqlStore(),
        session=session,
    )
    history = [
        ChatHistoryMessage(role="user", content="Where is Moonlight Noodles?"),
        ChatHistoryMessage(role="assistant", content=clarification),
    ]

    response = service.answer("yes", history=history)

    assert response.search_type == "Conversational"
    assert response.sources == []
    assert "vendor" in response.answer.casefold()
    assert any(
        token in response.answer.casefold()
        for token in ("name", "clarify", "specify", "type")
    )
    assert vector_store.search_calls == 0


def test_generic_clarification_quoted_request_is_not_a_suggested_vendor(
    session,
) -> None:
    """Only the suggestion slot, not arbitrary clarification text, is state."""

    _add_vendor(session, name="Moonlight", location="North Spine")
    session.commit()
    vector_store = NeverKnowledgeStore()
    service = ChatService(
        NeverEmbedder(),
        vector_store,
        generate=_never_generate,
        router=StaticRouter("Vector"),
        sql_store=NeverSqlStore(),
        session=session,
    )
    history = [
        ChatHistoryMessage(role="user", content="Where is Moonlite?"),
        ChatHistoryMessage(
            role="assistant",
            content=(
                'I could not identify "Moonlight Mystery". Do you mean a '
                "specific NTU food vendor? Please clarify the vendor name."
            ),
        ),
    ]

    response = service.answer("yes", history=history)

    assert response.search_type == "Conversational"
    assert response.sources == []
    assert "vendor" in response.answer.casefold()
    assert vector_store.search_calls == 0


def test_affirming_one_brand_returns_all_same_name_vendor_branches(session) -> None:
    """Location-qualified rows for one brand are one confirmation choice."""

    north = _add_vendor(
        session,
        name="The Crowded Bowl (North Spine)",
        location="North Spine",
    )
    gaia = _add_vendor(
        session,
        name="The Crowded Bowl (Gaia)",
        location="Gaia",
    )
    session.commit()
    sql_store = RecordingSqlStore(PgSqlStore(session))
    vector_store = NeverKnowledgeStore()
    service = ChatService(
        NeverEmbedder(),
        vector_store,
        generate=_generated_answer,
        router=StaticRouter("Vector"),
        sql_store=sql_store,
        session=session,
    )
    original_question = "Where is The Crowded Bol?"
    clarification = service.answer(original_question)
    history = [
        ChatHistoryMessage(role="user", content=original_question),
        ChatHistoryMessage(role="assistant", content=clarification.answer),
    ]

    response = service.answer("correct", history=history)

    assert "The Crowded Bowl (North Spine)" in clarification.answer
    assert "The Crowded Bowl (Gaia)" in clarification.answer
    assert response.search_type == "SQL"
    assert {source.vendor_id for source in response.sources} == {
        north.id,
        gaia.id,
    }
    assert len(sql_store.search_calls) == 1
    assert set(sql_store.search_calls[0].vendor_ids or []) == {
        north.id,
        gaia.id,
    }
    assert vector_store.search_calls == 0


@pytest.mark.parametrize("rejection", ["no", "nope", "\u4e0d\u5bf9"])
def test_rejecting_vendor_suggestion_asks_for_name_without_retrieval(
    session,
    rejection: str,
) -> None:
    _add_vendor(
        session,
        name="luckin coffee - NTU South Spine",
        location="South Spine",
    )
    session.commit()
    vector_store = NeverKnowledgeStore()
    service = ChatService(
        NeverEmbedder(),
        vector_store,
        generate=_never_generate,
        router=StaticRouter("Vector"),
        sql_store=NeverSqlStore(),
        session=session,
    )
    history = [
        ChatHistoryMessage(role="user", content="Where is lukin coffe?"),
        ChatHistoryMessage(
            role="assistant",
            content=(
                "Do you mean luckin coffee - NTU South Spine? Please clarify "
                "which vendor you want me to look up."
            ),
        ),
    ]

    response = service.answer(rejection, history=history)

    assert response.search_type == "Conversational"
    assert response.sources == []
    assert "vendor" in response.answer.casefold()
    assert any(
        token in response.answer.casefold()
        for token in ("name", "clarify", "specify", "type")
    )
    assert vector_store.search_calls == 0


def test_yes_after_non_clarification_does_not_confirm_previous_vendor(
    session,
) -> None:
    """Only the system's exact clarification turn activates yes/no handling."""

    _add_vendor(session, name="Popeyes", location="North Spine")
    session.commit()
    embedder = LocalEmbedder()
    vector_store = EmptyKnowledgeStore()
    sql_store = RecordingSqlStore(PgSqlStore(session))
    service = ChatService(
        embedder,
        vector_store,
        generate=lambda _prompt: "Okay.",
        router=StaticRouter("Vector"),
        sql_store=sql_store,
        session=session,
    )
    history = [
        ChatHistoryMessage(role="user", content="Where is Popeyes?"),
        ChatHistoryMessage(
            role="assistant",
            content="Popeyes is located at North Spine.",
        ),
    ]

    response = service.answer("yes", history=history)

    assert response.search_type != "SQL"
    assert sql_store.search_calls == []
    assert not any(source.vendor_name == "Popeyes" for source in response.sources)
