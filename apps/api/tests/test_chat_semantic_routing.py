import json
import re
from datetime import UTC, datetime

import pytest

from app.api import dependencies
from app.main import app
from app.models import RedditComment, Vendor
from app.schemas.chat import ChatHistoryMessage
from app.services.chat import ChatService
from app.services.query_resolution import QueryConstraints, ResolvedQuery
from app.services.retrieval import FakeKnowledgeStore, KnowledgeResult
from app.services.sql_search import PgSqlStore


class Embedder:
    def __init__(self):
        self.questions = []

    def embed(self, questions):
        self.questions.extend(questions)
        return [[1.0, 0.0] for _ in questions]


def make_service(session, plan, *, store=None):
    prompts, resolutions = [], []

    def resolve(question, history, **context):
        resolutions.append((question, history, context))
        return plan

    def no_legacy(*args, **kwargs):
        pytest.fail("Typed routing must not infer entity types again from a rewritten sentence")

    service = ChatService(
        Embedder(), store or FakeKnowledgeStore(items=[]), session=session, sql_store=PgSqlStore(session),
        query_resolver=resolve, rewrite_llm=no_legacy, filter_extractor_llm=no_legacy,
        generate=lambda prompt: prompts.append(prompt) or "Grounded answer [1].",
    )
    return service, prompts, resolutions


@pytest.mark.parametrize("question", ["where can I get it?", "Any spots for that?", "那去哪儿能吃到？", "这个附近有没有卖的", "where can i find the food i jus picked"])
@pytest.mark.parametrize("streaming", [False, True])
def test_semantic_picker_references_are_not_limited_to_special_phrases(session, question, streaming):
    salad = Vendor(name="The Crowded Bowl", category="Salad shop")
    dessert = Vendor(name="AcaiGuru", category="Dessert shop")
    session.add_all([salad, dessert])
    session.commit()
    plan = ResolvedQuery(target="food", reference="picker", question="Where can I find salad?", food_type="Salad")
    service, prompts, calls = make_service(session, plan)
    if streaming:
        events = list(service.stream_answer(question, food_pick="Salad"))
        sources = next(data for event, data in events if event == "sources")
    else:
        sources = service.answer(question, food_pick="Salad").sources
    assert {source.vendor_id for source in sources} == {salad.id}
    assert "AcaiGuru" not in prompts[0]
    assert calls[0][2]["food_pick"] == "Salad"
    assert (salad.id, salad.name) in calls[0][2]["vendors"]


@pytest.mark.parametrize("target", ["food", "vendor"])
def test_explicit_new_topic_overrides_old_picker_state(session, target):
    salad, pizza, vendor = Vendor(name="Salad Place", category="Salad"), Vendor(name="Pizza House", category="Pizza"), Vendor(name="Chateraise")
    session.add_all([salad, pizza, vendor])
    session.commit()
    question = "I'd rather have pizza" if target == "food" else "Where is Chateraise?"
    plan = ResolvedQuery(target=target, reference="current", question=question,
                         food_type="Pizza" if target == "food" else None,
                         vendor_names=["Chateraise"] if target == "vendor" else [])
    service, prompts, _ = make_service(session, plan)
    result = service.answer(question, food_pick="Salad")
    assert {source.vendor_id for source in result.sources} == {pizza.id if target == "food" else vendor.id}
    assert '"latest_food_pick"' not in prompts[0]
    assert "Salad Place" not in prompts[0]


def test_followup_about_recommended_business_stays_a_business_query(session):
    vendor = Vendor(name="Chateraise", opening_hours="10:00-22:00")
    session.add(vendor)
    session.commit()
    plan = ResolvedQuery(target="vendor", reference="conversation", question="When does Chateraise close?", vendor_names=["Chateraise"])
    service, prompts, _ = make_service(session, plan)
    result = service.answer("When does that shop close?", food_pick="Salad",
                            history=[ChatHistoryMessage(role="assistant", content="Chateraise is at North Spine.")])
    assert {source.vendor_id for source in result.sources} == {vendor.id}
    assert "22:00" in prompts[0]
    assert '"latest_food_pick"' not in prompts[0]


