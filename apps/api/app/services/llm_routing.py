"""Real Gemini-backed LLM fallbacks for intent routing and filter extraction.

These are injected into ``IntentRouter`` / ``ChatService`` from the FastAPI
dependency layer. Tests substitute fakes, so the Gemini calls stay out of the
unit-test path.
"""

import json
import re
import unicodedata
from typing import Callable

from app.core.config import settings
from app.models import ChatbotPrompt
from app.schemas.chat import ChatHistoryMessage
from app.services.intent_router import SEARCH_TYPES
from app.services.structured_filters import StructuredFilter

_MAX_VENDOR_NAMES = 20
_MAX_VENDOR_NAME_LENGTH = 100
_BUDGETS = {"cheap", "expensive"}
_OPEN_HOURS = {"after 20:00", "late", "sunday"}
_SORTS = {"rating", "price_asc", "price_desc"}


def _extract_search_type(text: str) -> str:
    for search_type in ("SQL + Vector", "SQL", "Vector"):
        if search_type.casefold() in text.casefold():
            return search_type
    return "Vector"


def build_classifier(
    client: object,
    model: str = settings.chat_model,
) -> Callable[[str, list[ChatbotPrompt]], str]:
    """Return a classifier that maps a question to a ``search_type``."""

    def classify(question: str, prompts: list[ChatbotPrompt]) -> str:
        options = "\n".join(
            f"- {prompt.question_text} -> {prompt.search_type}"
            for prompt in prompts
            if prompt.question_text
        )
        instruction = (
            "Classify the user's food question into exactly one search type: "
            f"{sorted(SEARCH_TYPES)}. Reply with only the search type.\n\n"
            f"Reference intents:\n{options or '(none)'}\n\n"
            f"Question: {question}"
        )
        response = client.models.generate_content(
            model=model,
            contents=instruction,
        )
        return _extract_search_type(response.text or "")

    return classify


def build_filter_extractor(
    client: object,
    model: str = settings.chat_model,
) -> Callable[[str], StructuredFilter]:
    """Return an extractor that turns a question into a ``StructuredFilter``."""

    def extract(question: str) -> StructuredFilter:
        instruction = (
            "Extract structured food filters from the question. Reply with only "
            "a JSON object using any of these keys: halal (bool), vegetarian "
            "(bool), cuisine (str), vendor_names (array of merchant/vendor "
            "name strings), location (str), budget (str: 'cheap' or "
            "'expensive'), open_hours (str), sort (str: 'rating', 'price_asc' "
            "or 'price_desc'), query_kind (str: 'list', 'count' or 'rank'), "
            "top_n (int). Put every explicitly named merchant in vendor_names, "
            "including multiple merchants, regardless of punctuation or how "
            "many are named. A proper business, brand, stall, cafe, or restaurant "
            "name is a vendor, never a cuisine. Only use cuisine for a type or "
            "regional style of food. Apply these rules consistently to every "
            "name rather than relying on a fixed list of examples. Omit keys "
            "that are unknown.\n\n"
            f"Question: {question}"
        )
        try:
            response = client.models.generate_content(
                model=model,
                contents=instruction,
            )
            return _parse_filter_json(response.text or "")
        except Exception:
            return StructuredFilter()

    return extract


def build_question_rewriter(
    client: object,
    model: str = settings.chat_model,
) -> Callable[[str, list[ChatHistoryMessage]], str]:
    """Return a rewriter that resolves a follow-up into a standalone question."""

    def rewrite(question: str, history: list[ChatHistoryMessage]) -> str:
        history_text = "\n".join(
            f"{'User' if message.role == 'user' else 'Foodie'}: {message.content}"
            for message in history
        )
        instruction = (
            "Rewrite the user's latest question into a single standalone "
            "question that resolves any references (pronouns, 'the one', "
            "'what about ...') to the conversation history. Preserve the "
            "user's intent and any names, places, or filters already stated. "
            "Reply with only the rewritten question and no explanation.\n\n"
            f"Conversation history:\n{history_text or '(none)'}\n\n"
            f"Latest question: {question}"
        )
        response = client.models.generate_content(
            model=model,
            contents=instruction,
        )
        return (response.text or "").strip()

    return rewrite


def _parse_filter_json(text: str) -> StructuredFilter:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return StructuredFilter()
    try:
        data = json.loads(match.group(0))
    except (json.JSONDecodeError, ValueError):
        return StructuredFilter()

    query_kind = data.get("query_kind")
    if not isinstance(query_kind, str) or query_kind not in {
        "list",
        "count",
        "rank",
    }:
        query_kind = "list"
    return StructuredFilter(
        halal=_as_bool(data.get("halal")),
        vegetarian=_as_bool(data.get("vegetarian")),
        cuisine=_as_str(data.get("cuisine")),
        location=_as_str(data.get("location")),
        budget=_as_enum(data.get("budget"), _BUDGETS),
        open_hours=_as_enum(data.get("open_hours"), _OPEN_HOURS),
        sort=_as_enum(data.get("sort"), _SORTS),
        top_n=_as_int(data.get("top_n")),
        query_kind=query_kind,
        vendor_names=_as_str_list(data.get("vendor_names")),
    )


def _as_bool(value: object) -> bool | None:
    return value if isinstance(value, bool) else None


def _as_str(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _as_enum(value: object, allowed: set[str]) -> str | None:
    parsed = _as_str(value)
    normalized = parsed.casefold() if parsed is not None else None
    return normalized if normalized in allowed else None


def _as_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, str):
        raw_digits = value.strip()
        if not raw_digits or not all(
            character.isdecimal() for character in raw_digits
        ):
            return None

        # Convert at most the three significant decimal digits needed for the
        # supported 1..100 range.  This avoids Python's large-integer conversion
        # limit for malicious or malformed strings with thousands of digits.
        significant_digits: list[str] = []
        for character in raw_digits:
            digit = unicodedata.decimal(character)
            if digit or significant_digits:
                significant_digits.append(str(digit))
                if len(significant_digits) > 3:
                    return None
        parsed = int("".join(significant_digits) or "0")
    else:
        return None
    return parsed if 1 <= parsed <= 100 else None


def _as_str_list(value: object) -> list[str] | None:
    """Return a bounded, cleaned list of unique non-empty strings."""
    if not isinstance(value, list):
        return None

    cleaned: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            continue
        name = " ".join(item.split())
        if not name or len(name) > _MAX_VENDOR_NAME_LENGTH:
            continue
        dedupe_key = name.casefold()
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        cleaned.append(name)
        if len(cleaned) == _MAX_VENDOR_NAMES:
            break
    return cleaned or None
