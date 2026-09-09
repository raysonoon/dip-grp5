from fastapi.testclient import TestClient

from app.api import dependencies
from app.main import app
from app.schemas.chat import ChatResponse, ChatSource
from app.services.chat import ChatService
from app.services.embedding import Embedder
from app.services.retrieval import (
    FakeKnowledgeStore,
    KnowledgeResult,
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


class FakeChatService:
    def __init__(self, response: ChatResponse) -> None:
        self._response = response

    def answer(self, question: str) -> ChatResponse:
        self.question = question
        return self._response


def _fake_response() -> ChatResponse:
    return ChatResponse(
        answer="Try the chicken rice at Demo Vendor 1.",
        sources=[
            ChatSource(
                source_type="internal_review",
                source_id="1",
                vendor_id=1,
                vendor_name="Demo Vendor 1",
                excerpt="Great chicken rice, generous portion.",
            )
        ],
    )


def test_chat_route_returns_answer_and_sources(client: TestClient) -> None:
    fake_service = FakeChatService(_fake_response())
    app.dependency_overrides[dependencies.get_chat_service] = lambda: fake_service
    try:
        response = client.post("/chat", json={"question": "What should I eat?"})
        assert response.status_code == 200
        payload = response.json()
        assert payload["answer"] == "Try the chicken rice at Demo Vendor 1."
        assert payload["sources"][0]["vendor_name"] == "Demo Vendor 1"
        assert fake_service.question == "What should I eat?"
    finally:
        app.dependency_overrides.clear()


def test_chat_route_rejects_blank_question(client: TestClient) -> None:
    response = client.post("/chat", json={"question": "   "})
    assert response.status_code == 422


def test_chat_service_orchestrates_retrieval() -> None:
    store = FakeKnowledgeStore(
        items=[
            (
                _vector(0.9),
                KnowledgeResult(
                    source_type="google_review",
                    source_id="g1",
                    vendor_id=1,
                    content="noodles are the best here",
                    metadata={"rating": 5},
                ),
            ),
            (
                _vector(0.1),
                KnowledgeResult(
                    source_type="internal_review",
                    source_id="1",
                    vendor_id=1,
                    content="great chicken rice",
                    metadata={"rating": 4.0},
                ),
            ),
        ],
        vendor_names={1: "Demo Vendor 1"},
    )
    captured: dict[str, str] = {}

    def fake_generate(prompt: str) -> str:
        captured["prompt"] = prompt
        return "great chicken rice"

    service = ChatService(
        FakeEmbedder(),
        store,
        generate=fake_generate,
    )

    response = service.answer("what is the best food?")

    assert response.answer == "great chicken rice"
    assert [source.source_id for source in response.sources] == ["1", "g1"]
    assert response.sources[0].vendor_name == "Demo Vendor 1"
    assert "what is the best food?" in captured["prompt"]
    assert "great chicken rice" in captured["prompt"]
    assert "Demo Vendor 1" in captured["prompt"]