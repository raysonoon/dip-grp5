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
    r"\b(?:do|does|did|ca|is|are|was|were|should|could|would)n['\u2019]?t|"
    r"\bwon['\u2019]t|"
    r"\bclosed(?:\s+on)?|\bno|\bnon|"
    r"\bwithout(?:\s+any)?)"
    r"(?:\s+(?:want|like|get|have|eat|order|try|find|serve|recommend|"
    r"prefer|need|looking))?"
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
# A clause can end in punctuation before a contrast boundary ("Vietnamese, but
# not Chinese food"). Strip it so the ancestral suffix check sees the adjective.
_CUISINE_CLAUSE_TRAILING_PUNCT_RE = re.compile(
    r"[\s,;:.!?\uff0c\uff1b\uff1a\uff0e\uff01\uff1f]+$"
)
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
    "are",
    "did",
    "do",
    "does",
    "is",
    "there",
    "was",
    "were",
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
    "eat",
    "like",
    "list",
    "looking",
    "show",
    "suggest",
}
_CUISINE_STOP_WORDS = {
    "affordable",
    "best",
    "biggest",
    "campus",
    "cheap",
    "cheaper",
    "cheapest",
    "delicious",
    "expensive",
    "famous",
    "favorite",
    "favourite",
    "freshest",
    "good",
    "great",
    "halal",
    "healthiest",
    "healthy",
    "late",
    "near",
    "nearby",
    "nice",
    "nicest",
    "night",
    "ntu",
    "popular",
    "premium",
    "pricey",
    "spiciest",
    "spicy",
    "student",
    "students",
    "tastiest",
    "tasty",
    "trending",
    "value",
    "vegan",
    "vegetarian",
    "worst",
}


def _vocabulary_tokens(mapping: dict[str, str | None]) -> set[str]:
    return {
        token for key in mapping for token in key.casefold().split()
    }


_CUISINE_REJECTION_WORDS = (
    _CUISINE_STOP_WORDS
    | _vocabulary_tokens(_OPEN_HOURS_KEYWORDS)
    | _vocabulary_tokens(_BUDGET_KEYWORDS)
    | VEGETARIAN_KEYWORDS
    | HALAL_KEYWORDS
)
_CUISINE_LOCATION_RE = re.compile(
    r"(?<!\w)(?:"
    + "|".join(
        re.escape(key.casefold())
        for key in sorted(LOCATION_KEYWORDS, key=len, reverse=True)
    )
    + r")(?!\w)"
)
_CUISINE_PHRASE_BLOCKERS = {
    "what",
    "when",
    "where",
    "why",
    "who",
    "whom",
    "whose",
    "how",
    "but",
    "and",
    "or",
    "versus",
    "vs",
    "prefer",
}
_CUISINE_REQUEST_CUES = _CUISINE_BOUNDARY_WORDS | {
    "any",
    "some",
    "which",
    "is",
    "are",
    "was",
    "were",
    "do",
    "does",
    "did",
    "there",
    "not",
    "no",
    "without",
    "don't",
    "doesn't",
    "didn't",
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


def _has_cuisine_request_cue(prefix: str) -> bool:
    """Report whether a request/boundary verb introduces a cuisine phrase.

    Walks backwards over filler words (``the``/``for``/``i`` ...) and returns
    ``True`` when the phrase is led by a request cue such as ``find`` or
    ``any``. This keeps bare noun phrases from becoming cuisines while still
    supporting verb-less requests.
    """
    for match in reversed(
        list(re.finditer(r"[A-Za-z][A-Za-z'\u2019-]*", prefix))
    ):
        folded = match.group(0).casefold().replace("\u2019", "'")
        if folded in _CUISINE_REQUEST_CUES:
            return True
        if folded not in _CUISINE_REQUEST_WORDS:
            return False
    return False


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

    raw_phrase = ""
    word_matches: list[re.Match[str]] = []
    words: list[str] = []
    for match in _EXPLICIT_CUISINE_PHRASE_RE.finditer(question):
        raw_phrase = match.group("phrase")
        word_matches = list(
            re.finditer(r"[A-Za-z][A-Za-z'\u2019-]*", raw_phrase)
        )
        words = [word_match.group(0) for word_match in word_matches]
        if not words or words[-1].casefold() in _CUISINE_REJECTION_WORDS:
            continue

        start_index = 0
        for index, word in enumerate(words):
            if word.casefold() in _CUISINE_BOUNDARY_WORDS:
                start_index = index + 1

        while start_index < len(words):
            previous_index = start_index
            while start_index < len(words) and (
                words[start_index].casefold() in _CUISINE_REQUEST_WORDS
                or words[start_index].casefold() in _CUISINE_REJECTION_WORDS
            ):
                start_index += 1
            if start_index >= len(words):
                break

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
        if not candidate_words or any(
            word.casefold()
            in _CUISINE_REJECTION_WORDS | _CUISINE_PHRASE_BLOCKERS
            for word in candidate_words
        ):
            continue
        if _CUISINE_LOCATION_RE.search(
            " ".join(word.casefold() for word in candidate_words)
        ):
            continue

        candidate_start = (
            match.start("phrase") + word_matches[start_index].start()
        )
        if _keyword_is_negated(question, candidate_start) != negated:
            continue
        prefix = question[:candidate_start]
        # A bare request may start with another filter ("late night
        # Vietnamese food", "North Spine Vietnamese food"). Remove whole
        # filter phrases before checking the remaining request language.
        for keyword in sorted(filter_keywords, key=len, reverse=True):
            prefix = re.sub(
                rf"(?<!\w){re.escape(keyword)}(?!\w)", " ", prefix,
                flags=re.IGNORECASE,
            )
        if prefix.strip() and not _has_cuisine_request_cue(prefix):
            continue
        return " ".join(candidate_words).title()
    if not words:
        return None
    return None


def _extract_cuisine(question: str, *, negated: bool = False) -> str | None:
    value = _find_keyword(question, CUISINE_KEYWORDS, negated=negated)
    if value is not None:
        return value
    value = _extract_explicit_cuisine_phrase(question, negated=negated)
    if value is not None:
        return value
    # In "Vietnamese but not Chinese food", the shared word "food" also qualifies the first clause.
    # Only accept a plausible cuisine adjective, tolerating clause punctuation ("Vietnamese, but not Chinese food").
    for boundary in _CUISINE_CLAUSE_BOUNDARY_RE.finditer(question):
        clause = _CUISINE_CLAUSE_TRAILING_PUNCT_RE.sub(
            "", question[:boundary.start()],
        )
        if _CUISINE_NAME_ENDING_RE.search(clause):
            value = _extract_explicit_cuisine_phrase(
                f"{clause} food", negated=negated,
            )
            if value is not None:
                return value
    return None


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
