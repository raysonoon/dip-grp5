"""Structured SQL filters extracted from a free-text chatbot question.

The SQL and ``SQL + Vector`` search paths need concrete predicates over the
relational ``vendors`` / ``reviews`` tables. These are derived from the user's
question by a deterministic rule-based extractor, with an optional LLM fallback
for phrasing the rules do not recognise.
"""

import re
from dataclasses import dataclass
from typing import Callable

# Cosine-similarity threshold that decides whether an embedding match is
# confident enough to route on. See ``IntentRouter`` tier 2.
SIMILARITY_THRESHOLD = 0.88

CUISINE_KEYWORDS = {
    "korean": "Korean",
    "japanese": "Japanese",
    "jap": "Japanese",
    "chinese": "Chinese",
    "western": "Western",
    "indian": "Indian",
    "malay": "Malay",
    "thai": "Thai",
    "italian": "Italian",
    "mexican": "Mexican",
    "halal": None,
}

LOCATION_KEYWORDS = {
    "north spine": "North Spine",
    "south spine": "South Spine",
    "library": "Library",
    "nie": "NIE",
    "hall 1": "Hall 1",
    "hall 2": "Hall 2",
    "hall 3": "Hall 3",
    "hall 4": "Hall 4",
    "hall 5": "Hall 5",
    "hall 6": "Hall 6",
    "hall 7": "Hall 7",
    "hall 8": "Hall 8",
    "hall 9": "Hall 9",
    "hall 10": "Hall 10",
    "hall 11": "Hall 11",
    "hall 12": "Hall 12",
    "hall 13": "Hall 13",
    "hall 14": "Hall 14",
    "hall 15": "Hall 15",
    "hall 16": "Hall 16",
    "quad": "Quad",
    "binjai": "Binjai",
    "crespion": "Crespion",
    "can 1": "Can 1",
    "can 2": "Can 2",
    "can 14": "Can 14",
    "can 16": "Can 16",
}

VEGETARIAN_KEYWORDS = {"vegetarian", "vegetarian-friendly", "vegan", "veg"}
HALAL_KEYWORDS = {"halal"}

_BUDGET_KEYWORDS = {
    "inexpensive": "cheap",
    "affordable": "cheap",
    "cheap": "cheap",
    "budget": "cheap",
    "expensive": "expensive",
    "pricey": "expensive",
    "premium": "expensive",
}

_OPEN_HOURS_KEYWORDS = {
    "after 8 pm": "after 20:00",
    "after 8pm": "after 20:00",
    "late at night": "late",
    "late night": "late",
    "open late": "late",
    "late": "late",
    "sunday": "sunday",
}

_NEGATION_BEFORE_KEYWORD_RE = re.compile(
    r"(?:\bnot\s+open(?:\s+on)?|"
    r"\bnot(?:\s+(?:a|an|at|in|near|on|too|very))?|"
    r"\bclosed(?:\s+on)?|\bno|\bnon|"
    r"\bwithout(?:\s+any)?)"
    r"[\s\-\u2010-\u2015]*$"
)
_TOP_N_RE = re.compile(
    r"\btop\s+(\d+)"
    r"(?!\w|[.,:/+'\u2010-\u2015\u2019\uff0c\uff0e\uff0f-]\s*\d|\s+\d)"
)
_EXPLICIT_CUISINE_PHRASE_RE = re.compile(
    r"(?P<phrase>(?:[A-Za-z][A-Za-z'\u2019-]*\s+){1,4})"
    r"food\b",
    re.IGNORECASE,
)
# Open-ended cuisine adjectives commonly use demonym-style suffixes.  Keeping
# this fallback morphological makes it conservative without growing a list of
# phrases that happened to be misclassified.  Ambiguous phrases are left for
# the existing LLM extractor instead of becoming restrictive SQL predicates.
_CUISINE_NAME_ENDING_RE = re.compile(
    r"(?:an|ean|ian|ese|ish|ic|i|ern)\Z",
    re.IGNORECASE,
)
_CUISINE_CLAUSE_BOUNDARY_RE = re.compile(r"\b(?:but|or)\b", re.IGNORECASE)
_CUISINE_REQUEST_WORDS = {
    "a",
    "an",
    "any",
    "can",
    "could",
    "craving",
    "eat",
    "find",
    "for",
    "get",
    "have",
    "has",
    "i",
    "like",
    "list",
    "looking",
    "me",
    "no",
    "not",
    "of",
    "options",
    "place",
    "places",
    "or",
    "please",
    "recommend",
    "serve",
    "serves",
    "serving",
    "show",
    "some",
    "the",
    "to",
    "want",
    "we",
    "where",
    "which",
    "without",
    "you",
}
_CUISINE_BOUNDARY_WORDS = {
    "craving",
    "find",
    "get",
    "have",
    "has",
    "offer",
    "offers",
    "recommend",
    "serve",
    "serves",
    "serving",
    "want",
}
_NON_CUISINE_DESCRIPTORS = {
    "affordable",
    "best",
    "cheap",
    "delicious",
    "expensive",
    "good",
    "halal",
    "healthy",
    "nice",
    "premium",
    "pricey",
    "spicy",
    "tasty",
    "vegan",
    "vegetarian",
}


