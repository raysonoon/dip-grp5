from types import SimpleNamespace

import pytest

from app.db import seed_reddit
from app.services.vendor_matching import (
    CHAT_VENDOR_ALIASES,
    VENDOR_ALIASES,
    match_vendor_mentions,
    normalize_vendor_text,
    resolve_vendor_names,
    suggest_vendor_names,
)


VENDORS = [
    (42, "Popeyes"),
    (8, "Blue Ocean Kopi & Toast"),
    (26, "Geláre"),
    (17, "Encik Tan"),
    (2, "A Hot Hideout"),
    (14, "Connect 71 Cafe (C71)"),
    (44, "Quad Cafe (SBS)"),
    (51, "The Soup Spoon Union"),
    (36, "North Hill Food Court (Colour Box)"),
    (25, "Food Court @ NIE"),
]


def test_normalize_vendor_text_uses_one_consistent_ascii_form() -> None:
    assert normalize_vendor_text("  Geláre & Café!!\n") == "gelare cafe"
    assert normalize_vendor_text("Paik’s   Bibim") == "paiks bibim"


def test_normalize_vendor_text_folds_unicode_separators_and_apostrophes(
) -> None:
    assert normalize_vendor_text("Blue—Ocean、Popeyes") == (
        "blue ocean popeyes"
    )
    assert normalize_vendor_text("Each‑A‑Cup") == "each a cup"
    assert normalize_vendor_text("McDonald's") == "mcdonalds"
    assert normalize_vendor_text("McDonald’s") == "mcdonalds"


def test_match_vendor_mentions_resolves_required_aliases_in_text_order() -> None:
    matches = match_vendor_mentions(
        "Where is Gelare, Encik Tan and Blue Ocean?",
        VENDORS,
    )

    assert matches == [
        (26, "Geláre"),
        (17, "Encik Tan"),
        (8, "Blue Ocean Kopi & Toast"),
    ]


def test_match_vendor_mentions_supports_full_and_shortened_official_names(
) -> None:
    vendors = [
        (1, "Campus Bites (North Wing)"),
        (2, "The Green Fork"),
    ]

    assert match_vendor_mentions(
        "Is Campus Bites (North Wing) open?",
        vendors,
    ) == [(1, "Campus Bites (North Wing)")]
    assert match_vendor_mentions("Is Campus Bites open?", vendors) == [
        (1, "Campus Bites (North Wing)"),
    ]
    assert match_vendor_mentions("Try Green Fork", vendors) == [
        (2, "The Green Fork"),
    ]


def test_match_vendor_mentions_deduplicates_repeated_vendor_names() -> None:
    matches = match_vendor_mentions(
        "Gelare is Geláre, and I still mean Gelare.",
        VENDORS,
    )

    assert matches == [(26, "Geláre")]


def test_match_vendor_mentions_supports_unicode_multi_vendor_separators(
) -> None:
    matches = match_vendor_mentions(
        "Blue—Ocean、Gelare、Encik Tan、Popeyes",
        VENDORS,
    )

    assert matches == [
        (8, "Blue Ocean Kopi & Toast"),
        (26, "Geláre"),
        (17, "Encik Tan"),
        (42, "Popeyes"),
    ]


def test_match_vendor_mentions_folds_optional_apostrophes() -> None:
    vendors = [
        (28, "June's Breathe Cafe\n@ LKC Medicine"),
        (33, "McDonald's"),
    ]

    for query in ("McDonald's", "McDonalds", "McDonald’s"):
        assert match_vendor_mentions(query, vendors) == [
            (33, "McDonald's")
        ]

    for query in (
        "June's Breathe Cafe",
        "Junes Breathe Cafe",
        "June’s Breathe Cafe",
    ):
        assert match_vendor_mentions(query, vendors) == [
            (28, "June's Breathe Cafe\n@ LKC Medicine")
        ]


