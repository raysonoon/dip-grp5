import pytest

from app.services.chat import (
    DEFAULT_SYSTEM_PROMPT,
    EMPTY_CONTEXT,
    build_prompt,
    format_context,
)
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
    ) == prompt


def test_build_prompt_uses_custom_template() -> None:
    template = "Question: {user_question}\n\nEvidence:\n{context}"
    prompt = build_prompt("q", "c", template=template)
    assert prompt == "Question: q\n\nEvidence:\nc"


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