@dataclass
class StructuredFilter:
    """Predicates over ``vendors`` / ``reviews`` plus the query shape.

    Unset attributes mean "no constraint". ``query_kind`` selects between a
    filtered listing (``list``), a row count (``count``), and an ordered,
    limited ranking (``rank``).
    """

    halal: bool | None = None
    vegetarian: bool | None = None
    cuisine: str | None = None
    exclude_cuisine: str | None = None
    location: str | None = None
    exclude_location: str | None = None
    budget: str | None = None
    exclude_budget: str | None = None
    open_hours: str | None = None
    exclude_open_hours: str | None = None
    sort: str | None = None
    top_n: int | None = None
    query_kind: str = "list"
    vendor_names: list[str] | None = None
    vendor_ids: list[int] | None = None

    @property
    def has_constraints(self) -> bool:
        return any(
            value is not None
            for value in (
                self.halal,
                self.vegetarian,
                self.cuisine,
                self.exclude_cuisine,
                self.location,
                self.exclude_location,
                self.budget,
                self.exclude_budget,
                self.open_hours,
                self.exclude_open_hours,
                self.sort,
                self.top_n,
                self.vendor_names,
                self.vendor_ids,
            )
        )


def _keyword_matches(question: str, keyword: str) -> list[re.Match[str]]:
    pattern = rf"(?<!\w){re.escape(keyword.casefold())}(?!\w)"
    return list(re.finditer(pattern, question.casefold()))


def _keyword_is_negated(question: str, start: int) -> bool:
    return (
        _NEGATION_BEFORE_KEYWORD_RE.search(question.casefold()[:start])
        is not None
    )


def _extract_boolean_keyword(
    question: str,
    keywords: set[str],
) -> bool | None:
    candidates: list[tuple[int, int, bool]] = []
    for keyword in sorted(keywords, key=lambda value: (-len(value), value)):
        for match in _keyword_matches(question, keyword):
            candidates.append(
                (
                    match.start(),
                    -len(keyword),
                    not _keyword_is_negated(question, match.start()),
                )
            )
    if not candidates:
        return None
    return min(candidates)[2]


def _find_keyword(
    question: str,
    mapping: dict[str, str | None],
    *,
    negated: bool = False,
) -> str | None:
    candidates: list[tuple[int, int, str | None]] = []
    for keyword, value in sorted(
        mapping.items(),
        key=lambda item: (-len(item[0]), item[0]),
    ):
        if value is None:
            continue
        for match in _keyword_matches(question, keyword):
            if _keyword_is_negated(question, match.start()) == negated:
                candidates.append((match.start(), -len(keyword), value))
    if not candidates:
        return None
    return min(candidates, key=lambda candidate: candidate[:2])[2]


def _extract_explicit_cuisine_phrase(
    question: str,
    *,
    negated: bool,
) -> str | None:
    """Extract an open-ended cuisine from an explicit ``X food`` phrase.

    The fixed mapping above keeps aliases such as ``jap`` deterministic, while
    this linguistic fallback lets explicit phrases such as ``Vietnamese food``
    or ``Middle Eastern food`` use the same SQL path without adding one keyword
    per cuisine. Generic request/adjective words are removed conservatively.
    """

    filter_keywords = (
        *LOCATION_KEYWORDS,
        *_BUDGET_KEYWORDS,
        *_OPEN_HOURS_KEYWORDS,
        *VEGETARIAN_KEYWORDS,
        *HALAL_KEYWORDS,
    )

    for match in _EXPLICIT_CUISINE_PHRASE_RE.finditer(question):
        raw_phrase = match.group("phrase")
        boundaries = list(_CUISINE_CLAUSE_BOUNDARY_RE.finditer(raw_phrase))
        ranges: list[tuple[int, int]] = []
        start = 0
        for boundary in boundaries:
            ranges.append((start, boundary.start()))
            start = boundary.end()
        ranges.append((start, len(raw_phrase)))

        for start, end in ranges:
            value = _extract_cuisine_clause(
                question,
                raw_phrase[start:end],
                match.start("phrase") + start,
                filter_keywords=filter_keywords,
                negated=negated,
            )
            if value is not None:
                return value
    return None


