import json
from types import SimpleNamespace

from app.schemas.chat import ChatHistoryMessage
from app.services.llm_routing import (
    _parse_filter_json,
    build_filter_extractor,
    build_question_rewriter,
)


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
