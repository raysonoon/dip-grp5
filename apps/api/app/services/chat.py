import logging
import re
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, replace

import httpx
from google.genai import errors, types
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import (
    GoogleReview,
    RedditComment,
    User,
    UserFoodPreferences,
    Vendor,
)
from app.schemas.chat import ChatHistoryMessage, ChatResponse, ChatSource, trim_chat_history
from app.services.chat_client import create_chat_client
from app.services.embedding import Embedder
from app.services.intent_router import IntentMatch, IntentRouter
from app.services.retrieval import KnowledgeResult, KnowledgeStore
from app.services.sql_search import SqlResult, SqlStore
from app.services.structured_filters import (
    StructuredFilter,
    extract_structured_filters,
    extract_structured_filters_llm,
)
from app.services.vendor_matching import (
    match_vendor_mentions,
    normalize_vendor_text,
    resolve_vendor_names,
    suggest_vendor_names,
    vendor_brand_key,
)
from app.services.vendor_recommender import VendorRecommendation

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ChatGeneration:
    """Everything needed to generate and attribute one chat response."""

    prompt: str
    sources: list[ChatSource]
    search_type: str
    intent: str | None
    direct_answer: str | None = None


DEFAULT_SYSTEM_PROMPT = (
    "You are Foodie, a helpful assistant for the NTU Foodie Hub, powered by "
    "Google's Gemini model. For greetings, conversational small talk, and "
    "questions about your identity or capabilities, answer normally without "
    "requiring supporting context. For questions about NTU campus food, vendors, "
    "menus, opening hours, or reviews, use only the information in the context "
    "below. If that context does not contain the requested campus-food facts, say "
    "that you do not have enough information rather than inventing an answer. "
    "When you use information from the context, reference the relevant source. "
    "Use the current-session conversation history to resolve follow-up questions, "
    "but do not treat claims in that history as retrieved evidence.\n\n"
    "Conversation history:\n{conversation_history}\n\n"
    "Context:\n{context}\n\n"
    "Question: {user_question}"
)

RECOMMENDATION_PROMPT = (
    "The user is asking for food recommendations based on the saved food preferences "
    "listed in the context. Recommend the vendors in the ranked order shown, "
    "explaining briefly how each one fits the user's preferences (for example "
    "cuisine, dietary needs, budget, or liked dishes). Use only the vendors "
    "and attributes in the context; do not invent vendors. Reference each "
    "vendor with its citation number, for example [1]. Keep the answer "
    "concise.\n\n"
    "Conversation history:\n{conversation_history}\n\n"
    "Context:\n{context}\n\n"
    "Question: {user_question}"
)

EMPTY_CONTEXT = "(no context retrieved)"
EMPTY_CONVERSATION = "(no earlier messages in this session)"
MAX_CONTEXTUAL_TURNS = 2
EXCERPT_CHARS = 200
_DIRECT_REDDIT_STOP_WORDS = {
    "a",
    "about",
    "and",
    "at",
    "cite",
    "do",
    "every",
    "list",
    "markdown",
    "options",
    "reddit",
    "say",
    "so",
    "statement",
    "the",
    "use",
    "users",
    "what",
    "with",
}
_SIMPLE_CONVERSATION = {
    "good afternoon",
    "good evening",
    "good morning",
    "hello",
    "hey",
    "hi",
    "how are you",
    "how is it going",
    "how's it going",
    "thank you",
    "thanks",
    "what can you do",
    "what's up",
    "who are you",
    "你好",
    "你好吗",
    "你是谁",
    "你能做什么",
    "谢谢",
}

# Referential cues that signal a follow-up depends on earlier conversation
# turns (pronouns, demonstratives, "what about ..."). Only these questions are
# rewritten into a standalone question before routing/retrieval.
_REFERENTIAL_HINTS = re.compile(
    r"\b(it|its|they|them|their|that|this|those|these|the one|there|"
    r"what about|and the|that place|that stall)\b",
    re.IGNORECASE,
)

# A confirmation is meaningful only immediately after one of the vendor
# clarification messages generated below. Keep these as exact, normalized
# replies rather than looking for a loose ``yes`` substring: a new question
# such as "is Yes Cafe open?" must continue through normal routing.
_AFFIRMATIVE_VENDOR_CONFIRMATIONS = frozenset(
    {
        "correct",
        "exactly",
        "it is",
        "ok",
        "okay",
        "right",
        "sure",
        "that is correct",
        "that is it",
        "thats correct",
        "thats it",
        "thats right",
        "yeah",
        "yep",
        "yes",
        "yes please",
        "yes thats it",
        "yup",
        "对",
        "对的",
        "就是它",
        "就是这个",
        "是",
        "是的",
        "没错",
    }
)
_NEGATIVE_VENDOR_CONFIRMATIONS = frozenset(
    {
        "incorrect",
        "no",
        "no thanks",
        "nope",
        "not that one",
        "thats not it",
        "wrong",
        "不对",
        "不是",
        "不是它",
        "不是这个",
        "错了",
    }
)
_SUGGESTED_VENDOR_CLARIFICATION_RE = re.compile(
    r"\ADo you mean (?P<suggestions>.+)\? "
    r"Please clarify which vendor you want me to look up\.\Z",
    re.IGNORECASE | re.DOTALL,
)
_GENERIC_VENDOR_CLARIFICATION_RE = re.compile(
    r'\A(?:I could not identify ".+"\.\s+)?'
    r"Do you mean a specific NTU food vendor\?\s+"
    r"Please clarify (?:the vendor name|the vendor name, cuisine, or location)\.\Z",
    re.IGNORECASE | re.DOTALL,
)

