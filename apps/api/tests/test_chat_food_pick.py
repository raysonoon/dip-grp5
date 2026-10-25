import pytest
from pydantic import ValidationError

from app.api import dependencies
from app.main import app
from app.schemas.chat import ChatHistoryMessage, ChatRequest
from app.services.chat import ChatService
from app.services.retrieval import FakeKnowledgeStore
from app.services.retrieval import KnowledgeResult
from app.services.sql_search import PgSqlStore
from app.services.query_resolution import ResolvedQuery
from app.models import Vendor


class RecordingEmbedder:
    def __init__(self):
        self.questions = []

    def embed(self, questions):
        self.questions.extend(questions)
        return [[1.0, 0.0] for _ in questions]


def resolve_picker_food(question, history, *, food_pick, vendors):
    return ResolvedQuery(target="food", reference="picker", question=question, food_type=food_pick)


@pytest.mark.parametrize("food", ["Pizza", "Noodles", "Salad"])
def test_food_pick_is_request_context_and_does_not_leak_into_the_next_answer(food):
    prompts = []
    rewrites = []
    embedder = RecordingEmbedder()

    def rewrite(question, history, *, food_pick=None):
        rewrites.append((question, history, food_pick))
        return f"I want {food_pick} food"

    service = ChatService(
        embedder, FakeKnowledgeStore(items=[]),
        generate=lambda prompt: prompts.append(prompt) or "A food idea.",
        rewrite_llm=rewrite,
    )
    service.answer("Would it make a good lunch?", food_pick=food)
    assert rewrites == [("Would it make a good lunch?", [], food)]
    assert embedder.questions[0] == f"I want {food} food"
    assert f'"latest_food_pick": "{food}"' in prompts[0]
    assert "Question: Would it make a good lunch?" in prompts[0]
    assert "User: " not in prompts[0]

    service.answer("Would it make a good lunch?")
    assert "latest_food_pick" not in prompts[1]
    assert embedder.questions[1] == "Would it make a good lunch?"


@pytest.mark.parametrize("streaming", [False, True])
def test_failed_picker_generation_does_not_dump_the_vendor_directory(session, streaming):
    session.add(Vendor(name="Campus Pizza House", location="North Spine"))
    session.commit()

    def fail(_prompt):
        raise TimeoutError("private provider diagnostic")

    service = ChatService(
        RecordingEmbedder(), FakeKnowledgeStore(items=[]), session=session,
        sql_store=PgSqlStore(session), generate=fail,
    )
    if streaming:
        events = list(service.stream_answer("", food_pick="Pizza", recommend_pick=True))
        answer = "".join(data for event, data in events if event == "delta")
    else:
        answer = service.answer("", food_pick="Pizza", recommend_pick=True).answer
    assert len(answer) < 120
    assert "Campus Pizza House" not in answer
    assert "private provider diagnostic" not in answer


def test_stream_route_passes_latest_pick_without_server_session_storage(client):
    calls = []

    class Service:
        def stream_answer(self, question, *, history=None, food_pick=None):
            calls.append((question, food_pick))
            yield "delta", "A food idea."
            yield "sources", []

    app.dependency_overrides[dependencies.get_chat_service] = lambda: Service()
    try:
        response = client.post("/chat/stream", json={
            "question": "What did I roll?", "food_pick": " Roti   prata ",
        })
        assert response.status_code == 200
        assert "event: sources" in response.text
        response = client.post("/chat/stream", json={"question": "What did I roll?"})
        assert response.status_code == 200
        assert calls == [("What did I roll?", "Roti prata"), ("What did I roll?", None)]
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize("food_pick", ["   ", "x" * 81])
def test_food_pick_rejects_blank_or_oversized_context(food_pick):
    with pytest.raises(ValidationError):
        ChatRequest(question="What did I roll?", food_pick=food_pick)


