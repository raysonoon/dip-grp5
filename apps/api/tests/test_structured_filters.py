import pytest

from app.services.structured_filters import (
    LOCATION_KEYWORDS,
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

    dietary_filters = extract_structured_filters("halal Japanese food")
    assert dietary_filters.halal is True
    assert dietary_filters.cuisine == "Japanese"


def test_cuisine_and_location_keywords_require_word_boundaries() -> None:
    assert extract_structured_filters("Indianapolis travel").cuisine is None
    assert extract_structured_filters("spaniel cafe").location is None
    assert extract_structured_filters("Japanese food").cuisine == "Japanese"


def test_generic_food_descriptions_do_not_become_cuisine_filters() -> None:
    cheapest = extract_structured_filters(
        "Which stall has the cheapest food?"
    )
    assert cheapest.cuisine is None
    assert cheapest.sort == "price_asc"

    late_night = extract_structured_filters("late night food")
    assert late_night.cuisine is None
    assert late_night.open_hours == "late"

    campus = extract_structured_filters("What's the best campus food?")
    assert campus.cuisine is None
    assert campus.sort == "rating"

    location = extract_structured_filters(
        "Where can I find North Spine food?"
    )
    assert location.cuisine is None
    assert location.location == "North Spine"

    assert extract_structured_filters("NTU food").cuisine is None


def test_open_ended_cuisine_phrases_still_use_structured_filter() -> None:
    assert (
        extract_structured_filters("Vietnamese food").cuisine
        == "Vietnamese"
    )
    assert (
        extract_structured_filters("Where can I find Middle Eastern food?")
        .cuisine
        == "Middle Eastern"
    )
    assert (
        extract_structured_filters("Show me South East Asian food").cuisine
        == "South East Asian"
    )


def test_other_filters_and_clauses_do_not_leak_into_cuisine() -> None:
    late = extract_structured_filters("late night Vietnamese food")
    assert late.cuisine == "Vietnamese"
    assert late.open_hours == "late"

    location = extract_structured_filters("North Spine Vietnamese food")
    assert location.cuisine == "Vietnamese"
    assert location.location == "North Spine"

    contrast = extract_structured_filters(
        "Vietnamese but not Chinese food"
    )
    assert contrast.cuisine == "Vietnamese"
    assert contrast.exclude_cuisine == "Chinese"


def test_all_location_keywords_avoid_prefix_collisions() -> None:
    for keyword, expected in LOCATION_KEYWORDS.items():
        filters = extract_structured_filters(f"food near {keyword}")
        assert filters.location == expected, keyword


def test_negated_cuisine_and_location_become_exclusions() -> None:
    cuisine = extract_structured_filters("not Indian food")
    assert cuisine.cuisine is None
    assert cuisine.exclude_cuisine == "Indian"
    assert cuisine.has_constraints is True

    location = extract_structured_filters("not near Hall 14")
    assert location.location is None
    assert location.exclude_location == "Hall 14"
    assert location.has_constraints is True


def test_budget() -> None:
    assert extract_structured_filters("cheap food").budget == "cheap"
    assert extract_structured_filters("expensive meal").budget == "expensive"
    assert extract_structured_filters("inexpensive meal").budget == "cheap"
    excluded = extract_structured_filters("not expensive")
    assert excluded.budget is None
    assert excluded.exclude_budget == "expensive"


def test_not_too_expensive_is_an_expensive_exclusion() -> None:
    filters = extract_structured_filters("not too expensive")

    assert filters.budget is None
    assert filters.exclude_budget == "expensive"
    assert filters.has_constraints is True


def test_explicit_dietary_negation() -> None:
    assert extract_structured_filters("non-halal food").halal is False
    assert extract_structured_filters("not halal").halal is False
    assert extract_structured_filters("without any halal food").halal is False
    assert extract_structured_filters("not vegetarian").vegetarian is False
    assert extract_structured_filters("non-vegetarian").vegetarian is False
    assert extract_structured_filters("not vegan").vegetarian is False


def test_open_hours() -> None:
    assert extract_structured_filters("open after 8pm").open_hours == "after 20:00"
    assert extract_structured_filters("open on Sunday").open_hours == "sunday"
    assert extract_structured_filters("open late").open_hours == "late"

    q042 = extract_structured_filters(
        "What's a good place near North Spine that's open late?"
    )
    assert q042.location == "North Spine"
    assert q042.open_hours == "late"


def test_negated_open_hours_become_exclusions() -> None:
    sunday = extract_structured_filters("not open on Sunday")
    assert sunday.open_hours is None
    assert sunday.exclude_open_hours == "sunday"
    assert sunday.has_constraints is True

    late = extract_structured_filters("not open after 8pm")
    assert late.open_hours is None
    assert late.exclude_open_hours == "after 20:00"


def test_positive_and_negative_constraints_are_kept_independently() -> None:
    filters = extract_structured_filters(
        "Indian but not Chinese near North Spine but not near Hall 14, "
        "cheap but not premium, open after 8pm but not Sunday"
    )

    assert filters.cuisine == "Indian"
    assert filters.exclude_cuisine == "Chinese"
    assert filters.location == "North Spine"
    assert filters.exclude_location == "Hall 14"
    assert filters.budget == "cheap"
    assert filters.exclude_budget == "expensive"
    assert filters.open_hours == "after 20:00"
    assert filters.exclude_open_hours == "sunday"


def test_count_query_kind() -> None:
    filters = extract_structured_filters("How many halal places are there?")
    assert filters.query_kind == "count"
    assert filters.halal is True


def test_rank_query_kind_and_top_n() -> None:
    filters = extract_structured_filters("top 10 best stalls")
    assert filters.query_kind == "rank"
    assert filters.top_n == 10
    assert filters.sort == "rating"


def test_rank_top_n_is_bounded_to_safe_positive_values() -> None:
    assert extract_structured_filters("top 0010 vendors").top_n == 10

    for question in (
        "top 0 vendors",
        "top -1 vendors",
        "top 101 vendors",
        "top " + ("9" * 1000) + " vendors",
    ):
        filters = extract_structured_filters(question)
        assert filters.query_kind == "list"
        assert filters.top_n is None


def test_rank_top_n_rejects_partial_numeric_tokens() -> None:
    for question in (
        "top 1.5 vendors",
        "top 10.0 vendors",
        "top 10,000 vendors",
        "top 1-2 vendors",
        "top 10/20 vendors",
        "top 10–20 vendors",
    ):
        filters = extract_structured_filters(question)
        assert filters.query_kind == "list", question
        assert filters.top_n is None, question


def test_rank_top_n_allows_sentence_punctuation() -> None:
    filters = extract_structured_filters("top 10, please")

    assert filters.query_kind == "rank"
    assert filters.top_n == 10


def test_list_default() -> None:
    filters = extract_structured_filters("Where can I get Korean food?")
    assert filters.query_kind == "list"
    assert filters.sort is None


def test_vendor_ids_default_none() -> None:
    filters = extract_structured_filters("Where can I find halal food?")
    assert filters.vendor_ids is None


def test_llm_fallback_returns_empty_without_extractor() -> None:
    filters = extract_structured_filters_llm("anything", extractor=None)
    assert filters.query_kind == "list"
    assert filters.has_constraints is False


def test_llm_fallback_uses_extractor() -> None:
    custom = extract_structured_filters("halal food")
    filters = extract_structured_filters_llm("anything", extractor=lambda q: custom)
    assert filters.halal is True


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("Vietnamese food", "Vietnamese"),
        ("Vietnamese food please", "Vietnamese"),
        ("any Vietnamese food?", "Vietnamese"),
        ("which Vietnamese food", "Vietnamese"),
        ("Where can I find Vietnamese food?", "Vietnamese"),
        ("I want Vietnamese food", "Vietnamese"),
        ("I'm looking for Vietnamese food", "Vietnamese"),
        ("Is there Vietnamese food?", "Vietnamese"),
        ("recommend Middle Eastern food", "Middle Eastern"),
        ("Where can I find South East Asian food?", "South East Asian"),
    ],
)
def test_explicit_cuisine_phrase_accepts_bare_and_verb_less_requests(
    question: str,
    expected: str,
) -> None:
    assert extract_structured_filters(question).cuisine == expected