def test_match_vendor_mentions_treats_popeyes_as_a_vendor() -> None:
    assert match_vendor_mentions("Where is Popeyes in NTU?", VENDORS) == [
        (42, "Popeyes"),
    ]


def test_match_vendor_mentions_does_not_treat_location_as_vendor() -> None:
    assert match_vendor_mentions(
        "Where can I eat around North Spine in NTU?",
        VENDORS,
    ) == []


def test_chat_matcher_ignores_location_like_seed_aliases() -> None:
    vendors = [
        (60, "North Spine Food Court & International Food Court (Koufu)"),
        (61, "South Spine Food Court (Foodies' Clan)"),
        (62, "Food Court 1"),
        (63, "Food Court @ NIE"),
        (64, "North Hill Food Court (Colour Box)"),
    ]

    assert match_vendor_mentions(
        "What food is around North Spine Food Court, South Spine, NIE Canteen, "
        "North Hill, Canteen 11 or can 1?",
        vendors,
    ) == []


def test_chat_matcher_does_not_match_canteen_alias_inside_vendor_name(
) -> None:
    vendors = [
        (19, "Food Court 11"),
        (31, "Malay Stall at South Spine (from Canteen 11)"),
    ]

    assert "canteen 11" not in CHAT_VENDOR_ALIASES
    assert match_vendor_mentions(
        "Where is Malay Stall at South Spine (from Canteen 11)?",
        vendors,
    ) == [(31, "Malay Stall at South Spine (from Canteen 11)")]
    assert match_vendor_mentions("food near Canteen 11", vendors) == []


def test_full_seed_aliases_still_resolve_canteen_names() -> None:
    vendors = [(19, "Food Court 11")]

    assert match_vendor_mentions(
        "Students discuss Canteen 11",
        vendors,
        aliases=VENDOR_ALIASES,
    ) == [(19, "Food Court 11")]


def test_seed_matcher_explicitly_keeps_location_like_aliases() -> None:
    vendors = [
        SimpleNamespace(
            id=61,
            name="South Spine Food Court (Foodies' Clan)",
        ),
        SimpleNamespace(id=62, name="Food Court 1"),
    ]

    matches = seed_reddit._find_mentioned_vendors(
        "Students discuss South Spine and can 1.",
        vendors,
    )

    assert [(vendor.id, vendor.name) for vendor in matches] == [
        (61, "South Spine Food Court (Foodies' Clan)"),
        (62, "Food Court 1"),
    ]


def test_resolve_vendor_names_returns_matches_and_unresolved_values() -> None:
    matches, unresolved = resolve_vendor_names(
        ["Gelare", "Popeyes", "Mystery Stall", "Blue Ocean"],
        VENDORS,
    )

    assert matches == [
        (26, "Geláre"),
        (42, "Popeyes"),
        (8, "Blue Ocean Kopi & Toast"),
    ]
    assert unresolved == ["Mystery Stall"]


def test_resolve_vendor_names_accepts_llm_phrase_but_not_misspelling() -> None:
    phrase_matches, phrase_unresolved = resolve_vendor_names(
        "Popeyes at NTU",
        VENDORS,
    )
    typo_matches, typo_unresolved = resolve_vendor_names("Popeys", VENDORS)

    assert phrase_matches == [(42, "Popeyes")]
    assert phrase_unresolved == []
    assert typo_matches == []
    assert typo_unresolved == ["Popeys"]


def test_resolve_vendor_names_ignores_non_string_values() -> None:
    matches, unresolved = resolve_vendor_names(
        ["Popeyes", 123, None],  # type: ignore[list-item]
        VENDORS,
    )

    assert matches == [(42, "Popeyes")]
    assert unresolved == []


