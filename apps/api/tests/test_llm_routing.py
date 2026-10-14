from types import SimpleNamespace

from app.schemas.chat import ChatHistoryMessage
from app.services.llm_routing import build_question_rewriter


class _FakeModels:
    def __init__(self, text: str) -> None:
        self._text = text
        self.calls: list[tuple[str, str]] = []

    def generate_content(self, model: str, contents: str) -> SimpleNamespace:
        self.calls.append((model, contents))
        return SimpleNamespace(text=self._text)


class _FakeClient:
    def __init__(self, text: str) -> None:
        self.models = _FakeModels(text)


def test_build_question_rewriter_resolves_followup() -> None:
    client = _FakeClient("What is the vibe at Quad Cafe?")
    rewrite = build_question_rewriter(client, model="test-model")
    history = [
        ChatHistoryMessage(role="user", content="tell me about quad cafe"),
        ChatHistoryMessage(role="assistant", content="Quad Cafe is central."),
    ]

    result = rewrite("what about the vibe there?", history)

    assert result == "What is the vibe at Quad Cafe?"
    _, prompt = client.models.calls[0]
    assert "what about the vibe there?" in prompt
    assert "tell me about quad cafe" in prompt
    assert "Quad Cafe is central." in prompt


def test_build_question_rewriter_strips_response() -> None:
    client = _FakeClient("  standalone question  \n")
    rewrite = build_question_rewriter(client)

    assert rewrite("it?", []) == "standalone question"


def test_build_question_rewriter_handles_empty_response() -> None:
    client = _FakeClient("")
    rewrite = build_question_rewriter(client)

    assert rewrite("it?", []) == ""
