import json
from types import SimpleNamespace

import pytest

from app.schemas.chat import ChatHistoryMessage
from app.services.llm_routing import (
    _parse_filter_json,
    build_filter_extractor,
    build_question_rewriter,
    build_query_resolver,
)
from app.services.query_resolution import ResolvedQuery


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


def test_build_question_rewriter_prompt_describes_list_and_typo_rules() -> None:
    client = _FakeClient("Are McDonald's, Subway, and Popeyes halal?")
    rewrite = build_question_rewriter(client)
    history = [
        ChatHistoryMessage(
            role="assistant",
            content="Halal at North Spine: McDonald's, Subway, Popeyes.",
        ),
    ]

    result = rewrite("which of those is halal", history)

    assert result == "Are McDonald's, Subway, and Popeyes halal?"
    _, prompt = client.models.calls[0]
    assert "exact vendor names" in prompt
    assert "including misspellings" in prompt
    assert "halaal" in prompt
    assert "previously recommended food vendors" in prompt


@pytest.mark.parametrize(
    "text",
    [
        "Sure, here is the rewritten question: Which of those is halal?",
        '"Which of those is halal?"',
        "```\nWhich of those is halal?\n```",
        "```text\nWhich of those is halal?\n```",
    ],
)
def test_build_question_rewriter_cleans_wrappers(text: str) -> None:
    client = _FakeClient(text)
    rewrite = build_question_rewriter(client)

    assert rewrite("which of those is halal", []) == "Which of those is halal?"


@pytest.mark.parametrize(
    "text",
    [
        "Which of those is halal?\nIt refers to the previous list.",
        '{"question": "Which of those is halal?"}',
        "Rewrite the user's latest question: Which of those is halal?",
    ],
)
def test_build_question_rewriter_rejects_unsafe_output(text: str) -> None:
    client = _FakeClient(text)
    rewrite = build_question_rewriter(client)

    assert rewrite("which of those is halal", []) == ""


def test_build_question_rewriter_removes_list_reference_meta() -> None:
    client = _FakeClient(
        "Which of the previously recommended food vendors at North Spine "
        "are Halal?"
    )
    rewrite = build_question_rewriter(client)

    assert (
        rewrite("which of those is halal", [])
        == "Which of the food vendors at North Spine are Halal?"
    )


def test_build_question_rewriter_preserves_vendor_name_typos() -> None:
    client = _FakeClient("Is paiks bibimm halal?")
    rewrite = build_question_rewriter(client)

    assert rewrite("is paiks bibimm halal", []) == "Is paiks bibimm halal?"


def test_build_filter_extractor_parses_vendor_names() -> None:
    client = _FakeClient(
        '{"vendor_names": ["Gelare", "Encik Tan", "Blue Ocean"]}'
    )
    extract = build_filter_extractor(client, model="test-model")

    filters = extract("Where is Gelare, Encik Tan and Blue Ocean?")

    assert filters.vendor_names == ["Gelare", "Encik Tan", "Blue Ocean"]
    assert filters.has_constraints is True
    _, prompt = client.models.calls[0]
    assert "vendor_names (array of merchant/vendor name strings)" in prompt
    assert "proper business, brand, stall, cafe, or restaurant" in prompt
    assert "fixed list of examples" in prompt


def test_build_filter_extractor_treats_popeyes_as_vendor_not_cuisine() -> None:
    client = _FakeClient('{"vendor_names": ["Popeyes"], "location": "NTU"}')
    extract = build_filter_extractor(client)

    filters = extract("Where is Popeyes in NTU?")

    assert filters.vendor_names == ["Popeyes"]
    assert filters.cuisine is None
    assert filters.location == "NTU"


def test_parse_filter_json_cleans_deduplicates_and_bounds_vendor_names() -> None:
    names: list[object] = [
        "  Gelare  ",
        "gelare",
        "Blue   Ocean",
        "",
        "   ",
        123,
        None,
        "x" * 101,
    ]
    names.extend(f"Vendor {index}" for index in range(25))

    filters = _parse_filter_json(
        '{"vendor_names": ' + json.dumps(names) + "}"
    )

    assert filters.vendor_names is not None
    assert filters.vendor_names[:2] == ["Gelare", "Blue Ocean"]
    assert len(filters.vendor_names) == 20
    assert all(isinstance(name, str) and name for name in filters.vendor_names)
    assert all(len(name) <= 100 for name in filters.vendor_names)


def test_parse_filter_json_rejects_non_array_or_empty_vendor_names() -> None:
    assert _parse_filter_json('{"vendor_names": "Popeyes"}').vendor_names is None
    assert _parse_filter_json('{"vendor_names": ["", 42]}').vendor_names is None


