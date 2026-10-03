import pytest

from app.services.chat import (
    DEFAULT_SYSTEM_PROMPT,
    EMPTY_CONTEXT,
    build_contextual_question,
    build_prompt,
    format_conversation_history,
    format_context,
)
from app.schemas.chat import ChatHistoryMessage
from app.services.retrieval import KnowledgeResult


def _result(source_id: str, content: str, vendor_id: int = 1) -> KnowledgeResult:
    return KnowledgeResult(
        source_type="internal_review",
        source_id=source_id,
        vendor_id=vendor_id,
        content=content,
        metadata={},
    )


def test_build_prompt_uses_default_template() -> None:
    prompt = build_prompt("Is halal food available?", "Context text here.")
    assert "Is halal food available?" in prompt
    assert "Context text here." in prompt
    assert "{user_question}" not in prompt
    assert "{context}" not in prompt
    assert DEFAULT_SYSTEM_PROMPT.format(
        user_question="Is halal food available?",
        context="Context text here.",
        conversation_history="(no earlier messages in this session)",
    ) == prompt


def test_default_prompt_allows_identity_and_small_talk_without_context() -> None:
    prompt = build_prompt("Are you Gemini?", EMPTY_CONTEXT)
    assert "powered by Google's Gemini model" in prompt
    assert "identity or capabilities" in prompt
    assert "answer normally without requiring supporting context" in prompt
    assert "rather than inventing an answer" in prompt


def test_build_prompt_uses_custom_template() -> None:
    template = "Question: {user_question}\n\nEvidence:\n{context}"
    prompt = build_prompt("q", "c", template=template)
    assert prompt == "Question: q\n\nEvidence:\nc"


def test_build_prompt_adds_history_to_custom_template() -> None:
    history = [ChatHistoryMessage(role="user", content="Tell me about Canteen 2")]
    prompt = build_prompt(
        "When does it close?",
        "hours context",
        template="Question: {user_question}\n\nEvidence:\n{context}",
        history=history,
    )
    assert "User: Tell me about Canteen 2" in prompt
    assert "Question: When does it close?" in prompt


def test_format_conversation_history_keeps_five_messages_per_role() -> None:
    history = [
        message
        for index in range(7)
        for message in (
            ChatHistoryMessage(role="user", content=f"user-{index}"),
            ChatHistoryMessage(role="assistant", content=f"assistant-{index}"),
        )
    ]
    rendered = format_conversation_history(history)
    assert "user-0" not in rendered
    assert "assistant-1" not in rendered
    assert "user-2" in rendered
    assert "assistant-6" in rendered


def test_contextual_question_prioritizes_current_and_keeps_two_recent_turns() -> None:
    history = [
        message
        for index in range(3)
        for message in (
            ChatHistoryMessage(role="user", content=f"user-{index}"),
            ChatHistoryMessage(role="assistant", content=f"assistant-{index}"),
        )
    ]

    rendered = build_contextual_question("current question", history)

    assert rendered.startswith(
        "=== CURRENT QUESTION (use this to determine intent) ===\ncurrent question"
    )
    assert "user-0" not in rendered
    assert "assistant-0" not in rendered
    assert "--- TURN 1 ---\nUser: user-1\nFoodie: assistant-1" in rendered
    assert "--- TURN 2 ---\nUser: user-2\nFoodie: assistant-2" in rendered


def test_build_prompt_rejects_unknown_placeholders() -> None:
    with pytest.raises(KeyError):
        build_prompt("q", "c", template="{unexpected}")


def test_format_context_empty() -> None:
    assert format_context([]) == EMPTY_CONTEXT


def test_format_context_numbers_sources() -> None:
    results = [
        _result("1", "first review"),
        _result("2", "second review"),
    ]
    rendered = format_context(results)
    assert rendered == "[1] (internal_review): first review\n\n[2] (internal_review): second review"


def test_format_context_includes_vendor_names() -> None:
    results = [
        _result("1", "best mala ever", vendor_id=1),
        _result("2", "great noodles", vendor_id=2),
    ]
    rendered = format_context(results, vendor_names={1: "A Hot Hideout", 2: "Noodle House"})
    assert "A Hot Hideout" in rendered
    assert "Noodle House" in rendered
    assert rendered == (
        "[1] (internal_review) A Hot Hideout: best mala ever\n\n"
        "[2] (internal_review) Noodle House: great noodles"
    )


def test_format_context_omits_unknown_vendor() -> None:
    results = [_result("1", "best mala ever")]
    rendered = format_context(results, vendor_names={})
    assert "[1] (internal_review): best mala ever" == rendered
