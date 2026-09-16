from app.services.structured_filters import (
    SIMILARITY_THRESHOLD,
    extract_structured_filters,
    extract_structured_filters_llm,
)


def test_threshold_constant() -> None:
    assert SIMILARITY_THRESHOLD == 0.88


def test_dietary_filters() -> None:
    filters = extract_structured_filters("Where can I find halal food?")
    assert filters.halal is True
    assert filters.vegetarian is None


def test_vegetarian_and_vegan() -> None:
    assert extract_structured_filters("vegan food please").vegetarian is True
    assert extract_structured_filters("vegetarian stall").vegetarian is True


def test_cuisine_and_location() -> None:
    filters = extract_structured_filters(
        "Which Korean food places are near North Spine?"
    )
    assert filters.cuisine == "Korean"
    assert filters.location == "North Spine"


def test_budget() -> None:
    assert extract_structured_filters("cheap food").budget == "cheap"
    assert extract_structured_filters("expensive meal").budget == "expensive"


def test_open_hours() -> None:
    assert extract_structured_filters("open after 8pm").open_hours == "after 20:00"
    assert extract_structured_filters("open on Sunday").open_hours == "sunday"


def test_count_query_kind() -> None:
    filters = extract_structured_filters("How many halal places are there?")
    assert filters.query_kind == "count"
    assert filters.halal is True


def test_rank_query_kind_and_top_n() -> None:
    filters = extract_structured_filters("top 10 best stalls")
    assert filters.query_kind == "rank"
    assert filters.top_n == 10
    assert filters.sort == "rating"


def test_list_default() -> None:
    filters = extract_structured_filters("Where can I get Korean food?")
    assert filters.query_kind == "list"
    assert filters.sort is None


def test_llm_fallback_returns_empty_without_extractor() -> None:
    filters = extract_structured_filters_llm("anything", extractor=None)
    assert filters.query_kind == "list"
    assert filters.has_constraints is False


def test_llm_fallback_uses_extractor() -> None:
    custom = extract_structured_filters("halal food")
    filters = extract_structured_filters_llm("anything", extractor=lambda q: custom)
    assert filters.halal is True