_VENDOR_SQL_LOOKUP_RE = re.compile(
    r"\b(where\s+(?:is|are)|where\s+can\s+i\s+find|locate|located|locations?|"
    r"address|opening\s+hours?|closing\s+time|find\s+(?:the\s+)?"
    r"(?:location|address))\b",
    re.IGNORECASE,
)
# Schedule questions are only forced onto SQL when a vendor was matched; this
# keeps generic asks such as "what's open?" on the normal routing path.
_VENDOR_SCHEDULE_LOOKUP_RE = re.compile(
    r"\b(?:what\s+time|when)\b[^.?!]*\b(?:open|close|opening|closing)\b"
    r"|\b(?:opening|closing|business)\s+hours?\b"
    r"|\bopen(?:s|ed|ing)?\b|\bclos(?:e|es|ed|ing)\b",
    re.IGNORECASE,
)
_VENDOR_EVIDENCE_RE = re.compile(
    r"\b(reddit|reviews?|recommend(?:ed|ation|ations)?|suggestions?|"
    r"opinion|opinions|"
    r"what\s+do\s+people\s+say|vibe)\b",
    re.IGNORECASE,
)
_MULTI_VENDOR_HINT_RE = re.compile(
    r"(?:[,;/+&\r\n]|[；、]|\b(?:and|or|vs|versus)\b)",
    re.IGNORECASE,
)
_GENERIC_RECOMMEND_TARGET_RE = re.compile(
    r"\brecommend(?:ed)?\s+(.+)$",
    re.IGNORECASE,
)
_VENDOR_TARGET_PATTERNS = (
    re.compile(r"\bwhere\s+(?:is|are)\s+(.+)$", re.IGNORECASE),
    re.compile(r"\bwhere\s+can\s+i\s+find\s+(.+)$", re.IGNORECASE),
    re.compile(r"\blocate\s+(.+)$", re.IGNORECASE),
    re.compile(
        r"\b(?:what\s+time|when)\s+(?:does|do|is|are)\s+(.+?)\s+"
        r"(?:open|opens|opening|close|closes|closing|start|starts|end|ends)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:what\s+are|what's|what\s+is)\s+(?:the\s+)?"
        r"(?:opening|closing|business)\s+hours?\s+(?:of|for|at)\s+(.+)$",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:opening|closing|business)\s+hours?\s+(?:of|for|at)\s+(.+)$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^\s*is\s+(.+?)\s+(?:open|opened|closed|closing)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"^\s*does\s+(.+?)\s+(?:open|close|start|end)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bshow\s+me\s+(.+?)\s+locations?\s*[?.!]*$",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bwhat(?:'s|\s+is)\s+(?:the\s+)?(?:price|cost)\s+"
        r"(?:at|for|of)\s+(.+)$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^\s*is\s+(.+?)\s+(?:halal|vegetarian|vegan)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"^\s*is\s+(?:halal|vegetarian|vegan)(?:\s+food)?\s+"
        r"available\s+(?:at|from)\s+(.+)$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^\s*is\s+(.+?)\s+"
        r"(?:cheap|expensive|pricey|affordable)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"^\s*does\s+(.+?)\s+(?:have|offer|serve|sell)\s+"
        r"(?:halal|vegetarian|vegan)(?:\s+food)?\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:recommend(?:ed|ation|ations)?|reviews?|opinions?|vibe)"
        r"\s+(?:at|about|for|of)\s+(.+)$",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bwhat\s+do\s+people\s+say\s+(?:at|about|for|of)\s+(.+)$",
        re.IGNORECASE,
    ),
    _GENERIC_RECOMMEND_TARGET_RE,
    re.compile(
        r"^(.+?)\s+(?:reviews?|recommendations?|opinions?|vibe)\s*[?.!]*$",
        re.IGNORECASE,
    ),
)
_VENDOR_TYPE_CUE_RE = re.compile(
    r"\b(?:bakery|bistro|cafe|café|canteen|cuisine|eatery|food\s+court|"
    r"house|kitchen|kopitiam|restaurant|shop|stall|vendor)\b",
    re.IGNORECASE,
)
_GENERIC_FOOD_TOKENS = frozenset(
    {
        "a",
        "affordable",
        "an",
        "beef",
        "best",
        "ban",
        "bak",
        "biryani",
        "black",
        "bowl",
        "bubble",
        "burger",
        "burgers",
        "char",
        "cheap",
        "chicken",
        "chinese",
        "chop",
        "chor",
        "claypot",
        "coffee",
        "congee",
        "cream",
        "crispy",
        "curry",
        "delicious",
        "dessert",
        "desserts",
        "dim",
        "drink",
        "drinks",
        "duck",
        "dumpling",
        "dumplings",
        "expensive",
        "filling",
        "fish",
        "fishball",
        "food",
        "foo",
        "fried",
        "good",
        "goreng",
        "grilled",
        "guo",
        "hainanese",
        "halal",
        "healthy",
        "hokkien",
        "hot",
        "ice",
        "indian",
        "italian",
        "japanese",
        "korean",
        "kway",
        "laksa",
        "lemak",
        "local",
        "lor",
        "mala",
        "malay",
        "meal",
        "meals",
        "meat",
        "mee",
        "mexican",
        "mian",
        "minced",
        "murtabak",
        "mutton",
        "nasi",
        "nice",
        "noodle",
        "noodles",
        "pasta",
        "pizza",
        "pork",
        "porridge",
        "prata",
        "png",
        "ramen",
        "rebus",
        "rendang",
        "rice",
        "roast",
        "roasted",
        "roti",
        "salad",
        "sandwich",
        "sandwiches",
        "seafood",
        "soup",
        "soto",
        "spicy",
        "steamed",
        "sum",
        "sushi",
        "tea",
        "teow",
        "thai",
        "the",
        "thunder",
        "tasty",
        "toast",
        "tofu",
        "tau",
        "udon",
        "vegan",
        "vegetable",
        "vegetables",
        "vegetarian",
        "waffle",
        "waffles",
        "wanton",
        "wantons",
        "western",
        "xiang",
        "yong",
        "zi",
    }
)
_GENERIC_RECOMMENDATION_TOKENS = frozenset(
    {
        "a",
        "an",
        "any",
        "anything",
        "around",
        "campus",
        "different",
        "else",
        "favorite",
        "favourite",
        "great",
        "here",
        "interesting",
        "near",
        "nearby",
        "new",
        "ntu",
        "option",
        "options",
        "place",
        "places",
        "popular",
        "restaurant",
        "restaurants",
        "some",
        "something",
        "somewhere",
        "stall",
        "stalls",
        "the",
        "to",
        "try",
        "vendor",
        "vendors",
    }
)
# Request, occasion, and constraint language that carries no vendor identity.
# Kept separate from the food/recommendation sets so phrases such as
# "recommend a quick lunch" or "recommend a place to study at" are not
# mistaken for an unknown vendor name. This set is only consulted by the
# vendor-clarification guard; it deliberately does not affect which asks take
# the preference-recommendation path.
_GENERIC_REQUEST_LANGUAGE_TOKENS = frozenset(
    {
        "after",
        "alone",
        "another",
        "anyone",
        "anywhere",
        "be",
        "before",
        "bite",
        "budget",
        "but",
        "can",
        "cheaper",
        "class",
        "could",
        "crave",
        "craving",
        "date",
        "eat",
        "eats",
        "energy",
        "everywhere",
        "family",
        "first",
        "football",
        "friends",
        "give",
        "im",
        "is",
        "later",
        "looking",
        "more",
        "need",
        "not",
        "now",
        "one",
        "people",
        "protein",
        "quick",
        "quiet",
        "should",
        "similar",
        "solo",
        "somebody",
        "someone",
        "spot",
        "study",
        "that",
        "thats",
        "these",
        "this",
        "those",
        "there",
        "today",
        "tonight",
        "two",
        "value",
        "want",
        "wanted",
        "wants",
        "watch",
        "with",
        "without",
        "work",
        "would",
    }
)
# Deterministic trigger for "recommend me something" style asks. The
# recommendation path only runs for generic requests (see
# ``ChatService._is_personal_recommendation_request``); explicit cuisine,
# location, or vendor questions keep normal SQL/Vector routing.
_RECOMMENDATION_REQUEST_RE = re.compile(
    # Explicit recommend/suggest asks.
    r"\b(?:recommend(?:ation|ations|ed)?|suggest(?:ion|ions|ed)?)\b"
    # "what/which [food] should/do/can/could I/we eat/try/have/get/order/grab"
    r"|\b(?:what|which)(?:\s+(?:food|meal|dish|dishes|place|places|"
    r"restaurant|restaurants|option|options|cuisine|cuisines))?"
    r"\s+(?:should|do|can|could)\s+(?:i|we)\s+"
    r"(?:eat|try|have|get|order|grab)\b"
    # "what/which [food] to eat/try/have/get/order/grab"
    r"|\b(?:what|which)(?:\s+(?:food|meal|dish|dishes|place|places|"
    r"restaurant|restaurants|option|options))?"
    r"\s+to\s+(?:eat|try|have|get|order|grab)\b"
    # "what's/what is [the/a] [best] [food/place] (to) eat/try/..."
    r"|\bwhat(?:'s| is)\s+(?:the\s+|a\s+|an\s+)?"
    r"(?:best\s+|good\s+|nice\s+|great\s+)?"
    r"(?:food|meal|dish|dishes|place|places|restaurant|restaurants|"
    r"option|options)?\s*(?:to\s+)?(?:eat|try|have|order|get|grab)\b"
    # "what/which food is good/tasty/..."
    r"|\b(?:what|which)\s+(?:food|meal|dish|dishes|options?)\s+"
    r"(?:is|are)\s+(?:good|nice|great|best|tasty|delicious)\b"
    # "where should I/we eat"
    r"|\bwhere\s+should\s+(?:i|we)\s+eat\b",
    re.IGNORECASE,
)

# Object of a recommendation request, used to distinguish a generic ask
# ("recommend me something to eat") from a vendor-specific one
# ("find recommendations for Popeyes").
_RECOMMENDATION_TARGET_PATTERNS = (
    re.compile(
        r"\b(?:recommend(?:ed|ation|ations)?|suggest(?:ed|ion|ions)?)"
        r"\s+(?:at|about|for|of)\s+(.+)$",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:recommend(?:ed)?|suggest(?:ed)?)\s+(?:me|us)\s+(.+)$",
        re.IGNORECASE,
    ),
    re.compile(r"\brecommend(?:ed)?\s+(.+)$", re.IGNORECASE),
    re.compile(r"\bsuggest(?:ed)?\s+(.+)$", re.IGNORECASE),
)

# Filler words that carry no vendor identity, so an extracted recommendation
# object made only of these is a generic ask.
_RECOMMENDATION_FILLER_TOKENS = frozenset(
    {
        "a",
        "affordable",
        "an",
        "any",
        "anything",
        "around",
        "at",
        "bakery",
        "best",
        "bistro",
        "breakfast",
        "brunch",
        "cafe",
        "campus",
        "canteen",
        "cheap",
        "court",
        "cuisine",
        "delicious",
        "different",
        "dinner",
        "eat",
        "eatery",
        "else",
        "favorite",
        "favourite",
        "filling",
        "food",
        "for",
        "get",
        "good",
        "grab",
        "great",
        "have",
        "healthy",
        "here",
        "house",
        "i",
        "ideas",
        "in",
        "interesting",
        "kitchen",
        "kopitiam",
        "lunch",
        "meal",
        "meals",
        "me",
        "near",
        "nearby",
        "new",
        "nice",
        "ntu",
        "of",
        "on",
        "option",
        "options",
        "order",
        "place",
        "places",
        "popular",
        "recommendation",
        "recommendations",
        "restaurant",
        "restaurants",
        "shop",
        "snack",
        "some",
        "something",
        "somewhere",
        "stall",
        "stalls",
        "suggestion",
        "suggestions",
        "supper",
        "tasty",
        "the",
        "to",
        "try",
        "us",
        "vendor",
        "vendors",
        "we",
        "what",
        "where",
        "which",
        "you",
    }
)
# Qualitative requirements the saved profile cannot express. These asks must
# use retrieval/search over vendor evidence instead of preference ranking.
_RECOMMENDATION_CONTENT_QUALIFIER_RE = re.compile(
    r"(?<!\w)(?:"
    r"healthy|healthier|nutritious|wholesome|balanced|"
    r"light|hearty|filling|spicy|sweet|savoury|savory|"
    r"comfort(?:ing)?|refreshing|"
    r"low[\s-]?calorie|low[\s-]?carb|high[\s-]?protein|protein[\s-]?rich"
    r")(?!\w)",
    re.IGNORECASE,
)
_VENDOR_CLAUSE_PREFIX_RE = re.compile(
    r"^(?:where\s+(?:is|are)|where\s+can\s+i\s+find|"
    r"find\s+(?:the\s+)?(?:location|address)(?:\s+of)?|"
    r"(?:at|about|for|of))\s+",
    re.IGNORECASE,
)
_NON_VENDOR_CLAUSE_RE = re.compile(
    r"^(?:what|when|where|why|how|which|who|is|are|do|does|did|"
    r"can|could|would|should|will|tell|show|list|give|opening|closing|"
    r"please|thanks|also)\b",
    re.IGNORECASE,
)
_TRAILING_VENDOR_DETAIL_RE = re.compile(
    r"\s+(?:located|location|address|opening\s+hours?|closing\s+time|"
    r"open|closed|closes?)\s*$",
    re.IGNORECASE,
)
_GENERIC_VENDOR_REFERENCES = {
    "a place",
    "a restaurant",
    "a stall",
    "a vendor",
    "food",
    "it",
    "restaurant",
    "restaurants",
    "stall",
    "stalls",
    "that place",
    "the place",
    "the restaurant",
    "the stall",
    "the vendor",
    "there",
    "vendor",
    "vendors",
}


