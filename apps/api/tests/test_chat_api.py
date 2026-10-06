from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.api import dependencies
from app.main import app
from app.models import RedditComment
from app.schemas.chat import ChatHistoryMessage, ChatRequest, ChatResponse, ChatSource
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

    def answer(
        self,
        question: str,
        *,
        history: list[ChatHistoryMessage] | None = None,
    ) -> ChatResponse:
        self.question = question
        self.history = history
        return self._response

    def stream_answer(
        self,
        question: str,
        *,
        history: list[ChatHistoryMessage] | None = None,
    ):
        self.question = question
        self.history = history
        midpoint = len(self._response.answer) // 2
        yield "delta", self._response.answer[:midpoint]
        yield "delta", self._response.answer[midpoint:]
        yield "sources", self._response.sources


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


def test_chat_stream_route_returns_deltas_then_sources(client: TestClient) -> None:
    fake_service = FakeChatService(_fake_response())
    app.dependency_overrides[dependencies.get_chat_service] = lambda: fake_service
    app.dependency_overrides[dependencies.get_current_user] = lambda: object()
    try:
        response = client.post(
            "/chat/stream",
            headers={"X-Dev-User-Id": "1"},
            json={
                "session_id": "session-a",
                "question": "What should I eat?",
                "history": [
                    {"role": "user", "content": "I want noodles."},
                    {"role": "assistant", "content": "Try Demo Vendor 1."},
                ],
            },
        )
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        blocks = response.text.strip().split("\n\n")
        assert blocks[0].startswith("event: delta\n")
        assert blocks[1].startswith("event: delta\n")
        assert blocks[2].startswith("event: sources\n")
        assert '"vendor_name": "Demo Vendor 1"' in blocks[2]
        assert fake_service.question == "What should I eat?"
        assert [message.content for message in fake_service.history] == [
            "I want noodles.",
            "Try Demo Vendor 1.",
        ]
    finally:
        app.dependency_overrides.clear()


def test_chat_route_rejects_blank_question(client: TestClient) -> None:
    app.dependency_overrides[dependencies.get_current_user] = lambda: object()
    try:
        response = client.post(
            "/chat/stream",
            headers={"X-Dev-User-Id": "1"},
            json={"session_id": "session-a", "question": "   "},
        )
        assert response.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_chat_route_accepts_missing_session_id(client: TestClient) -> None:
    fake_service = FakeChatService(_fake_response())
    app.dependency_overrides[dependencies.get_chat_service] = lambda: fake_service
    app.dependency_overrides[dependencies.get_current_user] = lambda: object()
    try:
        response = client.post(
            "/chat/stream",
            headers={"X-Dev-User-Id": "1"},
            json={"question": "What should I eat?"},
        )
        assert response.status_code == 200
    finally:
        app.dependency_overrides.clear()


def test_chat_request_accepts_null_and_normalizes_supplied_session_id() -> None:
    assert ChatRequest(question="What should I eat?").session_id is None
    assert (
        ChatRequest(
            session_id=None,
            question="What should I eat?",
        ).session_id
        is None
    )
    assert (
        ChatRequest(
            session_id="  session-a  ",
            question="What should I eat?",
        ).session_id
        == "session-a"
    )


def test_chat_route_drops_oldest_messages_per_role(client: TestClient) -> None:
    fake_service = FakeChatService(_fake_response())
    app.dependency_overrides[dependencies.get_chat_service] = lambda: fake_service
    app.dependency_overrides[dependencies.get_current_user] = lambda: object()
    history = []
    for index in range(7):
        history.extend(
            [
                {"role": "user", "content": f"user-{index}"},
                {"role": "assistant", "content": f"assistant-{index}"},
            ]
        )
    try:
        response = client.post(
            "/chat/stream",
            headers={"X-Dev-User-Id": "1"},
            json={
                "session_id": "session-a",
                "question": "follow up",
                "history": history,
            },
        )
        assert response.status_code == 200
        assert [message.content for message in fake_service.history] == [
            item
            for index in range(2, 7)
            for item in (f"user-{index}", f"assistant-{index}")
        ]
    finally:
        app.dependency_overrides.clear()


def test_legacy_chat_route_is_removed(client: TestClient) -> None:
    response = client.post("/chat", json={"question": "What should I eat?"})
    assert response.status_code == 404


def test_chat_stream_requires_dev_user_header(client: TestClient) -> None:
    response = client.post(
        "/chat/stream",
        json={"question": "What should I eat?"},
    )
    assert response.status_code == 401


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


def test_chat_service_streams_each_generated_chunk_before_sources() -> None:
    captured: dict[str, str] = {}

    def fake_stream(prompt: str):
        captured["prompt"] = prompt
        yield "Try "
        yield "Demo Vendor 1."

    service = ChatService(
        FakeEmbedder(),
        FakeKnowledgeStore(items=[]),
        generate_stream=fake_stream,
    )

    events = list(service.stream_answer("What should I eat?"))

    assert events[:-1] == [
        ("delta", "Try "),
        ("delta", "Demo Vendor 1."),
    ]
    assert events[-1] == ("sources", [])
    assert "What should I eat?" in captured["prompt"]


