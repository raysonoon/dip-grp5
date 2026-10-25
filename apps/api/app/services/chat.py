import json
import logging
import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass, replace

from google.genai import types
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import GoogleReview, RedditComment, Vendor
from app.schemas.chat import ChatHistoryMessage, ChatResponse, ChatSource, trim_chat_history
from app.services.chat_client import create_chat_client
from app.services.embedding import Embedder
from app.services.intent_router import IntentMatch, IntentRouter
from app.services.retrieval import KnowledgeResult, KnowledgeStore
from app.services.sql_search import SqlResult, SqlStore
from app.services.query_resolution import ResolvedQuery, QueryGroundingError, ground_query, resolved_filters
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

logger = logging.getLogger(__name__)

FOODIE_VOICE = (
    "You are Foodie, NTUmmy's friendly AI food buddy. Help someone decide "
    "what to eat, with the relaxed, lively tone of a short text to a friend. "
    "Match their language, use contractions, and keep the reply to one to "
    "three short sentences, usually under 45 words. A little Singlish or one "
    "emoji is fine when natural; don't force either. Format every list of "
    "options as short bulleted or numbered points, not a comma-separated "
    "paragraph. Avoid self-introductions, canned laughter, or customer-service wording. "
    "Stay kind; don't tease or belittle the user. "
    "For meal suggestions, prefer one or two matching campus vendors when "
    "the supplied evidence supports them, then mention the food to try. "
    "Otherwise offer suitable general dish ideas without inventing a stall. "
    "Start with useful suggestions, not a paraphrase of the "
    "request or 'you could explore other options'. Respect every stated "
    "dislike and exclusion: don't suggest rejected foods or bring up rejected "
    "vendors just to explain why they don't fit. Don't end every reply with "
    "a question. If needed, ask one useful follow-up such as location. "
    "For general cravings, you can suggest dish types from ordinary food "
    "knowledge. These are ideas, not a claim that a particular campus stall "
    "serves them. If retrieved context only covers excluded foods, leave "
    "that context out of the reply and offer suitable general food ideas. "
    "For specific vendors, menus, prices, hours, reviews, and dietary "
    "suitability, use only retrieved evidence and keep its numbered citations. "
    "Don't invent campus availability or put a citation on an unsupported "
    "suggestion. Be honest when specific information is missing. "
    "A current-session food picker event is a random draw you may recall, "
    "not a saved preference or evidence of a vendor's menu. Use it when "
    "relevant. For the latest draw, use latest_food_pick from the current "
    "request; it supersedes older draw results in conversation history. "
    "Do not repeat an earlier assistant answer instead of reading the latest "
    "event. A new explicit food request takes precedence over the draw. "
    "If no picker event is supplied, say you don't have a draw recorded in "
    "this session; don't guess a result or claim the user never rolled. "
    "The food picker is a scrolling list, not a wheel. Don't add unrelated "
    "food suggestions to a question that only asks about session memory. "
    "Do not claim personal eating experiences or to be human. If asked who "
    "you are, answer honestly that you are an AI."
)

PICKER_RETRY_MESSAGE = "I couldn't check a matching stall just now. Give it another go in a moment?"


@dataclass(frozen=True)
class ChatGeneration:
    """Everything needed to generate and attribute one chat response."""

    prompt: str
    sources: list[ChatSource]
    search_type: str
    intent: str | None
    direct_answer: str | None = None