def _strip_trailing_filter_scope(
    candidate: str,
    filters: StructuredFilter,
) -> str:
    """Remove trailing location/cuisine qualifiers without losing pure filters."""

    stripped = candidate
    if filters.location:
        without_location = re.sub(
            rf"\s+(?:in|at|near|around)\s+(?:the\s+)?"
            rf"{re.escape(filters.location)}\s*$",
            "",
            stripped,
            flags=re.IGNORECASE,
        ).strip()
        if without_location:
            stripped = without_location

    if filters.cuisine:
        without_cuisine = re.sub(
            rf"\s+(?:(?:serving|selling|with|for)\s+)?"
            rf"{re.escape(filters.cuisine)}(?:\s+(?:food|cuisine))?\s*$",
            "",
            stripped,
            flags=re.IGNORECASE,
        ).strip()
        if without_cuisine:
            stripped = without_cuisine
    return stripped


def _looks_like_generic_recommendation(value: str) -> bool:
    """Return whether a target is only food or non-entity request language."""

    normalized_tokens = normalize_vendor_text(value).split()
    allowed_tokens = (
        _GENERIC_FOOD_TOKENS
        | _GENERIC_RECOMMENDATION_TOKENS
        | _RECOMMENDATION_FILLER_TOKENS
        | _GENERIC_REQUEST_LANGUAGE_TOKENS
    )
    return bool(normalized_tokens) and all(
        token in allowed_tokens for token in normalized_tokens
    )


def _looks_like_vendor_brand(value: str) -> bool:
    """Recognize a non-food entity in an explicit vendor-object phrase."""

    normalized_tokens = normalize_vendor_text(value).split()
    return (
        bool(normalized_tokens)
        and not _looks_like_generic_recommendation(value)
        and any(
            any(character.isalpha() for character in token)
            for token in normalized_tokens
        )
    )


def _is_simple_conversation(question: str) -> bool:
    normalized = re.sub(r"[^\w\s']", "", question.casefold())
    return " ".join(normalized.split()) in _SIMPLE_CONVERSATION


def _vendor_confirmation_intent(question: str) -> str | None:
    """Classify a short standalone reply to a vendor clarification."""

    folded = question.casefold().replace("’", "'")
    normalized = re.sub(r"[^\w\s']", " ", folded).replace("'", "")
    normalized = " ".join(normalized.split())
    if normalized in _AFFIRMATIVE_VENDOR_CONFIRMATIONS:
        return "affirmative"
    if normalized in _NEGATIVE_VENDOR_CONFIRMATIONS:
        return "negative"
    return None


def _vendor_clarification_suggestions(answer: str) -> str | None:
    """Return only the suggested-name span from a service clarification.

    An empty string represents a recognized generic clarification with no
    concrete candidate. ``None`` means the preceding answer was not one of the
    service's vendor clarification templates.
    """

    stripped = answer.strip()
    suggested = _SUGGESTED_VENDOR_CLARIFICATION_RE.fullmatch(stripped)
    if suggested is not None:
        return suggested.group("suggestions")
    if _GENERIC_VENDOR_CLARIFICATION_RE.fullmatch(stripped) is not None:
        return ""
    return None


def _is_referential(question: str) -> bool:
    return bool(_REFERENTIAL_HINTS.search(question))

def build_prompt(
    question: str,
    context: str,
    template: str | None = None,
    history: list[ChatHistoryMessage] | None = None,
) -> str:
    """Fill ``{user_question}`` / ``{context}`` placeholders in a template.

    Falls back to ``DEFAULT_SYSTEM_PROMPT`` when no template is provided.
    """
    prompt = template if template else DEFAULT_SYSTEM_PROMPT
    conversation_history = format_conversation_history(history or [])
    rendered = prompt.format(
        user_question=question,
        context=context,
        conversation_history=conversation_history,
    )
    if template and "{conversation_history}" not in template and history:
        return (
            "Current-session conversation history:\n"
            f"{conversation_history}\n\n{rendered}"
        )
    return rendered


def format_conversation_history(history: list[ChatHistoryMessage]) -> str:
    trimmed = trim_chat_history(history)
    if not trimmed:
        return EMPTY_CONVERSATION
    labels = {"user": "User", "assistant": "Foodie"}
    return "\n".join(
        f"{labels[message.role]}: {message.content}" for message in trimmed
    )


def build_contextual_question(
    question: str,
    history: list[ChatHistoryMessage],
) -> str:
    """Prioritize the current question and add only recent turn context."""
    turns: list[list[ChatHistoryMessage]] = []
    current_turn: list[ChatHistoryMessage] = []
    for message in trim_chat_history(history):
        if message.role == "user" and current_turn:
            turns.append(current_turn)
            current_turn = []
        current_turn.append(message)
    if current_turn:
        turns.append(current_turn)

    recent_turns = turns[-MAX_CONTEXTUAL_TURNS:]
    if not recent_turns:
        return question

    sections = [
        "=== CURRENT QUESTION (use this to determine intent) ===",
        question,
        "=== RECENT CONVERSATION (context for follow-up references only) ===",
    ]
    for index, turn in enumerate(recent_turns, start=1):
        sections.append(f"--- TURN {index} ---")
        sections.append(format_conversation_history(turn))
    return "\n".join(sections)


def format_context(
    results: list[KnowledgeResult],
    vendor_names: dict[int, str] | None = None,
) -> str:
    """Render retrieved chunks into a numbered context block.

    Each chunk is prefixed with its source type and (when known) vendor name so
    the model can attribute a review to a specific food stall.
    """
    if not results:
        return EMPTY_CONTEXT

    lines = []
    for index, result in enumerate(results, start=1):
        prefix = f"[{index}] ({result.source_type})"
        if vendor_names and result.vendor_id is not None:
            name = vendor_names.get(result.vendor_id)
            if name:
                prefix += f" {name}"
        lines.append(f"{prefix}: {result.content}")
    return "\n\n".join(lines)


def format_sql_context(results: list[SqlResult]) -> str:
    """Render structured SQL rows into a numbered context block."""
    if not results:
        return EMPTY_CONTEXT

    lines = []
    for index, result in enumerate(results, start=1):
        if result.count is not None:
            lines.append(f"[{index}] (count): {result.count}")
            continue

        name = result.vendor_name or "Unknown"
        attributes = []
        if result.location:
            attributes.append(f"location={result.location}")
        if result.address:
            attributes.append(f"address={result.address}")
        if result.category:
            attributes.append(f"category={result.category}")
        if result.price_range:
            attributes.append(f"price={result.price_range}")
        if result.opening_hours:
            attributes.append(f"hours={result.opening_hours}")
        if result.halal is not None:
            attributes.append(f"halal={'yes' if result.halal else 'no'}")
        if result.vegetarian is not None:
            attributes.append(
                f"vegetarian={'yes' if result.vegetarian else 'no'}"
            )
        rating = result.average_rating
        if rating is None:
            rating = result.average_google_rating
        if rating is not None:
            attributes.append(f"rating={rating}")
        if result.review_count is not None:
            attributes.append(f"reviews={result.review_count}")

        detail = "; ".join(attributes)
        lines.append(f"[{index}] {name}: {detail}" if detail else f"[{index}] {name}")
    return "\n".join(lines)


_PREFERENCE_FIELD_LABELS = (
    ("cuisines", "Preferred cuisines"),
    ("locations", "Preferred locations"),
    ("dietary_restrictions", "Dietary restrictions"),
    ("likes", "Likes"),
    ("dislikes", "Dislikes"),
    ("lifestyle", "Lifestyle"),
)


def _describe_preferences(
    preferences: UserFoodPreferences,
) -> list[str]:
    """Return non-empty saved preference fields as ``Label: values`` lines."""

    lines: list[str] = []
    for field_name, label in _PREFERENCE_FIELD_LABELS:
        values = [
            str(value).strip()
            for value in (getattr(preferences, field_name, None) or [])
            if str(value).strip()
        ]
        if values:
            lines.append(f"{label}: {', '.join(values)}")
    return lines