def test_suggest_vendor_names_handles_typo_and_rejects_weak_guesses() -> None:
    assert suggest_vendor_names("Gelar", VENDORS) == ["Geláre"]
    assert suggest_vendor_names("Popeys", VENDORS) == ["Popeyes"]
    assert suggest_vendor_names("North Spine", VENDORS) == []
    assert suggest_vendor_names("completely unrelated", VENDORS) == []


def test_suggest_vendor_names_is_unique_and_honours_limit() -> None:
    food_courts = [
        (1, "Food Court 1"),
        (2, "Food Court 2"),
        (4, "Food Court 4"),
        (9, "Food Court 9"),
    ]

    suggestions = suggest_vendor_names("Food Cort", food_courts, limit=3)

    assert len(suggestions) == 3
    assert len(set(suggestions)) == 3
    assert suggest_vendor_names("Food Cort", food_courts, limit=0) == []


def test_existing_aliases_include_dip_84_vendor_spellings() -> None:
    assert VENDOR_ALIASES["gelare"] == "Geláre"
    assert VENDOR_ALIASES["blue ocean"] == "Blue Ocean Kopi & Toast"
    assert VENDOR_ALIASES["popeyes"] == "Popeyes"


def test_seed_reddit_uses_shared_matching_and_keeps_orm_objects() -> None:
    vendors = [
        SimpleNamespace(id=vendor_id, name=vendor_name)
        for vendor_id, vendor_name in VENDORS
    ]

    matches = seed_reddit._find_mentioned_vendors(
        "Blue Ocean, Gelare and Encik Tan",
        vendors,
    )

    assert [(vendor.id, vendor.name) for vendor in matches] == [
        (8, "Blue Ocean Kopi & Toast"),
        (26, "Geláre"),
        (17, "Encik Tan"),
    ]
    assert seed_reddit.VENDOR_ALIASES is VENDOR_ALIASES


@pytest.mark.parametrize(
    ("official_name", "short_name"),
    [
        ("Aurora Tea @ NTU", "Aurora Tea"),
        ("Copper Kettle - NTU", "Copper Kettle"),
        (
            "Juniper Kitchen Nanyang Technological University",
            "Juniper Kitchen",
        ),
        ("Lantern Cafe at Innovation Centre", "Lantern Cafe"),
    ],
)
def test_short_brand_matches_data_driven_campus_suffixes(
    official_name: str,
    short_name: str,
) -> None:
    """Campus/location suffix support must not depend on a brand allow-list."""

    vendors = [(701, official_name)]

    assert match_vendor_mentions(
        f"Could you locate {short_name} for me?",
        vendors,
    ) == [(701, official_name)]
    assert resolve_vendor_names(short_name, vendors) == (
        [(701, official_name)],
        [],
    )


def test_same_name_branches_all_match_and_typo_suggestion_is_unique() -> None:
    """Two rows for one brand are valid branches, not an ambiguous failure."""

    vendors = [
        (711, "Orbit Bowl"),
        (712, "Orbit Bowl"),
    ]

    assert match_vendor_mentions("Where is Orbit Bowl?", vendors) == vendors
    assert resolve_vendor_names("Orbit Bowl", vendors) == (vendors, [])
    assert suggest_vendor_names("Orbt Bowl", vendors) == ["Orbit Bowl"]


def test_short_suffix_brand_typo_can_still_be_suggested() -> None:
    vendors = [(713, "7 TEA @ NTU")]

    assert suggest_vendor_names("7 Tee", vendors) == ["7 TEA @ NTU"]


@pytest.mark.parametrize(
    "separator",
    [", ", " and ", " or ", " / ", " + ", " versus ", "\n", "、"],
)
def test_multi_vendor_matching_is_generic_across_phrasings(
    separator: str,
) -> None:
    vendors = [
        (721, "Amber Ladle"),
        (722, "Birch Bento"),
        (723, "Cobalt Crumbs"),
    ]
    names = [name for _, name in vendors]
    question = f"Where are {separator.join(names)}?"

    assert match_vendor_mentions(question, vendors) == vendors
