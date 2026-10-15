import pytest
from pydantic import ValidationError

from app.api import dependencies
from app.main import app
from app.schemas.chat import ChatRequest
from app.services.chat import ChatService
from app.services.retrieval import FakeKnowledgeStore
from app.services.retrieval import KnowledgeResult
from app.services.sql_search import PgSqlStore
from app.models import Vendor


class RecordingEmbedder:
    def __init__(self):
        self.questions = []

    def embed(self, questions):
        self.questions.extend(questions)
        return [[1.0, 0.0] for _ in questions]


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
    service.answer("What did I roll?", food_pick=food)
    assert rewrites == [("What did I roll?", [], food)]
    assert embedder.questions[0] == f"I want {food} food"
    assert f'"latest_food_pick": "{food}"' in prompts[0]
    assert "Question: What did I roll?" in prompts[0]
    assert "User: " not in prompts[0]

    service.answer("What did I roll?")
    assert "latest_food_pick" not in prompts[1]
    assert embedder.questions[1] == "What did I roll?"


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
def test_picker_recommendations_include_the_directory_with_correct_citation_numbers(session, food, name):
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
    assert result.sources[0].vendor_id == unrelated.id
    citation = next(index for index, source in enumerate(result.sources, start=1)
                    if source.source_type == "vendor" and source.vendor_id == matching.id)
    assert f"[{citation}] {name}" in prompts[0]
    assert any(source.source_type == "vendor" and source.vendor_id == unrelated.id for source in result.sources)
    assert f'"latest_food_pick": "{food}"' in prompts[0]