def format_recommendation_context(
    recommendations: list[VendorRecommendation],
    preferences: UserFoodPreferences,
) -> str:
    """Render preference-ranked vendors into a numbered context block."""

    if not recommendations:
        return EMPTY_CONTEXT

    lines: list[str] = []
    preference_lines = _describe_preferences(preferences)
    if preference_lines:
        lines.append("User's saved food preferences:")
        lines.extend(f"- {line}" for line in preference_lines)
        lines.append("")

    lines.append("Recommended vendors (best match first):")
    for index, recommendation in enumerate(recommendations, start=1):
        vendor = recommendation.vendor
        attributes: list[str] = []
        if vendor.location:
            attributes.append(f"location={vendor.location}")
        if vendor.category:
            attributes.append(f"category={vendor.category}")
        if vendor.price_range:
            attributes.append(f"price={vendor.price_range}")
        if vendor.opening_hours:
            attributes.append(f"hours={vendor.opening_hours}")
        if vendor.halal is not None:
            attributes.append(f"halal={'yes' if vendor.halal else 'no'}")
        if vendor.vegetarian is not None:
            attributes.append(
                f"vegetarian={'yes' if vendor.vegetarian else 'no'}"
            )
        rating = (
            vendor.average_rating
            if vendor.average_rating is not None
            else vendor.average_google_rating
        )
        if rating is not None:
            attributes.append(f"rating={rating}")
        detail = "; ".join(attributes)
        lines.append(
            f"[{index}] {vendor.name}: {detail}"
            if detail
            else f"[{index}] {vendor.name}"
        )
    return "\n".join(lines)


def _preference_alignment_note(
    preferences: UserFoodPreferences | None,
) -> str | None:
    """Return an instruction to call out preference fit for SQL/hybrid rows."""

    if preferences is None:
        return None
    preference_lines = _describe_preferences(preferences)
    if not preference_lines:
        return None
    return (
        "Personalisation note: this user has saved the following food "
        "preferences:\n"
        + "\n".join(f"- {line}" for line in preference_lines)
        + "\nWhen a vendor above matches these preferences (for example "
        "cuisine, dietary needs, budget, location, or liked dishes), briefly "
        "mention in your answer how it suits the user. Only rely on vendor "
        "facts shown in the context."
    )


def _recommendation_target_is_generic(question: str) -> bool:
    """Return whether a recommendation request has no specific object.

    ``recommend me something to eat`` is generic, while ``find recommendations
    for Popeyes`` names a vendor and must keep normal vendor routing.
    """

    for pattern in _RECOMMENDATION_TARGET_PATTERNS:
        target_match = pattern.search(question)
        if target_match is None:
            continue
        tokens = normalize_vendor_text(target_match.group(1)).split()
        return bool(tokens) and all(
            token in _RECOMMENDATION_FILLER_TOKENS for token in tokens
        )
    return True


# Upstream statuses that can still succeed if the same request is sent again.
_RETRYABLE_STATUS_CODES = frozenset({408, 429, 500, 502, 503, 504})


def _is_retryable_stream_error(error: BaseException) -> bool:
    """Return whether a failed generation attempt might succeed on retry."""
    if isinstance(error, errors.APIError):
        return error.code in _RETRYABLE_STATUS_CODES
    return isinstance(error, (TimeoutError, ConnectionError, httpx.TransportError))


def _stream_retry_delay(
    error: BaseException,
    *,
    attempt: int,
    attempts: int,
    emitted: bool,
    elapsed: float,
    timeout_seconds: float,
) -> float | None:
    """Return the backoff before replaying a failed stream, or None to give up.

    A stream is only replayable while it has not reached the user: once any
    text is visible a second attempt would duplicate the answer. A request that
    already burned its whole timeout is not retried either -- the model
    stalled, so repeating it would only double the wait before the user sees
    anything.
    """
    if emitted or attempt >= attempts:
        return None
    if elapsed >= timeout_seconds or not _is_retryable_stream_error(error):
        return None
    return min(
        settings.chat_retry_initial_delay_ms / 1000 * 2 ** (attempt - 1),
        settings.chat_retry_max_delay_ms / 1000,
    )