def test_picker_action_requires_a_pick_but_does_not_require_a_fake_question(client):
    calls = []

    class Service:
        def stream_answer(self, question, *, history=None, food_pick=None, recommend_pick=False):
            calls.append((question, food_pick, recommend_pick))
            yield "delta", "A matching vendor."
            yield "sources", []

    app.dependency_overrides[dependencies.get_chat_service] = lambda: Service()
    try:
        response = client.post("/chat/stream", json={"action": "recommend_pick", "food_pick": "Pizza"})
        assert response.status_code == 200
        assert calls == [("", "Pizza", True)]
        assert client.post("/chat/stream", json={"action": "recommend_pick"}).status_code == 422
        assert client.post("/chat/stream", json={}).status_code == 422
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize("food,name", [("Pizza", "Campus Pizza House"), ("Burgers", "Campus Burger Corner")])
def test_picker_recommendations_include_matching_directory_rows_with_correct_citations(session, food, name):
    matching = Vendor(name=name, location="North Spine")
    unrelated = Vendor(name="Unrelated Shop")
    session.add_all([matching, unrelated])
    session.commit()
    prompts = []
    store = FakeKnowledgeStore(
        items=[([1.0, 0.0], KnowledgeResult(
            source_type="google_review", source_id="review-1", vendor_id=unrelated.id,
            content="An unrelated meal.", metadata={},
        ))],
        vendor_names={unrelated.id: unrelated.name},
    )
    service = ChatService(
        RecordingEmbedder(), store, session=session, sql_store=PgSqlStore(session),
        generate=lambda prompt: prompts.append(prompt) or "A matching vendor.",
    )
    result = service.answer("", food_pick=food, recommend_pick=True)
    assert result.sources[0].vendor_id == matching.id
    citation = next(index for index, source in enumerate(result.sources, start=1)
                    if source.source_type == "vendor" and source.vendor_id == matching.id)
    assert f"[{citation}] {name}" in prompts[0]
    assert all(source.vendor_id != unrelated.id for source in result.sources)
    assert "Unrelated Shop" not in prompts[0]
    assert f'"latest_food_pick": "{food}"' in prompts[0]


@pytest.mark.parametrize("question", [
    "where can i find the food i jus picked",
    "Where can I eat the food I just rolled?",
    "Where can I find the food I just picked near North Spine? Only vegetarian places please.",
    "我刚刚抽到的食物，在 NTU 哪里能吃到？推荐 1–2 家，分点简单介绍。",
])
@pytest.mark.parametrize("streaming", [False, True])
def test_picker_follow_up_uses_latest_food_instead_of_treating_rewrite_as_vendor(session, question, streaming):
    vendor = Vendor(name="The Crowded Bowl", location="North Spine", category="Salad", vegetarian=True)
    session.add(vendor)
    session.commit()
    prompts = []
    rewrites = []

    def bad_rewrite(*args, **kwargs):
        rewrites.append(args)
        return "Where can I find Salad in NTU? Please recommend 1–2 places with a brief introduction for each."

    service = ChatService(
        RecordingEmbedder(), FakeKnowledgeStore(items=[]), session=session,
        sql_store=PgSqlStore(session), rewrite_llm=bad_rewrite,
        query_resolver=resolve_picker_food,
        generate=lambda prompt: prompts.append(prompt) or "Try The Crowded Bowl for salad [1].",
    )
    history = [ChatHistoryMessage(role="assistant", content="Here are places to check for salad: The Crowded Bowl.")]
    if streaming:
        events = list(service.stream_answer(question, history=history, food_pick="Salad"))
        answer = "".join(data for event, data in events if event == "delta")
        sources = next(data for event, data in events if event == "sources")
    else:
        response = service.answer(question, history=history, food_pick="Salad")
        answer, sources = response.answer, response.sources
    assert "could not identify" not in answer.lower()
    assert "The Crowded Bowl" in answer
    assert any(source.vendor_id == vendor.id for source in sources)
    assert rewrites == []
    assert f"Question: {question}" in prompts[0]
    assert '"latest_food_pick": "Salad"' in prompts[0]


def test_picker_place_followup_without_current_pick_does_not_guess_from_history():
    embedder = RecordingEmbedder()
    service = ChatService(embedder, FakeKnowledgeStore(items=[]), query_resolver=resolve_picker_food)
    response = service.answer(
        "Where can I find the food I just picked?",
        history=[ChatHistoryMessage(role="assistant", content="You rolled Salad in an earlier chat.")],
    )
    assert "don't have a food pick recorded" in response.answer
    assert "Salad" not in response.answer
    assert response.sources == []
    assert embedder.questions == []


def test_explicit_new_vendor_question_is_not_rewritten_because_a_food_pick_exists(session):
    session.add(Vendor(name="Chateraise", location="North Spine"))
    session.commit()
    embedder = RecordingEmbedder()
    rewrites = []

    def rewrite(*args, **kwargs):
        rewrites.append(args)
        return "Where can I find Salad?"

    service = ChatService(
        embedder, FakeKnowledgeStore(items=[]), session=session,
        sql_store=PgSqlStore(session), rewrite_llm=rewrite,
        generate=lambda prompt: "Chateraise is at North Spine.",
    )
    response = service.answer("Where is Chateraise?", food_pick="Salad")
    assert rewrites == []
    assert embedder.questions == ["Where is Chateraise?"]
    assert response.answer == "Chateraise is at North Spine."