DEFAULT_SYSTEM_PROMPT = (
    "You are Foodie, NTUmmy's friendly food buddy for the NTU Foodie Hub, powered by "
    "Google's Gemini model. For greetings, conversational small talk, and "
    "questions about your identity or capabilities, answer normally without "
    "requiring supporting context. Keep replies concise and conversational, "
    "with occasional natural Singlish. Format all lists as short bulleted or "
    "numbered points. When someone is unsure what to eat, suggest trying the "
    "food picker. General dish ideas for a craving may use "
    "ordinary food knowledge, without claiming that a campus vendor serves "
    "them or attaching unsupported citations. Respect the user's exclusions. "
    "For specific questions about NTU campus food, vendors, "
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

def _picker_food_terms(food: str) -> tuple[str, ...]:
    phrase = re.sub(r"[^\w]+", " ", food.casefold()).strip()
    terms = [phrase]
    if phrase.endswith("s") and not phrase.endswith("ss"):
        terms.append(phrase[:-1])
    aliases = {
        "roti prata": ("prata",),
        "poke bowls": ("poke",),
        "fish chips": ("fish and chips",),
        "bibimbap": ("bibim",),
        "biryani": ("briyani",),
        "bbq": ("barbecue", "barbeque"),
    }
    terms.extend(aliases.get(phrase, ()))
    return tuple(dict.fromkeys(term for term in terms if term))


def _matches_picker_food(value: str | None, terms: tuple[str, ...]) -> bool:
    normalized = re.sub(r"[^\w]+", " ", (value or "").casefold())
    return any(re.search(rf"(?<!\w){re.escape(term)}(?!\w)", normalized) for term in terms)

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
    allowed_tokens = _GENERIC_FOOD_TOKENS | _GENERIC_RECOMMENDATION_TOKENS
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


def format_sql_context(results: list[SqlResult], *, start_index: int = 1) -> str:
    """Render structured SQL rows into a numbered context block."""
    if not results:
        return EMPTY_CONTEXT

    lines = []
    for index, result in enumerate(results, start=start_index):
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


class ChatService:
    """RAG chat service that routes questions across SQL, Vector, and hybrid.

    HTTP requests use a validated semantic query plan before retrieval. The
    older router/rewriter injection remains available to standalone callers.
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
        rewrite_llm: Callable[..., str] | None = None,
        query_resolver: Callable[..., ResolvedQuery | None] | None = None,
        semantic_routing: bool = False,
        session: Session | None = None,
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
        self._query_resolver = query_resolver
        self._semantic_routing = semantic_routing or query_resolver is not None
        self._session = session
        self._client = client
        self._vendor_rows_cache: list[tuple[int, str]] | None = None

    def _prepare_request(
        self, question: str, history: list[ChatHistoryMessage], food_pick: str | None, recommend_pick: bool,
    ) -> tuple[ChatGeneration, str | None, bool]:
        self._vendor_rows_cache = None
        if recommend_pick and food_pick:
            return self._prepare_food_recommendation(food_pick, history, question=question or None), food_pick, True
        if not self._semantic_routing:
            # Backwards-compatible injected services; HTTP requests always use semantic routing.
            return self._prepare_answer(question, history=history, food_pick=food_pick), food_pick, False
        try:
            query = self._query_resolver(question, history, food_pick=food_pick, vendors=self._vendor_rows()) if self._query_resolver else None
            if not isinstance(query, ResolvedQuery):
                raise QueryGroundingError("No valid structured query")
            query = ground_query(query, question=question, history=history, food_pick=food_pick, vendors=self._vendor_rows())
        except Exception:
            logger.warning("Semantic query could not be validated; asking for clarification")
            return self._semantic_clarification(question), None, False
        return self._prepare_resolved_query(query, question, history, food_pick)

    @staticmethod
    def _semantic_clarification(question: str, *, missing_pick: bool = False) -> ChatGeneration:
        chinese = bool(re.search(r"[\u4e00-\u9fff]", question))
        if missing_pick:
            answer = "这个聊天里还没有抽签结果，先试试 food picker 吧。" if chinese else "I don't have a food pick recorded in this chat yet. Try the food picker first!"
        else:
            answer = "你指的是想吃的食物，还是某一家店？可以补充一下吗？" if chinese else "Do you mean a food you want to eat or a particular vendor? Could you clarify which one?"
        return ChatGeneration(prompt="", sources=[], search_type="Conversational", intent=None, direct_answer=answer)

    def _prepare_resolved_query(
        self, query: ResolvedQuery, question: str, history: list[ChatHistoryMessage], food_pick: str | None,
    ) -> tuple[ChatGeneration, str | None, bool]:
        logger.info("Verified query target=%s reference=%s", query.target, query.reference)
        if query.target == "clarify":
            return self._semantic_clarification(question), None, False
        if query.reference == "picker" and food_pick is None:
            return self._semantic_clarification(question, missing_pick=True), None, False
        if query.target == "picker_memory":
            answer = f"你最新抽到的是 {food_pick}！" if query.language == "Chinese" else f"Your latest pick was {food_pick}!"
            return ChatGeneration(prompt="", sources=[], search_type="Conversational", intent=None, direct_answer=answer), None, False
        filters = resolved_filters(query, question)
        excluded_ids = {vendor_id for name in query.constraints.excluded_vendor_names
                        for vendor_id, _ in self._match_vendor_names(name)}
        if excluded_ids:
            filters.vendor_ids = [vendor_id for vendor_id, _ in self._vendor_rows() if vendor_id not in excluded_ids]
            if not filters.vendor_ids:
                return self._prepare_no_matching_vendors(IntentMatch(search_type="SQL"), search_type="SQL"), None, False
        if query.target == "general":
            generation = ChatGeneration(prompt=build_prompt(question, EMPTY_CONTEXT, history=history), sources=[], search_type="Conversational", intent=None)
        elif query.target == "food" and query.food_type:
            generation = self._prepare_food_recommendation(query.food_type, history, question=question, constraints=filters,
                                                          review_source=query.review_source)
            if filters.query_kind == "count":
                count = len({source.vendor_id for source in generation.sources if source.vendor_id is not None})
                answer = f"找到 {count} 家有记录支持 {query.food_type} 的店。" if query.language == "Chinese" else f"I found {count} places with recorded evidence for {query.food_type}."
                generation = ChatGeneration(prompt="", sources=[ChatSource(source_type="count", count=count)], search_type="SQL", intent=None, direct_answer=answer)
        else:
            if self._sql_store is None:
                return self._semantic_clarification(question), None, False
            if query.target == "vendor":
                filters.vendor_names = query.vendor_names
                # Intersect requested businesses with exclusions; never broaden an empty set.
                requested = self._resolve_filter_vendor_names(replace(filters, vendor_ids=None))
                if excluded_ids and requested.vendor_ids:
                    requested.vendor_ids = [vendor_id for vendor_id in requested.vendor_ids if vendor_id not in excluded_ids]
                    if not requested.vendor_ids:
                        return self._prepare_no_matching_vendors(IntentMatch(search_type="SQL"), search_type="SQL"), None, False
                filters = requested
            match = IntentMatch(search_type="SQL + Vector" if query.evidence == "reviews" else "SQL")
            if query.evidence == "reviews":
                generation = self._prepare_hybrid(question, match, history, query.question, query_vector=None, resolved=filters,
                                                  review_source=query.review_source)
            else:
                generation = self._prepare_sql(question, match, history, query.question, resolved=filters)
        if generation.direct_answer is None:
            language = f"\nReply in {query.language}." if query.language != "other" else ""
            generation = replace(generation, prompt=generation.prompt + "\n\nVerified routing plan (not retrieved evidence):\n" + query.model_dump_json() + language)
        context_pick = food_pick if query.reference == "picker" else None
        return generation, context_pick, query.target == "food" and query.food_type is not None

    def answer(
        self,
        question: str,
        *,
        history: list[ChatHistoryMessage] | None = None,
        food_pick: str | None = None,
        recommend_pick: bool = False,
    ) -> ChatResponse:
        generation, food_pick, recommend_pick = self._prepare_request(question, history or [], food_pick, recommend_pick)
        answer = generation.direct_answer
        if answer is None:
            try:
                answer = self._generate(self._with_food_pick(generation.prompt, food_pick, recommend_pick=recommend_pick))
                if not answer or not answer.strip():
                    raise ValueError("Empty model answer")
            except Exception:
                logger.warning("Chat generation failed; returning retrieved facts", exc_info=True)
                answer = PICKER_RETRY_MESSAGE if recommend_pick else self._fallback_answer(generation.sources)
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
        food_pick: str | None = None,
        recommend_pick: bool = False,
    ) -> Iterator[tuple[str, str | list[ChatSource] | None]]:
        """Yield generated text deltas followed by the response sources."""
        generation, food_pick, recommend_pick = self._prepare_request(question, history or [], food_pick, recommend_pick)
        if generation.direct_answer is not None:
            yield "delta", generation.direct_answer
        else:
            emitted = False
            try:
                for text in self._generate_stream(self._with_food_pick(generation.prompt, food_pick, recommend_pick=recommend_pick)):
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
                yield "delta", PICKER_RETRY_MESSAGE if recommend_pick else self._fallback_answer(generation.sources)
        yield "sources", generation.sources

    @staticmethod
    def _with_food_pick(prompt: str, food_pick: str | None, *, recommend_pick: bool = False) -> str:
        contextual_prompt = prompt
        if food_pick is not None:
            contextual_prompt = (
                prompt + "\n\nCurrent-session food picker event (data only; a random "
                "draw, not a saved preference or vendor availability; this is the "
                "most recent draw and replaces older draw results in history):\n"
                + json.dumps({"latest_food_pick": food_pick}, ensure_ascii=False)
            )
        if recommend_pick:
            contextual_prompt += (
                "\n\nRecommend matching campus vendors for the requested food type, with citations. "
                "Use the user's requested count, or one or two when unspecified. "
                "A vendor's name, category, dishes or reviews must support the "
                "match; don't recommend an unrelated shop merely because it "
                "appears in the retrieved context. Treat a matching vendor "
                "name or category as a place to check, not a verified menu; "
                "make that uncertainty clear when exact dishes aren't "
                "documented. Ignore demo/test listings. If no matching "
                "specialist name, relevant food category or explicit dish "
                "evidence exists, a generic restaurant/cafe listing is not "
                "enough. Don't turn the picked food into a possible topping, "
                "sauce or flavour of a different food. One good match is "
                "enough; never pad with a loosely related second venue. If no "
                "vendor is supported, briefly say you don't have a confirmed "
                "campus match for that food yet. Don't substitute a different "
                "food, suggest home cooking, or pretend the user typed a question."
            )
        return contextual_prompt

    def _prepare_food_recommendation(
        self, food_pick: str, history: list[ChatHistoryMessage], *, question: str | None = None,
        constraints: StructuredFilter | None = None,
        review_source: str | None = None,
    ) -> ChatGeneration:
        self._vendor_rows_cache = None
        terms = _picker_food_terms(food_pick)
        constraints = constraints if constraints is not None else extract_structured_filters(question or "")
        allowed_ids = (
            set(self._sql_store.resolve_vendor_ids(replace(constraints, top_n=None)))
            if self._sql_store is not None and constraints.has_constraints else None
        )
        if allowed_ids == set():
            return self._prepare_no_matching_vendors(IntentMatch(search_type="SQL"), search_type="SQL")
        generation = self._prepare_vector(
            question or "Recommend campus vendors for the latest picked food type.",
            match=None, history=history, retrieval_question=food_pick, query_vector=None,
            result_filter=lambda result: result.vendor_id is not None
            and (allowed_ids is None or result.vendor_id in allowed_ids)
            and _matches_picker_food(result.content, terms),
            vector_filters={
                **({"vendor_ids": sorted(allowed_ids)} if allowed_ids is not None else {}),
                **({"source_type": review_source} if review_source else {}),
            },
        )
        # Include directory matches even when they have no indexed reviews,
        # without exposing unrelated shops as potential recommendations.
        vendor_count = len(self._vendor_rows())
        if vendor_count and self._sql_store is not None:
            review_vendor_ids = {source.vendor_id for source in generation.sources}
            menu_ids = {
                vendor_id for term in terms
                for vendor_id in self._sql_store.resolve_vendor_ids(StructuredFilter(cuisine=term))
            }
            filters = replace(constraints, query_kind="rank", top_n=vendor_count)
            listings = [
                row for row in self._sql_store.search(filters)
                if (row.category or "").casefold() not in {"demo", "test"}
                and (row.vendor_id in menu_ids or row.vendor_id in review_vendor_ids
                     or _matches_picker_food(row.vendor_name, terms)
                     or _matches_picker_food(row.category, terms))
            ]
            if listings:
                listing_context = format_sql_context(listings, start_index=len(generation.sources) + 1)
                generation = replace(
                    generation,
                    prompt=generation.prompt + f"\n\nCampus directory matches for {food_pick} (name, category, recorded dish keywords or review evidence; exact menu availability may vary):\n" + listing_context,
                    sources=[*generation.sources, *(self._to_sql_source(row) for row in listings)],
                    search_type="SQL + Vector",
                )
        if not generation.sources:
            return replace(generation, direct_answer=f"I don't have a confirmed campus match for {food_pick} yet.")
        return generation

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
        food_pick: str | None = None,
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
            routing_question = self._resolve_routing_question(question, history, food_pick=food_pick)
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
            )
        if match.search_type == "SQL + Vector":
            return self._prepare_hybrid(
                effective_question,
                match,
                history,
                routing_question,
                query_vector=match.query_vector,
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
        *,
        food_pick: str | None = None,
    ) -> str:
        """Resolve a follow-up into a standalone question for routing/retrieval.

        Routing and retrieval must operate on the *current* question, never on a
        history-wrapped block: structural cues and embeddings from earlier turns
        could misroute or pollute the query. Only the rewriter receives history
        or a picker event to resolve references; it must preserve explicit new
        topics. Without a rewrite callable (or on failure) the
        bare question is used and the safe Vector default absorbs the follow-up.
        """
        if not _is_referential(question) or (not history and food_pick is None):
            return question
        if self._rewrite_llm is None:
            return question
        try:
            resolved = (
                self._rewrite_llm(question, history, food_pick=food_pick)
                if food_pick is not None else self._rewrite_llm(question, history)
            ).strip()
        except Exception:
            logger.warning("Question rewrite failed; using bare question", exc_info=True)
            return question
        return resolved or question

    def _prepare_vector(
        self,
        question: str,
        match: IntentMatch | None,
        history: list[ChatHistoryMessage],
        retrieval_question: str,
        query_vector: list[float] | None,
        result_filter: Callable[[KnowledgeResult], bool] | None = None,
        vector_filters: dict | None = None,
    ) -> ChatGeneration:
        if vector_filters is None:
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
        if result_filter is not None:
            results = [result for result in results if result_filter(result)]
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
        resolved: StructuredFilter | None = None,
    ) -> ChatGeneration:
        filters = resolved if resolved is not None else self._resolve_filters(retrieval_question)
        if filters.vendor_names:
            return self._prepare_vendor_clarification(filters, match)
        if (
            resolved is None
            and not _has_scope_constraint(filters)
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
        if resolved is not None and filters.query_kind != "count" and _sql_results_are_empty(results):
            return self._prepare_no_matching_vendors(match, search_type="SQL")
        should_retry = _sql_results_are_empty(results) and not (
            filters.query_kind == "count"
            and not _has_scope_constraint(filters)
        )
        if should_retry and resolved is None:
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
        resolved: StructuredFilter | None = None,
        review_source: str | None = None,
    ) -> ChatGeneration:
        filters = resolved if resolved is not None else self._resolve_filters(retrieval_question)
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
            if resolved is not None:
                return self._prepare_no_matching_vendors(match, search_type="SQL + Vector")
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

        vector_filters = self._build_vector_filters(retrieval_question) if resolved is None else {}
        vector_filters["vendor_ids"] = vendor_ids
        if review_source:
            vector_filters["source_type"] = review_source
        results = self._search_direct_reddit(retrieval_question, vector_filters)
        if not results:
            query_vector = query_vector or self._embedder.embed([retrieval_question])[0]
            results = self._store.search(query_vector, limit=self._top_k, filters=vector_filters)
        logger.info("Hybrid path retrieved %d knowledge chunk(s)", len(results))
        vendor_names = self._store.resolve_vendor_names(
            {result.vendor_id for result in results if result.vendor_id is not None}
        )
        context = format_context(results, vendor_names)
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
        return self._resolve_filter_vendor_names(filters)

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
            and _VENDOR_SQL_LOOKUP_RE.search(question)
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
            config=types.GenerateContentConfig(system_instruction=FOODIE_VOICE),
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
        for chunk in self._client.models.generate_content_stream(
            model=self._model,
            contents=prompt,
            config=types.GenerateContentConfig(system_instruction=FOODIE_VOICE),
        ):
            if chunk.text:
                yield chunk.text

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
