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
from app.services.chat import ChatService, _stream_retry_delay
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
    session, client, failure, monkeypatch,
):
    monkeypatch.setattr(settings, "chat_retry_initial_delay_ms", 0)
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
    assert len(calls) == settings.chat_retry_attempts


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


def _chunks(*texts):
    def stream():
        for text in texts:
            yield SimpleNamespace(text=text)
    return stream


def _fails_after(error, *texts):
    def stream():
        for text in texts:
            yield SimpleNamespace(text=text)
        raise error
    return stream


class ScriptedProvider:
    """Provider double that replays one scripted stream per call."""

    def __init__(self, *steps):
        self._steps = list(steps)
        self.calls = 0
        self.models = SimpleNamespace(generate_content_stream=self._stream)

    def _stream(self, **_kwargs):
        self.calls += 1
        yield from self._steps[min(self.calls - 1, len(self._steps) - 1)]()


def _scripted_service(provider):
    return ChatService(
        LocalEmbedder(), FakeKnowledgeStore(items=[]), client=provider,
    )


def test_transient_failure_before_the_first_token_is_retried(monkeypatch):
    monkeypatch.setattr(settings, "chat_retry_initial_delay_ms", 0)
    provider = ScriptedProvider(_fails_after(unavailable()), _chunks("Answer"))
    events = list(
        _scripted_service(provider).stream_answer("Which vendors are halal?")
    )
    assert events == [("delta", "Answer"), ("sources", [])]
    assert provider.calls == 2


def test_failure_after_the_first_token_is_not_replayed():
    provider = ScriptedProvider(_fails_after(unavailable(), "Partial"))
    with pytest.raises(errors.ServerError):
        list(_scripted_service(provider).stream_answer("Which vendors are halal?"))
    assert provider.calls == 1


def test_permanent_failure_is_not_retried():
    provider = ScriptedProvider(_fails_after(errors.ClientError(400, {
        "error": {"message": "bad request", "status": "INVALID_ARGUMENT"},
    })))
    with pytest.raises(errors.ClientError):
        list(_scripted_service(provider)._generate_stream("prompt"))
    assert provider.calls == 1


def test_stream_gives_up_after_the_attempt_limit(monkeypatch):
    monkeypatch.setattr(settings, "chat_retry_initial_delay_ms", 0)
    monkeypatch.setattr(settings, "chat_retry_attempts", 2)
    provider = ScriptedProvider(_fails_after(unavailable()))
    with pytest.raises(errors.ServerError):
        list(_scripted_service(provider)._generate_stream("prompt"))
    assert provider.calls == 2


@pytest.mark.parametrize(
    ("scenario", "expected"),
    [
        ({"attempt": 1, "attempts": 3, "emitted": False, "elapsed": 0.2}, 0.25),
        ({"attempt": 2, "attempts": 3, "emitted": False, "elapsed": 0.2}, 0.5),
        ({"attempt": 1, "attempts": 3, "emitted": True, "elapsed": 0.2}, None),
        ({"attempt": 3, "attempts": 3, "emitted": False, "elapsed": 0.2}, None),
        ({"attempt": 1, "attempts": 3, "emitted": False, "elapsed": 20.0}, None),
    ],
)
def test_stream_retry_delay(monkeypatch, scenario, expected):
    monkeypatch.setattr(settings, "chat_retry_initial_delay_ms", 250)
    monkeypatch.setattr(settings, "chat_retry_max_delay_ms", 2_000)
    assert _stream_retry_delay(
        unavailable(), timeout_seconds=20.0, **scenario
    ) == expected


def test_stream_retry_delay_is_capped(monkeypatch):
    monkeypatch.setattr(settings, "chat_retry_initial_delay_ms", 1_000)
    monkeypatch.setattr(settings, "chat_retry_max_delay_ms", 1_500)
    assert _stream_retry_delay(
        unavailable(), attempt=2, attempts=5, emitted=False,
        elapsed=0.1, timeout_seconds=20.0,
    ) == 1.5


def test_interactive_client_retries_transient_failures_with_short_backoff(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", SecretStr("test-key"))
    monkeypatch.setattr(settings, "chat_request_timeout_ms", 12_000)
    monkeypatch.setattr(settings, "chat_retry_attempts", 3)
    monkeypatch.setattr(settings, "chat_retry_initial_delay_ms", 250)
    monkeypatch.setattr(settings, "chat_retry_max_delay_ms", 2_000)
    with patch("app.services.chat_client.genai.Client") as client:
        create_chat_client()
    options = client.call_args.kwargs["http_options"]
    assert options.timeout == 12_000
    assert options.retry_options.attempts == 3
    assert options.retry_options.initial_delay == 0.25
    assert options.retry_options.max_delay == 2.0


def test_interactive_embedder_reuses_the_bounded_client():
    provider = object()
    with patch.object(dependencies, "_get_genai_client", return_value=provider):
        with patch.object(dependencies, "GoogleEmbedder") as embedder:
            dependencies.get_embedder.__wrapped__()
    assert embedder.call_args.kwargs["client"] is provider
    assert embedder.call_args.kwargs["max_retries"] == 1
