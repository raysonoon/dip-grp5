import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from google.genai import errors
from pydantic import SecretStr

from app.api import dependencies
from app.core.config import settings
from app.main import app
from app.models import Vendor
from app.services.chat import ChatService
from app.services.chat_client import create_chat_client
from app.services.intent_router import IntentRouter
from app.services.retrieval import FakeKnowledgeStore, KnowledgeResult
from app.services.sql_search import PgSqlStore


def unavailable():
    return errors.ServerError(503, {
        "error": {"message": "private provider diagnostic", "status": "UNAVAILABLE"},
    })


def stream_events(response):
    return [
        (block.splitlines()[0].removeprefix("event: "),
         json.loads(block.splitlines()[1].removeprefix("data: ")))
        for block in response.text.strip().split("\n\n")
    ]


class LocalEmbedder:
    def embed(self, texts):
        return [[1.0, 0.0] for _ in texts]


@pytest.mark.parametrize("failure", [unavailable, lambda: TimeoutError("slow model")])
def test_multi_vendor_lookup_returns_cited_facts_when_generation_fails(
    session, client, failure,
):
    session.add_all([
        Vendor(name="Gelare", location="North Spine", unit_code="#01-01"),
        Vendor(name="Encik Tan", location="South Spine"),
        Vendor(name="Blue Ocean", location="Hall 14"),
        Vendor(name="Unrelated Vendor", location="Elsewhere"),
    ])
    session.commit()
    calls = []

    def fail_generation(**kwargs):
        calls.append(kwargs)
        raise failure()

    provider = SimpleNamespace(models=SimpleNamespace(
        generate_content_stream=fail_generation,
    ))
    service = ChatService(
        LocalEmbedder(), FakeKnowledgeStore(items=[]), client=provider,
        router=IntentRouter(session), sql_store=PgSqlStore(session), session=session,
    )
    app.dependency_overrides[dependencies.get_chat_service] = lambda: service
    response = client.post("/chat/stream", json={
        "question": "where is gelare, encik tan, blue ocean?",
    })
    assert response.status_code == 200
    events = stream_events(response)
    assert [event for event, _ in events] == ["delta", "sources"]
    answer, sources = events[0][1], events[1][1]
    assert "couldn't generate a full answer" in answer
    assert {source["vendor_name"] for source in sources} == {
        "Gelare", "Encik Tan", "Blue Ocean",
    }
    for index, source in enumerate(sources, start=1):
        assert source["location"] in answer
        assert f"[{index}]" in answer
    assert "#01-01" in answer
    assert "Unrelated Vendor" not in answer
    assert "private provider diagnostic" not in answer
    assert len(calls) == 1


def test_vector_fallback_keeps_review_excerpt_and_source():
    def fail(_prompt):
        raise unavailable()

    service = ChatService(
        LocalEmbedder(),
        FakeKnowledgeStore(items=[([1.0, 0.0], KnowledgeResult(
            source_type="internal_review", source_id="review-1", vendor_id=1,
            content="The noodles were good.", metadata={},
        ))], vendor_names={1: "Demo Vendor"}),
        generate=fail,
    )
    response = service.answer("What should I eat?")
    assert "Demo Vendor: The noodles were good. [1]" in response.answer
    assert response.sources[0].source_id == "review-1"


@pytest.mark.parametrize("empty", [False, True])
def test_missing_or_empty_generation_returns_retry_message_without_evidence(empty):
    def generate(_prompt):
        if not empty:
            raise unavailable()
        yield "   "

    service = ChatService(
        LocalEmbedder(), FakeKnowledgeStore(items=[]), generate_stream=generate,
    )
    events = list(service.stream_answer("Hello!"))
    assert events == [
        ("delta", "Foodie is temporarily unavailable. Please try again in a moment."),
        ("sources", []),
    ]


@pytest.mark.parametrize("partial", [False, True])
def test_route_ends_failed_stream_with_sanitized_error(client, partial):
    class BrokenService:
        def stream_answer(self, *_args, **_kwargs):
            if partial:
                yield "delta", "Partial answer"
            raise RuntimeError("private database diagnostic")

    app.dependency_overrides[dependencies.get_chat_service] = BrokenService
    events = stream_events(client.post("/chat/stream", json={"question": "Hello"}))
    assert events[-1] == ("error", {"code": "chat_unavailable"})
    assert "sources" not in [event for event, _ in events]
    assert "private database diagnostic" not in str(events)


def test_failure_after_first_generated_chunk_is_not_completed(client):
    def generate(_prompt):
        yield "First part"
        raise unavailable()

    service = ChatService(
        LocalEmbedder(), FakeKnowledgeStore(items=[]), generate_stream=generate,
    )
    app.dependency_overrides[dependencies.get_chat_service] = lambda: service
    events = stream_events(client.post("/chat/stream", json={"question": "Hello"}))
    assert events == [
        ("delta", "First part"), ("error", {"code": "chat_unavailable"}),
    ]


def test_interactive_clients_disable_sdk_retry_backoff(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", SecretStr("test-key"))
    monkeypatch.setattr(settings, "chat_request_timeout_ms", 1234)
    with patch("app.services.chat_client.genai.Client") as client:
        create_chat_client()
    options = client.call_args.kwargs["http_options"]
    assert options.timeout == 1234
    assert options.retry_options.attempts == 1


def test_interactive_embedder_reuses_the_bounded_client():
    provider = object()
    with patch.object(dependencies, "_get_genai_client", return_value=provider):
        with patch.object(dependencies, "GoogleEmbedder") as embedder:
            dependencies.get_embedder.__wrapped__()
    assert embedder.call_args.kwargs["client"] is provider
    assert embedder.call_args.kwargs["max_retries"] == 1