class ChatService:
    """RAG chat service that routes questions across SQL, Vector, and hybrid.

    With no ``router`` configured the service stays vector-only (the legacy
    behaviour). Otherwise it classifies each question and branches on the
    matched intent's ``search_type``.
    """

    def __init__(
        self,
        embedder: Embedder,
        store: KnowledgeStore,
        *,
        model: str = settings.chat_model,
        top_k: int = settings.vector_top_k,
        generate: Callable[[str], str] | None = None,
        generate_stream: Callable[[str], Iterator[str]] | None = None,
        client: object | None = None,
        router: IntentRouter | None = None,
        sql_store: SqlStore | None = None,
        filter_extractor_llm: Callable[[str], StructuredFilter] | None = None,
        rewrite_llm: Callable[[str, list[ChatHistoryMessage]], str] | None = None,
        session: Session | None = None,
        recommend_fn: (
            Callable[[UserFoodPreferences], list[VendorRecommendation]] | None
        ) = None,
    ) -> None:
        self._embedder = embedder
        self._store = store
        self._model = model
        self._top_k = top_k
        self._generate_fn = generate
        self._generate_stream_fn = generate_stream
        self._router = router
        self._sql_store = sql_store
        self._filter_extractor_llm = filter_extractor_llm
        self._rewrite_llm = rewrite_llm
        self._session = session
        self._client = client
        self._recommend_fn = recommend_fn
        self._vendor_rows_cache: list[tuple[int, str]] | None = None

    def answer(
        self,
        question: str,
        *,
        history: list[ChatHistoryMessage] | None = None,
        current_user: User | None = None,
    ) -> ChatResponse:
        generation = self._prepare_answer(
            question,
            history=history,
            current_user=current_user,
        )
        answer = generation.direct_answer
        if answer is None:
            try:
                answer = self._generate(generation.prompt)
                if not answer or not answer.strip():
                    raise ValueError("Empty model answer")
            except Exception:
                logger.warning("Chat generation failed; returning retrieved facts", exc_info=True)
                answer = self._fallback_answer(generation.sources)
        return ChatResponse(
            answer=answer,
            sources=generation.sources,
            search_type=generation.search_type,
            intent=generation.intent,
        )

    def stream_answer(
        self,
        question: str,
        *,
        history: list[ChatHistoryMessage] | None = None,
        current_user: User | None = None,
    ) -> Iterator[tuple[str, str | list[ChatSource] | None]]:
        """Yield generated text deltas followed by the response sources."""
        generation = self._prepare_answer(
            question,
            history=history,
            current_user=current_user,
        )
        if generation.direct_answer is not None:
            yield "delta", generation.direct_answer
        else:
            emitted = False
            try:
                for text in self._generate_stream(generation.prompt):
                    if text and (emitted or text.strip()):
                        emitted = True
                        yield "delta", text
                if not emitted:
                    raise ValueError("Empty model answer")
            except Exception:
                # Once text is visible, do not append a second answer or mark
                # an incomplete response as successful with a sources event.
                if emitted:
                    raise
                logger.warning("Chat generation failed; returning retrieved facts", exc_info=True)
                yield "delta", self._fallback_answer(generation.sources)
        yield "sources", generation.sources

    @staticmethod
    def _fallback_answer(sources: list[ChatSource]) -> str:
        """Show retrieved evidence without requiring another model call."""
        facts: list[str] = []
        for index, source in enumerate(sources, start=1):
            if source.count is not None:
                fact = f"Matching vendors: {source.count}"
            elif source.source_type == "vendor":
                details = [value for value in (
                    source.location, source.unit_code, source.category,
                    source.price_range, source.opening_hours,
                ) if value]
                fact = ": ".join(filter(None, (
                    source.vendor_name, "; ".join(details),
                )))
            else:
                fact = ": ".join(filter(None, (source.vendor_name, source.excerpt)))
            if fact:
                facts.append(f"- {fact} [{index}]")
        if not facts:
            return "Foodie is temporarily unavailable. Please try again in a moment."
        return (
            "I couldn't generate a full answer right now. "
            "Here is the information I found:\n\n" + "\n".join(facts)
        )

    def _prepare_answer(
        self,
        question: str,
        *,
        history: list[ChatHistoryMessage] | None = None,
        current_user: User | None = None,
    ) -> ChatGeneration:
        # Keep vendor data stable and query it at most once per answer.
        self._vendor_rows_cache = None

        # The current question counts as one of the five retained user messages.
        # Append it while trimming, then remove the duplicate current-question
        # entry because prompts render it separately below.
        history_with_question = trim_chat_history(
            [
                *(history or []),
                ChatHistoryMessage(role="user", content=question),
            ]
        )
        history = history_with_question[:-1]
        confirmation_resolution = self._resolve_vendor_confirmation(
            question,
            history,
        )
        if isinstance(confirmation_resolution, ChatGeneration):
            return confirmation_resolution

        effective_question = confirmation_resolution or question
        if confirmation_resolution is not None:
            # The accepted suggestion reconstructs the original request with
            # the official vendor name, so it is already standalone and must
            # be re-routed as that request rather than as the bare word "yes".
            routing_question = effective_question
        elif _is_simple_conversation(question):
            return ChatGeneration(
                prompt=build_prompt(question, EMPTY_CONTEXT, history=history),
                sources=[],
                search_type="Conversational",
                intent=None,
            )
        else:
            routing_question = self._resolve_routing_question(question, history)

        # Preferences are only needed for personalised recommendations and the
        # SQL/hybrid alignment note, so load them at most once per answer.
        preferences = self._load_preferences(current_user)

        if (
            preferences is not None
            and self._is_personal_recommendation_request(routing_question)
        ):
            recommendation = self._prepare_recommendation(
                effective_question,
                preferences,
                history,
            )
            if recommendation is not None:
                return recommendation

        if self._router is None:
            logger.info("No intent router configured; using Vector path")
            return self._prepare_vector(
                effective_question,
                match=None,
                history=history,
                retrieval_question=routing_question,
                query_vector=None,
            )

        match = self._router.classify(routing_question)
        vendor_matches = self._match_vendor_names(routing_question)
        if (
            match.search_type != "SQL"
            and self._should_force_vendor_sql(routing_question, vendor_matches)
        ):
            logger.info(
                "Recognized vendor location lookup; overriding %s route with SQL",
                match.search_type,
            )
            match = replace(match, search_type="SQL", tier=1)
        if (
            match.search_type in {"SQL", "SQL + Vector"}
            and self._sql_store is None
        ):
            logger.warning(
                "Cannot execute %s route because no SQL store is configured",
                match.search_type,
            )
            return ChatGeneration(
                prompt="",
                sources=[],
                search_type=match.search_type,
                intent=match.intent_key,
                direct_answer=(
                    "Structured vendor search is temporarily unavailable. "
                    "Please try again later."
                ),
            )
        logger.info("Executing chatbot answer via search_type=%s", match.search_type)
        if match.search_type == "SQL":
            return self._prepare_sql(
                effective_question,
                match,
                history,
                routing_question,
                preferences=preferences,
            )
        if match.search_type == "SQL + Vector":
            return self._prepare_hybrid(
                effective_question,
                match,
                history,
                routing_question,
                query_vector=match.query_vector,
                preferences=preferences,
            )
        return self._prepare_vector(
            effective_question,
            match,
            history=history,
            retrieval_question=routing_question,
            query_vector=match.query_vector,
        )

    def _resolve_vendor_confirmation(
        self,
        question: str,
        history: list[ChatHistoryMessage],
    ) -> str | ChatGeneration | None:
        """Resolve yes/no replies to the immediately preceding clarification.

        A positive reply is accepted only when the clarification contains one
        distinct official vendor name and the preceding user request contains
        one unresolved vendor-like phrase. This preserves the original intent
        (location, price, reviews, dietary constraints, and so on) while
        replacing only the misspelled name. Multiple branch rows with the same
        official name intentionally remain one selectable vendor and are all
        resolved later by normal matching.
        """

        confirmation = _vendor_confirmation_intent(question)
        if confirmation is None or not history or history[-1].role != "assistant":
            return None

        clarification = history[-1].content
        suggestion_text = _vendor_clarification_suggestions(clarification)
        if suggestion_text is None:
            return None

        if confirmation == "negative":
            logger.info("Vendor clarification was rejected by the user")
            return self._vendor_confirmation_reply(
                "Okay - please type the vendor name you meant, and I will look it up."
            )

        vendors = self._vendor_rows()
        suggested_matches = match_vendor_mentions(suggestion_text, vendors)
        suggested_names: dict[str, str] = {}
        for _, vendor_name in suggested_matches:
            brand_key = vendor_brand_key(vendor_name)
            if brand_key:
                suggested_names.setdefault(brand_key, vendor_name)

        if not suggested_names:
            logger.info("Vendor confirmation had no concrete suggestion to accept")
            return self._vendor_confirmation_reply(
                "I still need the vendor name because there is no specific "
                "suggestion to confirm. Please type the vendor name you meant."
            )
        if len(suggested_names) > 1:
            choices = ", ".join(suggested_names.values())
            logger.info(
                "Vendor confirmation was ambiguous across %d suggestions",
                len(suggested_names),
            )
            return self._vendor_confirmation_reply(
                f"I found multiple possible vendors: {choices}. Please reply "
                "with the exact vendor name so I know which one to use."
            )

        previous_question = next(
            (
                message.content
                for message in reversed(history[:-1])
                if message.role == "user"
            ),
            None,
        )
        if previous_question is None:
            logger.info("Vendor confirmation had no preceding user request")
            return self._vendor_confirmation_reply(
                "Please type the vendor name and what you want to know about it."
            )

        previous_matches = match_vendor_mentions(previous_question, vendors)
        unresolved = self._suspected_unresolved_vendor_names(
            previous_question,
            vendors,
            previous_matches,
        )
        if len(unresolved) != 1:
            logger.info(
                "Vendor confirmation could not identify one unresolved name; found %d",
                len(unresolved),
            )
            return self._vendor_confirmation_reply(
                "I could not safely connect that confirmation to one vendor. "
                "Please type the exact vendor name and your question."
            )

        official_name = next(iter(suggested_names.values()))
        resolved_question, replacements = re.subn(
            re.escape(unresolved[0]),
            lambda _match: official_name,
            previous_question,
            count=1,
            flags=re.IGNORECASE,
        )
        if replacements != 1:
            logger.info("Vendor confirmation target was not replaceable in prior request")
            return self._vendor_confirmation_reply(
                "I could not safely restore the earlier request. Please type the "
                "exact vendor name and your question."
            )

        logger.info(
            "Resolved vendor confirmation %r to %r",
            question,
            resolved_question,
        )
        return resolved_question

    @staticmethod
    def _vendor_confirmation_reply(answer: str) -> ChatGeneration:
        return ChatGeneration(
            prompt="",
            sources=[],
            search_type="Conversational",
            intent=None,
            direct_answer=answer,
        )

    def _resolve_routing_question(
        self,
        question: str,
        history: list[ChatHistoryMessage],
    ) -> str:
        """Resolve a follow-up into a standalone question for routing/retrieval.

        Routing and retrieval must operate on the *current* question, never on a
        history-wrapped block: structural cues and embeddings from earlier turns
        could misroute or pollute the query. History is only consulted when
        the question is referential, and only an LLM rewrite is allowed to
        resolve those references. Without a rewrite callable (or on failure) the
        bare question is used and the safe Vector default absorbs the follow-up.
        """
        if not history or not _is_referential(question):
            return question
        if self._rewrite_llm is None:
            return question
        try:
            resolved = self._rewrite_llm(question, history).strip()
        except Exception:
            logger.warning("Question rewrite failed; using bare question", exc_info=True)
            return question
        return resolved or question

    def _load_preferences(
        self,
        current_user: User | None,
    ) -> UserFoodPreferences | None:
        """Return completed preferences for the request user, if any."""

        if current_user is None or self._session is None:
            return None
        preferences = self._session.scalar(
            select(UserFoodPreferences).where(
                UserFoodPreferences.user_id == current_user.id
            )
        )
        if preferences is None or preferences.onboarding_status != "completed":
            return None
        return preferences

    def _is_personal_recommendation_request(self, question: str) -> bool:
        """Return whether the question asks for preference-based picks.

        Only attribute-free asks qualify. A named (or likely vendor-named)
        object, an explicit cuisine/location/dietary/budget scope, or a
        qualitative requirement such as "healthy" keeps normal SQL/Vector
        routing so specific queries are not replaced by preference ranking.
        """

        if _RECOMMENDATION_REQUEST_RE.search(question) is None:
            return False
        if self._match_vendor_names(question):
            return False
        if not _recommendation_target_is_generic(question):
            return False
        if _RECOMMENDATION_CONTENT_QUALIFIER_RE.search(question):
            return False
        return not _has_scope_constraint(extract_structured_filters(question))

    def _prepare_recommendation(
        self,
        question: str,
        preferences: UserFoodPreferences,
        history: list[ChatHistoryMessage],
    ) -> ChatGeneration | None:
        """Rank vendors by preference, or return None to use normal routing."""

        if self._recommend_fn is None:
            return None

        try:
            recommendations = self._recommend_fn(preferences)
        except Exception:
            logger.warning(
                "Vendor recommendation failed; falling back to normal routing",
                exc_info=True,
            )
            return None

        if not recommendations:
            logger.info(
                "No vendor recommendations matched the user's preferences; "
                "falling back to normal routing"
            )
            return None

        logger.info(
            "Personalised recommendation path returned %d vendor(s)",
            len(recommendations),
        )
        context = format_recommendation_context(recommendations, preferences)
        prompt = build_prompt(
            question,
            context,
            template=RECOMMENDATION_PROMPT,
            history=history,
        )
        return ChatGeneration(
            prompt=prompt,
            sources=[
                self._to_recommendation_source(recommendation)
                for recommendation in recommendations
            ],
            search_type="Recommendation",
            intent="vendor_recommendation",
        )

    @staticmethod
    def _to_recommendation_source(
        recommendation: VendorRecommendation,
    ) -> ChatSource:
        vendor = recommendation.vendor
        rating = (
            vendor.average_rating
            if vendor.average_rating is not None
            else vendor.average_google_rating
        )
        return ChatSource(
            source_type="vendor",
            source_id=str(vendor.id) if vendor.id is not None else None,
            vendor_id=vendor.id,
            vendor_name=vendor.name,
            location=vendor.location,
            unit_code=vendor.unit_code,
            category=vendor.category,
            price_range=vendor.price_range,
            opening_hours=vendor.opening_hours,
            rating=None if rating is None else float(rating),
        )

    def _prepare_vector(
        self,
        question: str,
        match: IntentMatch | None,
        history: list[ChatHistoryMessage],
        retrieval_question: str,
        query_vector: list[float] | None,
    ) -> ChatGeneration:
        vendors = self._vendor_rows()
        unresolved = self._suspected_unresolved_vendor_names(
            retrieval_question,
            vendors,
            match_vendor_mentions(retrieval_question, vendors),
        )
        if unresolved:
            return self._prepare_vendor_clarification(
                StructuredFilter(vendor_names=unresolved),
                match,
                search_type="Vector",
            )

        vector_filters = self._build_vector_filters(retrieval_question)
        results = self._search_direct_reddit(retrieval_question, vector_filters)
        if not results:
            query_vector = query_vector or self._embedder.embed([retrieval_question])[0]
            results = self._store.search(
                query_vector,
                limit=self._top_k,
                filters=vector_filters or None,
            )
        vendor_names = self._store.resolve_vendor_names(
            {result.vendor_id for result in results if result.vendor_id is not None}
        )
        context = format_context(results, vendor_names)
        prompt = build_prompt(
            question,
            context,
            template=match.prompt_template if match else None,
            history=history,
        )
        reddit_permalinks = self._resolve_reddit_permalinks(results)
        google_maps_urls = self._resolve_google_review_maps_urls(results)

        return ChatGeneration(
            prompt=prompt,
            sources=[
                self._to_source(
                    result,
                    vendor_names,
                    reddit_permalinks,
                    google_maps_urls,
                )
                for result in results
            ],
            search_type="Vector",
            intent=match.intent_key if match else None,
        )

    def _prepare_sql(
        self,
        question: str,
        match: IntentMatch,
        history: list[ChatHistoryMessage],
        retrieval_question: str,
        *,
        preferences: UserFoodPreferences | None = None,
    ) -> ChatGeneration:
        filters = self._resolve_filters(retrieval_question)
        if filters.vendor_names:
            return self._prepare_vendor_clarification(filters, match)
        if (
            not _has_scope_constraint(filters)
            and _VENDOR_SQL_LOOKUP_RE.search(retrieval_question)
        ):
            logger.info(
                "SQL lookup did not identify a bounded vendor filter; asking "
                "for clarification"
            )
            return self._prepare_vendor_clarification(filters, match)

        logger.info("SQL path filters: %s", _describe_filters(filters))
        results = self._sql_store.search(filters)
        logger.info("SQL path returned %d vendor result(s)", len(results))
        should_retry = _sql_results_are_empty(results) and not (
            filters.query_kind == "count"
            and not _has_scope_constraint(filters)
        )
        if should_retry:
            retry_filters = self._retry_filters_with_llm(
                retrieval_question,
                query_shape=filters,
            )
            if retry_filters is not None:
                if retry_filters.vendor_names:
                    return self._prepare_vendor_clarification(retry_filters, match)
                filters = retry_filters
                logger.info(
                    "SQL path returned no vendors; retrying with LLM filters: %s",
                    _describe_filters(filters),
                )
                results = self._sql_store.search(filters)
                logger.info(
                    "LLM-corrected SQL path returned %d vendor result(s)",
                    len(results),
                )

            if _sql_results_are_empty(results):
                clarification = self._clarify_failed_vendor_lookup(
                    retrieval_question,
                    filters,
                    match,
                )
                if clarification is not None:
                    return clarification

            if _sql_results_are_empty(results) and _has_scope_constraint(filters):
                logger.info(
                    "Scoped SQL lookup still returned no vendors; returning a "
                    "bounded no-match response"
                )
                return self._prepare_no_matching_vendors(
                    match,
                    search_type="SQL",
                )

            if _sql_results_are_empty(results) and filters.query_kind == "list":
                logger.info(
                    "SQL list path still returned no vendors; falling back to "
                    "filtered Vector search"
                )
                return self._prepare_vector(
                    question,
                    match=None,
                    history=history,
                    retrieval_question=retrieval_question,
                    query_vector=match.query_vector,
                )
        context = format_sql_context(results)
        preference_note = _preference_alignment_note(preferences)
        if preference_note:
            context = f"{context}\n\n{preference_note}"
        prompt = build_prompt(
            question,
            context,
            template=match.prompt_template,
            history=history,
        )
        return ChatGeneration(
            prompt=prompt,
            sources=[self._to_sql_source(result) for result in results],
            search_type="SQL",
            intent=match.intent_key,
        )

    def _prepare_hybrid(
        self,
        question: str,
        match: IntentMatch,
        history: list[ChatHistoryMessage],
        retrieval_question: str,
        *,
        query_vector: list[float] | None,
        preferences: UserFoodPreferences | None = None,
    ) -> ChatGeneration:
        filters = self._resolve_filters(retrieval_question)
        if filters.vendor_names:
            return self._prepare_vendor_clarification(
                filters,
                match,
                search_type="SQL + Vector",
            )

        logger.info("Hybrid path filters: %s", _describe_filters(filters))
        vendor_ids = self._sql_store.resolve_vendor_ids(filters)
        logger.info("Hybrid path resolved %d vendor_id(s): %s", len(vendor_ids), vendor_ids)
        if _has_scope_constraint(filters) and not vendor_ids:
            retry_filters = self._retry_filters_with_llm(
                retrieval_question,
                query_shape=filters,
            )
            if retry_filters is not None:
                if retry_filters.vendor_names:
                    return self._prepare_vendor_clarification(
                        retry_filters,
                        match,
                        search_type="SQL + Vector",
                    )
                filters = retry_filters
                logger.info(
                    "Hybrid filters resolved no vendors; retrying with LLM "
                    "filters: %s",
                    _describe_filters(filters),
                )
                vendor_ids = self._sql_store.resolve_vendor_ids(filters)
                logger.info(
                    "LLM-corrected hybrid path resolved %d vendor_id(s): %s",
                    len(vendor_ids),
                    vendor_ids,
                )

            if not vendor_ids:
                clarification = self._clarify_failed_vendor_lookup(
                    retrieval_question,
                    filters,
                    match,
                    search_type="SQL + Vector",
                )
                if clarification is not None:
                    return clarification
                return self._prepare_no_matching_vendors(
                    match,
                    search_type="SQL + Vector",
                )

        query_vector = query_vector or self._embedder.embed([retrieval_question])[0]
        results = self._store.search(
            query_vector,
            limit=self._top_k,
            filters={
                **self._build_vector_filters(retrieval_question),
                "vendor_ids": vendor_ids,
            },
        )
        logger.info("Hybrid path retrieved %d knowledge chunk(s)", len(results))
        vendor_names = self._store.resolve_vendor_names(
            {result.vendor_id for result in results if result.vendor_id is not None}
        )
        context = format_context(results, vendor_names)
        preference_note = _preference_alignment_note(preferences)
        if preference_note:
            context = f"{context}\n\n{preference_note}"
        prompt = build_prompt(
            question,
            context,
            template=match.prompt_template,
            history=history,
        )
        reddit_permalinks = self._resolve_reddit_permalinks(results)
        google_maps_urls = self._resolve_google_review_maps_urls(results)
        return ChatGeneration(
            prompt=prompt,
            sources=[
                self._to_source(
                    result,
                    vendor_names,
                    reddit_permalinks,
                    google_maps_urls,
                )
                for result in results
            ],
            search_type="SQL + Vector",
            intent=match.intent_key,
        )

    def _resolve_filters(self, question: str) -> StructuredFilter:
        filters = extract_structured_filters(question)
        vendors = self._vendor_rows()
        matches = match_vendor_mentions(question, vendors)
        unresolved_candidates = self._suspected_unresolved_vendor_names(
            question,
            vendors,
            matches,
        )
        if matches:
            filters.vendor_ids = [vendor_id for vendor_id, _ in matches]
            if filters.location and any(
                normalize_vendor_text(filters.location)
                in normalize_vendor_text(name)
                for _, name in matches
            ):
                filters.location = None
            if filters.cuisine and any(
                normalize_vendor_text(filters.cuisine)
                in normalize_vendor_text(name)
                for _, name in matches
            ):
                filters.cuisine = None

        if unresolved_candidates:
            # Keep deterministic evidence for every unresolved coordinated
            # phrase.  The LLM may add useful structure, but an unavailable,
            # empty, or mistaken extraction must never silently discard an
            # unknown vendor or broaden retrieval.
            filters.vendor_names = unresolved_candidates
            if self._filter_extractor_llm is not None:
                llm_filters = self._extract_llm_filters(question)
                if llm_filters is not None:
                    filters = _merge_structured_filters(filters, llm_filters)
        if (
            filters.query_kind == "list"
            and not filters.has_constraints
            and self._filter_extractor_llm is not None
        ):
            llm_filters = self._extract_llm_filters(question)
            if llm_filters is not None:
                filters = llm_filters
        filters = self._resolve_filter_vendor_names(filters)
        # A vendor-scoped schedule question must return that vendor even when it
        # is closed on the requested day, so the answer can say "closed" instead
        # of "no matching vendors". List/count questions keep the day filter.
        if filters.vendor_ids and _VENDOR_SCHEDULE_LOOKUP_RE.search(question):
            filters.open_hours = None
            filters.exclude_open_hours = None
        return filters

    @staticmethod
    def _suspected_unresolved_vendor_names(
        question: str,
        vendors: list[tuple[int, str]],
        matches: list[tuple[int, str]],
    ) -> list[str]:
        """Extract vendor-like clauses that deterministic matching missed.

        This is intentionally conservative.  It only inspects the object of a
        vendor lookup/evidence phrase, or coordinated clauses next to a known
        vendor.  Question continuations (``and when does it close?``) and real
        structured filters (``Korean``, ``North Spine``) are not vendor names.
        """

        target: str | None = None
        for pattern in _VENDOR_TARGET_PATTERNS:
            target_match = pattern.search(question)
            if target_match is not None:
                target = target_match.group(1)
                break

        if target is None:
            if not matches or _MULTI_VENDOR_HINT_RE.search(question) is None:
                return []
            target = question

        candidates: list[str] = []
        seen: set[str] = set()
        coordinated_with_known_vendor = bool(
            matches and _MULTI_VENDOR_HINT_RE.search(target)
        )
        matched_name_forms = {
            normalize_vendor_text(name) for _, name in matches
        }
        for clause in _MULTI_VENDOR_HINT_RE.split(target):
            candidate = _VENDOR_CLAUSE_PREFIX_RE.sub("", clause.strip())
            candidate = re.sub(
                r"\s+(?:in|at)\s+ntu(?:\s+campus)?\s*$",
                "",
                candidate,
                flags=re.IGNORECASE,
            )
            candidate = _TRAILING_VENDOR_DETAIL_RE.sub("", candidate)
            candidate = candidate.strip(" \t\r\n?.!;:'\"")
            if not candidate or _NON_VENDOR_CLAUSE_RE.search(candidate):
                continue

            normalized = normalize_vendor_text(candidate)
            if not normalized or normalized in _GENERIC_VENDOR_REFERENCES:
                continue
            if any(normalized in name for name in matched_name_forms):
                continue
            if match_vendor_mentions(candidate, vendors):
                continue

            candidate_filters = extract_structured_filters(candidate)
            candidate = _strip_trailing_filter_scope(candidate, candidate_filters)
            normalized = normalize_vendor_text(candidate)
            if not normalized or normalized in _GENERIC_VENDOR_REFERENCES:
                continue
            if any(normalized in name for name in matched_name_forms):
                continue
            if match_vendor_mentions(candidate, vendors):
                continue
            if extract_structured_filters(candidate).has_constraints:
                continue
            if _looks_like_generic_recommendation(candidate):
                continue
            if not (
                coordinated_with_known_vendor
                or _VENDOR_TYPE_CUE_RE.search(candidate)
                or suggest_vendor_names([candidate], vendors, limit=1)
                or _looks_like_vendor_brand(candidate)
            ):
                continue
            if normalized in seen:
                continue
            candidates.append(candidate)
            seen.add(normalized)
        return candidates

    def _extract_llm_filters(self, question: str) -> StructuredFilter | None:
        if self._filter_extractor_llm is None:
            return None
        try:
            return extract_structured_filters_llm(
                question,
                self._filter_extractor_llm,
            )
        except Exception:
            logger.warning("LLM filter extraction failed", exc_info=True)
            return None

    def _retry_filters_with_llm(
        self,
        question: str,
        *,
        query_shape: StructuredFilter,
    ) -> StructuredFilter | None:
        """Give a zero-result SQL lookup one deterministic-first retry."""
        supplemental = self._extract_llm_filters(question)
        if supplemental is None:
            return None
        supplemental = self._resolve_filter_vendor_names(supplemental)

        # The deterministic pass defines both scope and answer shape.  The LLM
        # may fill fields that were genuinely absent, but must never replace a
        # known vendor/location/cuisine or turn list/count/rank into another
        # query kind.
        filters = replace(
            query_shape,
            vendor_names=(
                list(query_shape.vendor_names)
                if query_shape.vendor_names is not None
                else None
            ),
            vendor_ids=(
                list(query_shape.vendor_ids)
                if query_shape.vendor_ids is not None
                else None
            ),
        )
        filters = _merge_structured_filters(filters, supplemental)
        filters.query_kind = query_shape.query_kind
        filters.top_n = query_shape.top_n
        filters.sort = query_shape.sort
        filters = self._resolve_filter_vendor_names(filters)
        if not _has_scope_constraint(filters):
            logger.info(
                "Ignoring unbounded LLM retry filters to avoid an all-vendor SQL query"
            )
            return None
        if filters == query_shape:
            logger.info("Ignoring LLM retry because it added no safe constraints")
            return None
        return filters

    def _resolve_filter_vendor_names(
        self,
        filters: StructuredFilter,
    ) -> StructuredFilter:
        """Resolve LLM vendor names and correct vendor-as-cuisine mistakes."""
        vendors = self._vendor_rows()
        if not vendors:
            return filters

        vendor_ids = list(filters.vendor_ids or [])
        unresolved: list[str] = []
        if filters.vendor_names:
            matches, unresolved = resolve_vendor_names(filters.vendor_names, vendors)
            vendor_ids.extend(vendor_id for vendor_id, _ in matches)

        # LLMs may still put a known brand in cuisine. Correct this only when
        # the value resolves unambiguously to a known vendor, preserving real
        # cuisine values such as Korean or Japanese.
        if filters.cuisine:
            cuisine_matches, cuisine_unresolved = resolve_vendor_names(
                [filters.cuisine],
                vendors,
            )
            if cuisine_matches and not cuisine_unresolved:
                vendor_ids.extend(vendor_id for vendor_id, _ in cuisine_matches)
                filters.cuisine = None

        filters.vendor_ids = list(dict.fromkeys(vendor_ids)) or None
        filters.vendor_names = unresolved or None
        return filters

    def _match_vendor_names(self, question: str) -> list[tuple[int, str]]:
        return match_vendor_mentions(question, self._vendor_rows())

    def _vendor_rows(self) -> list[tuple[int, str]]:
        if self._vendor_rows_cache is not None:
            return self._vendor_rows_cache
        if self._session is None:
            self._vendor_rows_cache = []
            return self._vendor_rows_cache
        self._vendor_rows_cache = [
            (vendor_id, vendor_name)
            for vendor_id, vendor_name in self._session.execute(
                select(Vendor.id, Vendor.name)
            ).all()
            if vendor_name
        ]
        return self._vendor_rows_cache

    def _should_force_vendor_sql(
        self,
        question: str,
        matches: list[tuple[int, str]],
    ) -> bool:
        return bool(
            matches
            and self._sql_store is not None
            and (
                _VENDOR_SQL_LOOKUP_RE.search(question)
                or _VENDOR_SCHEDULE_LOOKUP_RE.search(question)
            )
            and not _VENDOR_EVIDENCE_RE.search(question)
        )

    def _prepare_vendor_clarification(
        self,
        filters: StructuredFilter,
        match: IntentMatch | None,
        *,
        search_type: str = "SQL",
    ) -> ChatGeneration:
        unresolved = filters.vendor_names or []
        suggestions = suggest_vendor_names(unresolved, self._vendor_rows(), limit=3)
        if suggestions:
            choices = ", ".join(suggestions)
            answer = (
                f"Do you mean {choices}? Please clarify which vendor you want "
                "me to look up."
            )
        else:
            requested = ", ".join(unresolved)
            if requested:
                answer = (
                    f'I could not identify "{requested}". Do you mean a specific '
                    "NTU food vendor? Please clarify the vendor name."
                )
            else:
                answer = (
                    "Do you mean a specific NTU food vendor? Please clarify the "
                    "vendor name, cuisine, or location."
                )
        return ChatGeneration(
            prompt="",
            sources=[],
            search_type=search_type,
            intent=match.intent_key if match else None,
            direct_answer=answer,
        )

    def _prepare_no_matching_vendors(
        self,
        match: IntentMatch,
        *,
        search_type: str,
    ) -> ChatGeneration:
        return ChatGeneration(
            prompt="",
            sources=[],
            search_type=search_type,
            intent=match.intent_key,
            direct_answer=(
                "I couldn't find any NTU food vendors matching those filters. "
                "Please try another vendor, cuisine, or location."
            ),
        )

    def _clarify_failed_vendor_lookup(
        self,
        question: str,
        filters: StructuredFilter,
        match: IntentMatch,
        *,
        search_type: str = "SQL",
    ) -> ChatGeneration | None:
        if filters.vendor_names:
            return self._prepare_vendor_clarification(
                filters,
                match,
                search_type=search_type,
            )

        vendors = self._vendor_rows()

        # If a location-style question contains a likely misspelled vendor that
        # the LLM placed in cuisine, offer only high-confidence name suggestions.
        if filters.cuisine and _VENDOR_SQL_LOOKUP_RE.search(question):
            suggestions = suggest_vendor_names(
                [filters.cuisine],
                vendors,
                limit=3,
            )
            if suggestions:
                return self._prepare_vendor_clarification(
                    StructuredFilter(vendor_names=[filters.cuisine]),
                    match,
                    search_type=search_type,
                )
        if _has_scope_constraint(filters):
            return None
        if _VENDOR_SQL_LOOKUP_RE.search(question):
            return self._prepare_vendor_clarification(
                StructuredFilter(),
                match,
                search_type=search_type,
            )
        return None

    def _build_vector_filters(self, question: str) -> dict:
        filters: dict[str, object] = {}
        normalized_question = question.casefold()
        if "reddit" in normalized_question:
            filters["source_type"] = "reddit"
        elif "google review" in normalized_question:
            filters["source_type"] = "google_review"

        mentioned_vendor_ids = [
            vendor_id for vendor_id, _ in self._match_vendor_names(question)
        ]
        if mentioned_vendor_ids:
            filters["vendor_ids"] = mentioned_vendor_ids
        return filters

    def _search_direct_reddit(
        self,
        question: str,
        filters: dict,
    ) -> list[KnowledgeResult]:
        if self._session is None or filters.get("source_type") != "reddit":
            return []
        vendor_ids = filters.get("vendor_ids")
        if not vendor_ids:
            return []

        comments = list(
            self._session.scalars(
                select(RedditComment).where(
                    RedditComment.vendor_id.in_(vendor_ids)
                )
            ).all()
        )
        query_tokens = {
            token
            for token in re.findall(r"[a-z0-9]+", question.casefold())
            if len(token) > 1 and token not in _DIRECT_REDDIT_STOP_WORDS
        }

        def relevance(comment: RedditComment) -> tuple[int, float]:
            content = comment.comment_text.casefold()
            score = sum(token in content for token in query_tokens)
            return score, comment.created_at.timestamp()

        comments.sort(key=relevance, reverse=True)
        return [
            KnowledgeResult(
                source_type="reddit",
                source_id=comment.reddit_comment_id,
                vendor_id=comment.vendor_id,
                content=comment.comment_text,
                metadata={"permalink": comment.permalink},
            )
            for comment in comments[: self._top_k]
        ]

    def _generate(self, prompt: str) -> str:
        if self._generate_fn is not None:
            return self._generate_fn(prompt)
        if self._client is None:
            if settings.gemini_api_key is None:
                raise RuntimeError(
                    "GEMINI_API_KEY is not configured; cannot generate answers"
                )
            self._client = create_chat_client()
        response = self._client.models.generate_content(
            model=self._model,
            contents=prompt,
        )
        return response.text

    def _generate_stream(self, prompt: str) -> Iterator[str]:
        if self._generate_stream_fn is not None:
            yield from self._generate_stream_fn(prompt)
            return
        if self._generate_fn is not None:
            # Test/local injected generators may only expose the legacy callback.
            yield self._generate_fn(prompt)
            return
        if self._client is None:
            if settings.gemini_api_key is None:
                raise RuntimeError(
                    "GEMINI_API_KEY is not configured; cannot generate answers"
                )
            self._client = create_chat_client()

        # The SDK cannot replay a stream that stalls after the headers arrive,
        # so retries are handled here, one attempt at a time. The SDK retry is
        # disabled for these requests to keep a single retry authority.
        attempts = settings.chat_retry_attempts
        timeout_seconds = settings.chat_request_timeout_ms / 1000
        for attempt in range(1, attempts + 1):
            started = time.monotonic()
            emitted = False
            try:
                for chunk in self._client.models.generate_content_stream(
                    model=self._model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        http_options=types.HttpOptions(
                            retry_options=types.HttpRetryOptions(attempts=1),
                        ),
                    ),
                ):
                    if chunk.text:
                        emitted = True
                        yield chunk.text
            except Exception as error:
                delay = _stream_retry_delay(
                    error,
                    attempt=attempt,
                    attempts=attempts,
                    emitted=emitted,
                    elapsed=time.monotonic() - started,
                    timeout_seconds=timeout_seconds,
                )
                if delay is None:
                    raise
                logger.info(
                    "Chat stream attempt %d/%d failed (%s); retrying in %.2fs",
                    attempt,
                    attempts,
                    type(error).__name__,
                    delay,
                )
                if delay:
                    time.sleep(delay)
            else:
                return

    @staticmethod
    def _to_source(
        result: KnowledgeResult,
        vendor_names: dict[int, str],
        reddit_permalinks: dict[str, str | None],
        google_maps_urls: dict[str, str | None],
    ) -> ChatSource:
        content = result.content
        excerpt = content[:EXCERPT_CHARS] + "…" if len(content) > EXCERPT_CHARS else content
        return ChatSource(
            source_type=result.source_type,
            source_id=result.source_id,
            vendor_id=result.vendor_id,
            vendor_name=(
                vendor_names.get(result.vendor_id)
                if result.vendor_id is not None
                else None
            ),
            excerpt=excerpt,
            permalink=(
                reddit_permalinks.get(result.source_id)
                if result.source_type == "reddit" and result.source_id is not None
                else None
            ),
            maps_url=(
                google_maps_urls.get(result.source_id)
                if result.source_type == "google_review" and result.source_id is not None
                else None
            ),
        )

    def _resolve_reddit_permalinks(
        self,
        results: list[KnowledgeResult],
    ) -> dict[str, str | None]:
        if self._session is None:
            return {}

        source_ids = {
            result.source_id
            for result in results
            if result.source_type == "reddit" and result.source_id is not None
        }
        if not source_ids:
            return {}

        rows = self._session.execute(
            select(
                RedditComment.reddit_comment_id,
                RedditComment.permalink,
            ).where(RedditComment.reddit_comment_id.in_(source_ids))
        ).all()
        return {source_id: permalink for source_id, permalink in rows}


    def _resolve_google_review_maps_urls(
        self,
        results: list[KnowledgeResult],
    ) -> dict[str, str | None]:
        if self._session is None:
            return {}

        source_ids = {
            result.source_id
            for result in results
            if result.source_type == "google_review"
            and result.source_id is not None
        }

        if not source_ids:
            return {}

        rows = self._session.execute(
            select(
                GoogleReview.external_review_id,
                GoogleReview.maps_url,
            ).where(
                GoogleReview.external_review_id.in_(source_ids)
            )
        ).all()

        return {
            source_id: maps_url
            for source_id, maps_url in rows
        }


    @staticmethod
    def _to_sql_source(result: SqlResult) -> ChatSource:
        if result.count is not None:
            return ChatSource(
                source_type="count",
                count=result.count,
            )
        return ChatSource(
            source_type="vendor",
            source_id=str(result.vendor_id) if result.vendor_id is not None else None,
            vendor_id=result.vendor_id,
            vendor_name=result.vendor_name,
            location=result.location,
            unit_code=result.unit_code,
            category=result.category,
            price_range=result.price_range,
            opening_hours=result.opening_hours,
            rating=result.average_rating or result.average_google_rating,
        )


