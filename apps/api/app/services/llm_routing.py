"""Real Gemini-backed LLM fallbacks for intent routing and filter extraction.

These are injected into ``IntentRouter`` / ``ChatService`` from the FastAPI
dependency layer. Tests substitute fakes, so the Gemini calls stay out of the
unit-test path.
"""

import json
import re
from typing import Callable

from app.core.config import settings
from app.models import ChatbotPrompt
from app.schemas.chat import ChatHistoryMessage
from app.services.intent_router import SEARCH_TYPES
from app.services.structured_filters import StructuredFilter


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
            "(bool), cuisine (str), location (str), budget (str: 'cheap' or "
            "'expensive'), open_hours (str), sort (str: 'rating', 'price_asc' "
            "or 'price_desc'), query_kind (str: 'list', 'count' or 'rank'), "
            "top_n (int). Omit keys that are unknown.\n\n"
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
    if query_kind not in {"list", "count", "rank"}:
        query_kind = "list"
    return StructuredFilter(
        halal=_as_bool(data.get("halal")),
        vegetarian=_as_bool(data.get("vegetarian")),
        cuisine=_as_str(data.get("cuisine")),
        location=_as_str(data.get("location")),
        budget=_as_str(data.get("budget")),
        open_hours=_as_str(data.get("open_hours")),
        sort=_as_str(data.get("sort")),
        top_n=_as_int(data.get("top_n")),
        query_kind=query_kind,
    )


def _as_bool(value: object) -> bool | None:
    return value if isinstance(value, bool) else None


def _as_str(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _as_int(value: object) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None