@pytest.mark.parametrize("language,question", [("English", "What was my latest draw?"), ("Chinese", "我最后抽到了什么？")])
def test_memory_uses_only_actual_latest_pick_and_never_old_history(session, language, question):
    plan = ResolvedQuery(target="picker_memory", reference="picker", question=question, language=language)
    service, prompts, _ = make_service(session, plan)
    history = [ChatHistoryMessage(role="assistant", content="Your old pick was Salad.")]
    result = service.answer(question, food_pick="Pizza", history=history)
    assert "Pizza" in result.answer and "Salad" not in result.answer
    missing = service.answer(question, history=history)
    assert "Salad" not in missing.answer
    assert "food picker" in missing.answer
    assert not prompts


@pytest.mark.parametrize("plan", [None, ResolvedQuery(target="vendor", reference="current", question="Where is Salad?", vendor_names=["Salad"]),
    ResolvedQuery(target="vendor", reference="current", question="Where is it?", vendor_names=["Salad in NTU? Please recommend two places"]),
    ResolvedQuery(target="food", reference="picker", question="Where?", food_type="Pizza"),
    ResolvedQuery(target="food", reference="current", question="Where is salad?", food_type="Salad"),
])
def test_invalid_or_stale_plans_clarify_without_retrieving_unrelated_vendors(session, plan):
    session.add(Vendor(name="AcaiGuru", category="Dessert"))
    session.commit()
    service, prompts, _ = make_service(session, plan)
    question = "I want pizza" if plan and plan.reference == "current" and plan.target == "food" else "where can I get it?"
    result = service.answer(question, food_pick="Salad")
    assert "clarify" in result.answer.lower()
    assert result.sources == []
    assert service._embedder.questions == []
    assert prompts == []


def test_invalid_plan_does_not_guess_whether_named_vendor_is_a_target_or_exclusion(session):
    vendor = Vendor(name="Chateraise")
    session.add_all([vendor, Vendor(name="Other Shop")])
    session.commit()
    service, prompts, _ = make_service(session, None)
    result = service.answer("Salad except Chateraise please", food_pick="Salad")
    assert result.sources == []
    assert "clarify" in result.answer.lower()
    assert not prompts


def test_zero_result_preserves_constraints_without_retrying_a_different_entity(session):
    session.add(Vendor(name="Chateraise", location="South Spine"))
    session.commit()
    plan = ResolvedQuery(target="vendor", reference="current", question="Chateraise at North Spine?", vendor_names=["Chateraise"],
                         constraints=QueryConstraints(location="North Spine"))
    service, prompts, _ = make_service(session, plan)
    result = service.answer(plan.question)
    assert result.sources == []
    assert prompts == []


def test_food_constraints_exclusions_and_count_use_the_same_bounded_matches(session):
    vendors = [Vendor(name="The Crowded Bowl", category="Salad", location="North Spine", vegetarian=True),
               Vendor(name="Green Kitchen", dishes="Salad", location="North Spine", vegetarian=True),
               Vendor(name="South Salad", category="Salad", location="South Spine", vegetarian=True)]
    session.add_all(vendors)
    session.commit()
    question = "北区有几家素食沙拉？除了 The Crowded Bowl"
    plan = ResolvedQuery(target="food", reference="current", question=question, food_type="Salad", food_mention="沙拉", language="Chinese",
                         constraints=QueryConstraints(location="North Spine", vegetarian=True, query_kind="count", excluded_vendor_names=["The Crowded Bowl"]))
    service, prompts, _ = make_service(session, plan)
    result = service.answer(question, food_pick="Pizza")
    assert result.sources[0].count == 1
    assert "1" in result.answer
    assert not prompts