def _merge_structured_filters(
    primary: StructuredFilter,
    supplemental: StructuredFilter,
) -> StructuredFilter:
    """Merge LLM-discovered names without weakening deterministic filters."""

    for field in (
        "halal",
        "vegetarian",
        "cuisine",
        "location",
        "budget",
        "open_hours",
        "exclude_cuisine",
        "exclude_location",
        "exclude_budget",
        "exclude_open_hours",
    ):
        if (
            hasattr(primary, field)
            and hasattr(supplemental, field)
            and getattr(primary, field) is None
        ):
            setattr(primary, field, getattr(supplemental, field))

    # Treat names and IDs as one logical constraint.  Once deterministic
    # matching identifies any vendor, a hallucinated LLM vendor cannot be
    # appended or substituted during retry.
    if not primary.vendor_names and not primary.vendor_ids:
        primary.vendor_names = (
            list(dict.fromkeys(supplemental.vendor_names or [])) or None
        )
        primary.vendor_ids = (
            list(dict.fromkeys(supplemental.vendor_ids or [])) or None
        )
    return primary


def _sql_results_are_empty(results: list[SqlResult]) -> bool:
    """Treat a structured count of zero as a zero-result SQL lookup too."""

    return not results or (
        len(results) == 1
        and results[0].count is not None
        and results[0].count == 0
    )


def _has_scope_constraint(filters: StructuredFilter) -> bool:
    """Return whether filters narrow retrieval to a vendor subset.

    ``sort`` and ``top_n`` shape an answer but do not prevent an accidental
    all-vendor query, so they deliberately do not count here.
    """

    return any(
        getattr(filters, name, None) is not None
        for name in (
            "halal",
            "vegetarian",
            "cuisine",
            "vendor_names",
            "vendor_ids",
            "location",
            "budget",
            "open_hours",
            "exclude_cuisine",
            "exclude_location",
            "exclude_budget",
            "exclude_open_hours",
        )
    )


def _describe_filters(filters: StructuredFilter) -> str:
    """Render a ``StructuredFilter`` for log output."""
    fields = []
    for name in (
        "halal",
        "vegetarian",
        "cuisine",
        "vendor_names",
        "vendor_ids",
        "location",
        "budget",
        "open_hours",
        "exclude_cuisine",
        "exclude_location",
        "exclude_budget",
        "exclude_open_hours",
        "sort",
        "top_n",
    ):
        value = getattr(filters, name, None)
        if value is not None:
            fields.append(f"{name}={value}")
    fields.append(f"query_kind={filters.query_kind}")
    return "; ".join(fields) if fields else "none"
