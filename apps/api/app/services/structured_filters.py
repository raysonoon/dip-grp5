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
    location: str | None = None
    budget: str | None = None
    open_hours: str | None = None
    sort: str | None = None
    top_n: int | None = None
    query_kind: str = "list"

    @property
    def has_constraints(self) -> bool:
        return any(
            value is not None
            for value in (
                self.halal,
                self.vegetarian,
                self.cuisine,
                self.location,
                self.budget,
                self.open_hours,
                self.sort,
                self.top_n,
            )
        )


def _contains_any(question: str, keywords: set[str]) -> bool:
    lowered = question.casefold()
    return any(keyword in lowered for keyword in keywords)


def _find_keyword(question: str, mapping: dict[str, str | None]) -> str | None:
    lowered = question.casefold()
    for keyword, value in mapping.items():
        if keyword in lowered:
            return value
    return None


def _extract_cuisine(question: str) -> str | None:
    value = _find_keyword(question, CUISINE_KEYWORDS)
    return value


def _extract_location(question: str) -> str | None:
    return _find_keyword(question, LOCATION_KEYWORDS)


def _extract_budget(question: str) -> str | None:
    lowered = question.casefold()
    if any(word in lowered for word in ("cheap", "affordable", "budget")):
        return "cheap"
    if any(word in lowered for word in ("expensive", "pricey", "premium")):
        return "expensive"
    return None


def _extract_open_hours(question: str) -> str | None:
    lowered = re.sub(r"\s+", " ", question.casefold())
    if "after 8pm" in lowered:
        return "after 20:00"
    if "late at night" in lowered or "late night" in lowered:
        return "late"
    if "open on sunday" in lowered or "sunday" in lowered:
        return "sunday"
    return None


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

    top_match = re.search(r"\btop\s+(\d+)\b", lowered)
    if top_match:
        return "rank", int(top_match.group(1))
    return "list", None


def extract_structured_filters(question: str) -> StructuredFilter:
    """Derive structured SQL filters from a question using deterministic rules."""
    halal = None
    vegetarian = None
    if _contains_any(question, HALAL_KEYWORDS):
        halal = True
    if _contains_any(question, VEGETARIAN_KEYWORDS):
        vegetarian = True

    query_kind, top_n = _extract_query_kind(question)
    sort = _extract_sort(question)
    if query_kind == "rank" and top_n is None and sort == "rating":
        top_n = 10

    return StructuredFilter(
        halal=halal,
        vegetarian=vegetarian,
        cuisine=_extract_cuisine(question),
        location=_extract_location(question),
        budget=_extract_budget(question),
        open_hours=_extract_open_hours(question),
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