def _extract_cuisine_clause(
    question: str,
    raw_phrase: str,
    phrase_start: int,
    *,
    filter_keywords: tuple[str, ...],
    negated: bool,
) -> str | None:
    """Extract one cuisine candidate without absorbing other filter spans."""

    word_matches = list(
        re.finditer(r"[A-Za-z][A-Za-z'\u2019-]*", raw_phrase)
    )
    words = [word_match.group(0) for word_match in word_matches]
    if not words or words[-1].casefold() in _NON_CUISINE_DESCRIPTORS:
        return None

    start_index = 0
    for index, word in enumerate(words):
        if word.casefold() in _CUISINE_BOUNDARY_WORDS:
            start_index = index + 1

    while start_index < len(words):
        previous_index = start_index
        while start_index < len(words) and (
            words[start_index].casefold() in _CUISINE_REQUEST_WORDS
            or words[start_index].casefold() in _NON_CUISINE_DESCRIPTORS
        ):
            start_index += 1
        if start_index >= len(words):
            return None

        suffix_start = word_matches[start_index].start()
        suffix = raw_phrase[suffix_start:]
        filter_end = max(
            (
                keyword_match.end()
                for keyword in filter_keywords
                for keyword_match in _keyword_matches(suffix, keyword)
                if keyword_match.start() == 0
            ),
            default=0,
        )
        if filter_end:
            absolute_end = suffix_start + filter_end
            while (
                start_index < len(words)
                and word_matches[start_index].start() < absolute_end
            ):
                start_index += 1

        if start_index == previous_index:
            break

    candidate_words = words[start_index:]
    if not candidate_words or all(
        word.casefold() in _NON_CUISINE_DESCRIPTORS
        for word in candidate_words
    ):
        return None
    if _CUISINE_NAME_ENDING_RE.search(candidate_words[-1]) is None:
        return None

    candidate_start = phrase_start + word_matches[start_index].start()
    if _keyword_is_negated(question, candidate_start) != negated:
        return None
    return " ".join(candidate_words).title()


def _extract_cuisine(question: str, *, negated: bool = False) -> str | None:
    value = _find_keyword(question, CUISINE_KEYWORDS, negated=negated)
    if value is not None:
        return value
    return _extract_explicit_cuisine_phrase(question, negated=negated)


def _extract_location(question: str, *, negated: bool = False) -> str | None:
    return _find_keyword(question, LOCATION_KEYWORDS, negated=negated)


def _extract_budget(question: str, *, negated: bool = False) -> str | None:
    return _find_keyword(question, _BUDGET_KEYWORDS, negated=negated)


def _extract_open_hours(
    question: str,
    *,
    negated: bool = False,
) -> str | None:
    return _find_keyword(question, _OPEN_HOURS_KEYWORDS, negated=negated)


def _extract_sort(question: str) -> str | None:
    lowered = question.casefold()
    if any(word in lowered for word in ("cheapest", "most affordable")):
        return "price_asc"
    if any(word in lowered for word in ("most expensive", "pricey")):
        return "price_desc"
    if any(
        word in lowered
        for word in ("best", "highest rated", "top rated", "top-rated")
    ):
        return "rating"
    return None


def _extract_query_kind(question: str) -> tuple[str, int | None]:
    lowered = question.casefold()

    if "how many" in lowered or "how much" in lowered:
        return "count", None

    top_match = _TOP_N_RE.search(lowered)
    if top_match:
        digits = top_match.group(1).lstrip("0") or "0"
        if len(digits) <= 3:
            top_n = int(digits)
            if 1 <= top_n <= 100:
                return "rank", top_n
    return "list", None


def extract_structured_filters(question: str) -> StructuredFilter:
    """Derive structured SQL filters from a question using deterministic rules."""
    halal = _extract_boolean_keyword(question, HALAL_KEYWORDS)
    vegetarian = _extract_boolean_keyword(question, VEGETARIAN_KEYWORDS)

    query_kind, top_n = _extract_query_kind(question)
    sort = _extract_sort(question)
    if query_kind == "rank" and top_n is None and sort == "rating":
        top_n = 10

    return StructuredFilter(
        halal=halal,
        vegetarian=vegetarian,
        cuisine=_extract_cuisine(question),
        exclude_cuisine=_extract_cuisine(question, negated=True),
        location=_extract_location(question),
        exclude_location=_extract_location(question, negated=True),
        budget=_extract_budget(question),
        exclude_budget=_extract_budget(question, negated=True),
        open_hours=_extract_open_hours(question),
        exclude_open_hours=_extract_open_hours(question, negated=True),
        sort=sort,
        top_n=top_n,
        query_kind=query_kind,
    )


def extract_structured_filters_llm(
    question: str,
    extractor: Callable[[str], StructuredFilter] | None,
) -> StructuredFilter:
    """Fall back to an LLM filter extractor, else return an empty filter."""
    if extractor is None:
        return StructuredFilter()
    return extractor(question)