def test_parse_filter_json_preserves_existing_cuisine_behavior() -> None:
    filters = _parse_filter_json(
        '{"cuisine": " Korean ", "location": " North Spine "}'
    )

    assert filters.cuisine == "Korean"
    assert filters.location == "North Spine"
    assert filters.vendor_names is None


@pytest.mark.parametrize(
    "cuisine",
    [
        "Previously Recommended",
        "previously recommended",
        "Listed",
        "the above",
        "Suggested food",
        "those",
    ],
)
def test_parse_filter_json_rejects_list_reference_cuisines(
    cuisine: str,
) -> None:
    filters = _parse_filter_json(
        json.dumps({"cuisine": cuisine})
    )

    assert filters.cuisine is None


def test_parse_filter_json_rejects_unsupported_filter_enums() -> None:
    filters = _parse_filter_json(
        '{"budget": "free", "open_hours": "whenever", "sort": "random"}'
    )

    assert filters.budget is None
    assert filters.open_hours is None
    assert filters.sort is None
    assert filters.has_constraints is False


def test_parse_filter_json_normalizes_supported_filter_enums() -> None:
    filters = _parse_filter_json(
        '{"budget": "CHEAP", "open_hours": "Sunday", "sort": "PRICE_ASC"}'
    )

    assert filters.budget == "cheap"
    assert filters.open_hours == "sunday"
    assert filters.sort == "price_asc"


def test_parse_filter_json_bounds_top_n_to_safe_positive_integers() -> None:
    assert _parse_filter_json('{"top_n": 5}').top_n == 5
    assert _parse_filter_json('{"top_n": "100"}').top_n == 100
    assert _parse_filter_json('{"top_n": "００１"}').top_n == 1

    for unsafe_value in (-5, 0, True, 1.5, "3.5", 101, 999999999):
        filters = _parse_filter_json(
            '{"top_n": ' + json.dumps(unsafe_value) + "}"
        )
        assert filters.top_n is None


def test_parse_filter_json_rejects_huge_top_n_without_raising() -> None:
    for digits in (
        "9" * 4301,
        "9" * 10_000,
        "９" * 10_000,
    ):
        filters = _parse_filter_json(
            '{"top_n": ' + json.dumps(digits) + "}"
        )
        assert filters.top_n is None

    leading_zeroes = "0" * 10_000 + "5"
    filters = _parse_filter_json(
        '{"top_n": ' + json.dumps(leading_zeroes) + "}"
    )
    assert filters.top_n == 5


def test_parse_filter_json_rejects_non_string_query_kind_without_raising(
) -> None:
    for value in ([], {}, 42, True, None):
        filters = _parse_filter_json(
            '{"query_kind": ' + json.dumps(value) + "}"
        )
        assert filters.query_kind == "list"


def test_semantic_resolver_uses_json_schema_and_actual_context():
    calls = []
    payload = {"target": "food", "reference": "picker", "question": "Where can I find salad?", "food_type": "Salad"}

    def generate_content(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(text=json.dumps(payload))

    resolve = build_query_resolver(SimpleNamespace(models=SimpleNamespace(generate_content=generate_content)), model="test-model")
    result = resolve("那去哪儿能吃到？", [ChatHistoryMessage(role="assistant", content="Earlier you drew Pizza")],
                     food_pick="Salad", vendors=[(2, "The Crowded Bowl")])
    assert result.target == "food" and result.reference == "picker"
    schema = calls[0]["config"].response_schema
    assert "food" in schema["properties"]["target"]["enum"]
    assert "vendor_names" in schema["properties"] and "food_type" in schema["properties"]
    assert "additionalProperties" not in json.dumps(schema)
    assert calls[0]["config"].response_mime_type == "application/json"
    assert '"current_picker_food": "Salad"' in calls[0]["contents"]
    assert "那去哪儿能吃到？" in calls[0]["contents"]
    assert "The Crowded Bowl" in calls[0]["contents"]


def test_semantic_resolver_fails_closed_on_invalid_json_or_provider_error():
    for response in ["Salad in NTU? Please recommend places", '{"target":"vendor","reference":"picker","question":"Where?","vendor_names":["Salad"]}']:
        client = SimpleNamespace(models=SimpleNamespace(generate_content=lambda **kwargs: SimpleNamespace(text=response)))
        assert build_query_resolver(client)("Where?", [], food_pick="Salad", vendors=[]) is None

    def fail(**kwargs):
        raise TimeoutError("provider unavailable")

    client = SimpleNamespace(models=SimpleNamespace(generate_content=fail))
    assert build_query_resolver(client)("Where?", [], food_pick="Salad", vendors=[]) is None