def test_picker_place_followup_retrieves_the_latest_pick_not_the_previous_draw(session):
    vendor = Vendor(name="Campus Pizza House", location="North Spine")
    session.add(vendor)
    session.commit()
    embedder = RecordingEmbedder()
    prompts = []
    service = ChatService(
        embedder, FakeKnowledgeStore(items=[]), session=session,
        sql_store=PgSqlStore(session), generate=lambda prompt: prompts.append(prompt) or "Try Campus Pizza House [1].",
        query_resolver=resolve_picker_food,
    )
    response = service.answer(
        "Where can I find the food I just picked?", food_pick="Pizza",
        history=[ChatHistoryMessage(role="assistant", content="Your previous roll was Salad.")],
    )
    assert embedder.questions == ["Pizza"]
    assert '"latest_food_pick": "Pizza"' in prompts[0]
    assert any(source.vendor_id == vendor.id for source in response.sources)


def test_salad_followup_excludes_unrelated_dessert_directory_and_review_evidence(session):
    salad = Vendor(name="The Crowded Bowl", category="Salad shop", location="North Spine")
    dessert = Vendor(name="AcaiGuru", category="Dessert shop", location="North Spine")
    session.add_all([salad, dessert])
    session.commit()
    prompts = []
    service = ChatService(
        RecordingEmbedder(), FakeKnowledgeStore(
            items=[([1.0, 0.0], KnowledgeResult(
                source_type="google_review", source_id="dessert-review", vendor_id=dessert.id,
                content="Delicious acai desserts and frozen treats.", metadata={},
            ))], vendor_names={dessert.id: dessert.name},
        ), session=session, sql_store=PgSqlStore(session),
        query_resolver=resolve_picker_food,
        generate=lambda prompt: prompts.append(prompt) or "Try The Crowded Bowl [1].",
    )
    response = service.answer("where can i find the food i jus picked", food_pick="Salad")
    assert {source.vendor_id for source in response.sources} == {salad.id}
    assert "AcaiGuru" not in prompts[0]
    assert "acai desserts" not in prompts[0]


@pytest.mark.parametrize("evidence", ["menu", "review"])
def test_picker_can_find_food_evidence_beyond_vendor_names_and_categories(session, evidence):
    vendor = Vendor(name="Campus Kitchen", category="Restaurant", dishes="Salad, Pasta" if evidence == "menu" else None)
    session.add(vendor)
    session.commit()
    review = KnowledgeResult(source_type="google_review", source_id="r-1", vendor_id=vendor.id,
                             content="I ordered the fresh salad for lunch.", metadata={})
    service = ChatService(
        RecordingEmbedder(), FakeKnowledgeStore(items=[([1.0, 0.0], review)] if evidence == "review" else [],
                                               vendor_names={vendor.id: vendor.name}),
        session=session, sql_store=PgSqlStore(session), generate=lambda prompt: "Try Campus Kitchen [1].",
        query_resolver=resolve_picker_food,
    )
    response = service.answer("where can i find the food i jus picked", food_pick="Salad")
    assert {source.vendor_id for source in response.sources} == {vendor.id}


def test_picker_filters_both_reviews_and_directory_by_explicit_location_and_diet(session):
    vendors = [
        Vendor(name="North Salad", location="North Spine", category="Salad shop", vegetarian=True),
        Vendor(name="South Salad", location="South Spine", category="Salad shop", vegetarian=True),
        Vendor(name="Unknown Diet Salad", location="North Spine", category="Salad shop", vegetarian=None),
    ]
    session.add_all(vendors)
    session.commit()
    reviews = [([1.0, 0.0], KnowledgeResult(source_type="google_review", source_id=str(vendor.id),
                vendor_id=vendor.id, content="Fresh salad for lunch.", metadata={})) for vendor in vendors]
    prompts = []
    service = ChatService(
        RecordingEmbedder(), FakeKnowledgeStore(items=reviews, vendor_names={vendor.id: vendor.name for vendor in vendors}),
        session=session, sql_store=PgSqlStore(session), generate=lambda prompt: prompts.append(prompt) or "Try North Salad [1].",
        query_resolver=resolve_picker_food,
    )
    response = service.answer("Where can I eat the food I just picked near North Spine? Only vegetarian places please.", food_pick="Salad")
    assert {source.vendor_id for source in response.sources} == {vendors[0].id}
    assert "South Salad" not in prompts[0]
    assert "Unknown Diet Salad" not in prompts[0]


def test_picker_with_no_supported_matches_does_not_invent_a_vendor(session):
    session.add(Vendor(name="AcaiGuru", category="Dessert shop"))
    session.commit()

    def must_not_generate(_prompt):
        pytest.fail("An unrelated directory must not be used to invent a match")

    service = ChatService(RecordingEmbedder(), FakeKnowledgeStore(items=[]), session=session,
                          sql_store=PgSqlStore(session), generate=must_not_generate, query_resolver=resolve_picker_food)
    response = service.answer("where can i find the food i jus picked", food_pick="Salad")
    assert "confirmed campus match" in response.answer
    assert response.sources == []