def test_chat_service_uses_history_for_follow_up_prompt_and_retrieval() -> None:
    embedded: list[str] = []

    class CapturingEmbedder(FakeEmbedder):
        def embed(self, texts: list[str]) -> list[list[float]]:
            embedded.extend(texts)
            return super().embed(texts)

    captured: dict[str, str] = {}
    service = ChatService(
        CapturingEmbedder(),
        FakeKnowledgeStore(items=[]),
        generate=lambda prompt: captured.setdefault("prompt", prompt),
        rewrite_llm=lambda _question, _history: "What time does Quad Cafe close?",
    )
    history = [
        ChatHistoryMessage(role="user", content="Tell me about Quad Cafe."),
        ChatHistoryMessage(
            role="assistant",
            content="Quad Cafe is in the School of Biological Sciences.",
        ),
    ]

    service.answer("What time does it close?", history=history)

    # Retrieval uses the resolved standalone question, not the history block.
    assert embedded[0] == "What time does Quad Cafe close?"
    # The prompt still carries the raw history and the raw current question.
    assert "User: Tell me about Quad Cafe." in captured["prompt"]
    assert "Foodie: Quad Cafe is in" in captured["prompt"]
    assert "Question: What time does it close?" in captured["prompt"]


def test_chat_service_builds_filters_from_current_question_only() -> None:
    captured: dict[str, str] = {}

    class CapturingFilterService(ChatService):
        def _build_vector_filters(self, question: str) -> dict:
            captured["filter_question"] = question
            return {}

    service = CapturingFilterService(
        FakeEmbedder(),
        FakeKnowledgeStore(items=[]),
        generate=lambda prompt: prompt,
    )
    history = [
        ChatHistoryMessage(
            role="user",
            content="Show me Reddit reviews for Quad Cafe.",
        ),
        ChatHistoryMessage(
            role="assistant",
            content="Here are Reddit reviews for Quad Cafe.",
        ),
    ]

    service.answer("Which places have halal food?", history=history)

    assert captured["filter_question"] == "Which places have halal food?"


def test_current_question_counts_toward_five_user_message_limit() -> None:
    captured: dict[str, str] = {}
    service = ChatService(
        FakeEmbedder(),
        FakeKnowledgeStore(items=[]),
        generate=lambda prompt: captured.setdefault("prompt", prompt),
    )
    history = [
        message
        for index in range(5)
        for message in (
            ChatHistoryMessage(role="user", content=f"old-user-{index}"),
            ChatHistoryMessage(role="assistant", content=f"old-assistant-{index}"),
        )
    ]

    service.answer("current-user-question", history=history)

    assert "old-user-0" not in captured["prompt"]
    assert "old-user-1" in captured["prompt"]
    assert captured["prompt"].count("current-user-question") == 1
    assert "old-assistant-0" in captured["prompt"]


def test_chat_service_resolves_reddit_permalinks_from_comments(session) -> None:
    session.add_all(
        [
            RedditComment(
                reddit_comment_id="reddit-linked",
                subreddit="NTU",
                thread_id="thread-1",
                thread_title="Food recommendations",
                comment_text="Try the noodles.",
                created_at=datetime.now(UTC),
                permalink="/r/NTU/comments/thread-1/comment/reddit-linked/",
            ),
            RedditComment(
                reddit_comment_id="reddit-unlinked",
                subreddit="NTU",
                thread_id="thread-2",
                thread_title="More food recommendations",
                comment_text="Try the rice.",
                created_at=datetime.now(UTC),
                permalink=None,
            ),
        ]
    )
    session.commit()
    store = FakeKnowledgeStore(
        items=[
            (
                _vector(0.1),
                KnowledgeResult(
                    source_type="reddit",
                    source_id="reddit-linked",
                    vendor_id=None,
                    content="Try the noodles.",
                    metadata={},
                ),
            ),
            (
                _vector(0.2),
                KnowledgeResult(
                    source_type="reddit",
                    source_id="reddit-unlinked",
                    vendor_id=None,
                    content="Try the rice.",
                    metadata={},
                ),
            ),
            (
                _vector(0.3),
                KnowledgeResult(
                    source_type="google_review",
                    source_id="google-1",
                    vendor_id=None,
                    content="Good portions.",
                    metadata={},
                ),
            ),
        ]
    )
    service = ChatService(
        FakeEmbedder(),
        store,
        generate=lambda _prompt: "Answer [1] [2] [3]",
        session=session,
    )

    response = service.answer("What should I eat?")
    sources = {source.source_id: source for source in response.sources}

    assert sources["reddit-linked"].permalink == (
        "/r/NTU/comments/thread-1/comment/reddit-linked/"
    )
    assert sources["reddit-unlinked"].permalink is None
    assert sources["google-1"].permalink is None