@pytest.mark.parametrize(
    "question",
    [
        "NTU food",
        "campus food",
        "nearby food",
        "near food",
        "popular food",
        "trending food",
        "famous food",
        "favourite food",
        "favorite food",
        "great food",
        "worst food",
        "value food",
        "student food",
        "late night food",
        "cheapest food",
        "cheap food",
        "affordable food",
        "expensive food",
        "halal food",
        "vegan food",
        "vegetarian food",
        "library food",
        "Sunday food",
        "What is the cheapest food in NTU?",
        "What is the Vietnamese food",
        "What is the freshest food",
        "I love Vietnamese food",
    ],
)
def test_explicit_cuisine_phrase_rejects_generic_and_vocabulary_words(
    question: str,
) -> None:
    filters = extract_structured_filters(question)
    assert filters.cuisine is None, question
    assert filters.exclude_cuisine is None, question


@pytest.mark.parametrize(
    "question",
    [
        "near North Spine food",
        "library food",
        "Sunday food",
    ],
)
def test_location_and_open_hours_words_never_become_cuisine(
    question: str,
) -> None:
    assert extract_structured_filters(question).cuisine is None


def test_contracted_cuisine_negation_becomes_exclusion() -> None:
    filters = extract_structured_filters("I don't want Vietnamese food")
    assert filters.cuisine is None
    assert filters.exclude_cuisine == "Vietnamese"

    not_filters = extract_structured_filters("not Vietnamese food")
    assert not_filters.cuisine is None
    assert not_filters.exclude_cuisine == "Vietnamese"


@pytest.mark.parametrize("question", [
    "Where is Gelare?", "How many vendors are there?", "hello", "library food",
])
def test_query_without_explicit_cuisine_returns_no_cuisine(question) -> None:
    assert extract_structured_filters(question).cuisine is None

