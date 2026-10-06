import logging
import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import RedditComment, Vendor
from app.schemas.chat import ChatHistoryMessage, ChatResponse, ChatSource, trim_chat_history
from app.services.embedding import Embedder
from app.services.intent_router import IntentMatch, IntentRouter
from app.services.retrieval import KnowledgeResult, KnowledgeStore
from app.services.sql_search import SqlResult, SqlStore
from app.services.structured_filters import (
    StructuredFilter,
    extract_structured_filters,
    extract_structured_filters_llm,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ChatGeneration:
    """Everything needed to generate and attribute one chat response."""

    prompt: str
    sources: list[ChatSource]
    search_type: str
    intent: str | None


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

_PARENTHETICAL_RE = re.compile(r"\([^)]*\)")

def _is_simple_conversation(question: str) -> bool:
    normalized = re.sub(r"[^\w\s']", "", question.casefold())
    return " ".join(normalized.split()) in _SIMPLE_CONVERSATION

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

    def answer(
        self,
        question: str,
        *,
        history: list[ChatHistoryMessage] | None = None,
    ) -> ChatResponse:
        generation = self._prepare_answer(question, history=history)
        return ChatResponse(
            answer=self._generate(generation.prompt),
            sources=generation.sources,
            search_type=generation.search_type,
            intent=generation.intent,
        )

    def stream_answer(
        self,
        question: str,
        *,
        history: list[ChatHistoryMessage] | None = None,
    ) -> Iterator[tuple[str, str | list[ChatSource] | None]]:
        """Yield generated text deltas followed by the response sources."""
        generation = self._prepare_answer(question, history=history)
        for text in self._generate_stream(generation.prompt):
            if text:
                yield "delta", text
        yield "sources", generation.sources

    def _prepare_answer(
        self,
        question: str,
        *,
        history: list[ChatHistoryMessage] | None = None,
    ) -> ChatGeneration:
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
        if _is_simple_conversation(question):
            return ChatGeneration(
                prompt=build_prompt(question, EMPTY_CONTEXT, history=history),
                sources=[],
                search_type="Conversational",
                intent=None,
            )
        routing_question = self._resolve_routing_question(question, history)
        if self._router is None:
            logger.info("No intent router configured; using Vector path")
            return self._prepare_vector(
                question,
                match=None,
                history=history,
                retrieval_question=routing_question,
                query_vector=None,
            )

        match = self._router.classify(routing_question)
        logger.info("Executing chatbot answer via search_type=%s", match.search_type)
        if match.search_type == "SQL":
            return self._prepare_sql(question, match, history, routing_question)
        if match.search_type == "SQL + Vector":
            return self._prepare_hybrid(
                question,
                match,
                history,
                routing_question,
                query_vector=match.query_vector,
            )
        return self._prepare_vector(
            question,
            match,
            history=history,
            retrieval_question=routing_question,
            query_vector=match.query_vector,
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

    def _prepare_vector(
        self,
        question: str,
        match: IntentMatch | None,
        history: list[ChatHistoryMessage],
        retrieval_question: str,
        query_vector: list[float] | None,
    ) -> ChatGeneration:
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
        return ChatGeneration(
            prompt=prompt,
            sources=[
                self._to_source(result, vendor_names, reddit_permalinks)
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
    ) -> ChatGeneration:
        filters = self._resolve_filters(retrieval_question)
        logger.info("SQL path filters: %s", _describe_filters(filters))
        results = self._sql_store.search(filters)
        logger.info("SQL path returned %d vendor result(s)", len(results))
        if not results and filters.query_kind == "list":
            logger.info(
                "SQL list path returned no vendors; falling back to Vector search"
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
    ) -> ChatGeneration:
        filters = self._resolve_filters(retrieval_question)
        logger.info("Hybrid path filters: %s", _describe_filters(filters))
        vendor_ids = self._sql_store.resolve_vendor_ids(filters)
        logger.info("Hybrid path resolved %d vendor_id(s): %s", len(vendor_ids), vendor_ids)
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
        prompt = build_prompt(
            question,
            context,
            template=match.prompt_template,
            history=history,
        )
        reddit_permalinks = self._resolve_reddit_permalinks(results)
        return ChatGeneration(
            prompt=prompt,
            sources=[
                self._to_source(result, vendor_names, reddit_permalinks)
                for result in results
            ],
            search_type="SQL + Vector",
            intent=match.intent_key,
        )

    def _resolve_filters(self, question: str) -> StructuredFilter:
        filters = extract_structured_filters(question)
        matches = self._match_vendor_names(question)
        if matches:
            filters.vendor_ids = [vendor_id for vendor_id, _ in matches]
            if filters.location and any(
                filters.location.casefold() in name for _, name in matches
            ):
                filters.location = None
        if (
            filters.query_kind == "list"
            and not filters.has_constraints
            and self._filter_extractor_llm is not None
        ):
            filters = extract_structured_filters_llm(
                question,
                self._filter_extractor_llm,
            )
        return filters

    def _match_vendor_names(self, question: str) -> list[tuple[int, str]]:
        """Return ``(vendor_id, normalized_name)`` for vendors named in a question.

        Vendor names are normalized by dropping parenthetical suffixes (e.g.
        ``"Quad Cafe (SBS)"`` -> ``"quad cafe"``) so user phrasing like
        ``"quad cafe"`` matches even when the stored name differs.
        """
        if self._session is None:
            return []
        normalized = " ".join(re.sub(r"[^\w\s]", " ", question.casefold()).split())
        if not normalized:
            return []
        
        question_words = set(normalized.split())
        rows = self._session.execute(select(Vendor.id, Vendor.name)).all()
        matches: list[tuple[int, str]] = []
        
        for vendor_id, vendor_name in rows:
            name = " ".join(
                _PARENTHETICAL_RE.sub(" ", (vendor_name or "").casefold()).split()
            )
            if not name:
                continue
            
            # Check either: full name is in question, OR any vendor word (>=3 chars) is in question
            vendor_words = [w for w in name.split() if len(w) >= 3]
            if name in normalized or any(w in question_words for w in vendor_words):
                matches.append((vendor_id, name))
                
        return matches

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
            from google import genai

            self._client = genai.Client(
                api_key=settings.gemini_api_key.get_secret_value()
            )
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
            from google import genai

            self._client = genai.Client(
                api_key=settings.gemini_api_key.get_secret_value()
            )
        for chunk in self._client.models.generate_content_stream(
            model=self._model,
            contents=prompt,
        ):
            if chunk.text:
                yield chunk.text

    @staticmethod
    def _to_source(
        result: KnowledgeResult,
        vendor_names: dict[int, str],
        reddit_permalinks: dict[str, str | None],
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


def _describe_filters(filters: StructuredFilter) -> str:
    """Render a ``StructuredFilter`` for log output."""
    fields = []
    for name in (
        "halal",
        "vegetarian",
        "cuisine",
        "location",
        "budget",
        "open_hours",
        "sort",
        "top_n",
    ):
        value = getattr(filters, name)
        if value is not None:
            fields.append(f"{name}={value}")
    fields.append(f"query_kind={filters.query_kind}")
    return "; ".join(fields) if fields else "none"