def test_vendor_opinions_are_restricted_to_named_business(session):
    vendor, other = Vendor(name="Chateraise"), Vendor(name="AcaiGuru")
    session.add_all([vendor, other])
    session.commit()
    reviews = [([1.0, 0.0], KnowledgeResult(source_type="google_review", source_id=str(row.id), vendor_id=row.id,
                                         content=row.name + " is popular", metadata={})) for row in [vendor, other]]
    store = FakeKnowledgeStore(items=reviews, vendor_names={row.id: row.name for row in [vendor, other]})
    plan = ResolvedQuery(target="vendor", reference="current", question="Do people like Chateraise?", vendor_names=["Chateraise"], evidence="reviews")
    service, prompts, _ = make_service(session, plan, store=store)
    result = service.answer(plan.question, food_pick="Salad")
    assert {source.vendor_id for source in result.sources} == {vendor.id}
    assert "AcaiGuru" not in prompts[0]


def test_production_dependency_enables_structured_routing_even_without_a_model(session, monkeypatch):
    monkeypatch.setattr(dependencies, "_get_genai_client", lambda: None)
    embedder = Embedder()
    service = dependencies.get_chat_service(session, embedder, FakeKnowledgeStore(items=[]), None, PgSqlStore(session), None, None)
    result = service.answer("Any places for that?", food_pick="Salad")
    assert result.sources == [] and "clarify" in result.answer.lower()
    assert embedder.questions == []


def test_typed_vendor_review_request_preserves_reddit_comments_and_links(session):
    vendor = Vendor(name="Chateraise")
    session.add(vendor)
    session.flush()
    session.add(RedditComment(reddit_comment_id="typed-reddit", vendor_id=vendor.id, subreddit="NTU", thread_id="food",
                              thread_title="Campus food", comment_text="Chateraise has nice cakes.", created_at=datetime.now(UTC),
                              permalink="/r/NTU/comments/food/comment/typed-reddit/"))
    session.commit()
    plan = ResolvedQuery(target="vendor", reference="current", question="Find Reddit comments about Chateraise", vendor_names=["Chateraise"],
                         evidence="reviews", review_source="reddit")
    service, prompts, _ = make_service(session, plan)
    result = service.answer(plan.question)
    assert result.sources[0].source_type == "reddit"
    assert result.sources[0].vendor_id == vendor.id
    assert "typed-reddit" in result.sources[0].permalink
    assert "nice cakes" in prompts[0]


@pytest.mark.parametrize("question", ["Where can I find salad?", "沙拉在哪儿能吃到？"])
def test_http_stream_uses_real_dependency_wiring_for_typed_food_query(client, session, monkeypatch, question):
    salad = Vendor(name="The Crowded Bowl", category="Salad shop")
    session.add_all([salad, Vendor(name="Unrelated Shop")])
    session.commit()
    plan = ResolvedQuery(target="food", reference="current", question="Where can I find salad?", food_type="Salad",
                         food_mention="沙拉" if "沙拉" in question else "salad")
    monkeypatch.setattr(dependencies, "_get_genai_client", lambda: None)
    monkeypatch.setattr(ChatService, "_generate_stream", lambda self, prompt: iter(["Try The Crowded Bowl [1]."]))
    app.dependency_overrides.update({
        dependencies.get_embedder: lambda: Embedder(),
        dependencies.get_knowledge_store: lambda: FakeKnowledgeStore(items=[]),
        dependencies.get_intent_router: lambda: None,
        dependencies.get_filter_extractor_llm: lambda: None,
        dependencies.get_query_resolver: lambda: (lambda *args, **kwargs: plan),
    })
    try:
        response = client.post("/chat/stream", json={"question": question, "food_pick": "Pizza"})
        assert response.status_code == 200
        assert "event: error" not in response.text
        assert "could not identify" not in response.text
        sources = json.loads(re.search(r"event: sources\ndata: (.+)", response.text).group(1))
        assert {source["vendor_id"] for source in sources} == {salad.id}
    finally:
        for dependency in [dependencies.get_embedder, dependencies.get_knowledge_store, dependencies.get_intent_router,
                           dependencies.get_filter_extractor_llm, dependencies.get_query_resolver]:
            app.dependency_overrides.pop(dependency, None)
