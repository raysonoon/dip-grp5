import logging
import re
from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import RedditComment, Vendor
from app.schemas.chat import ChatResponse, ChatSource
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

DEFAULT_SYSTEM_PROMPT = (
    "You are Foodie, a helpful assistant for the NTU Foodie Hub, powered by "
    "Google's Gemini model. For greetings, conversational small talk, and "
    "questions about your identity or capabilities, answer normally without "
    "requiring supporting context. For questions about NTU campus food, vendors, "
    "menus, opening hours, or reviews, use only the information in the context "
    "below. If that context does not contain the requested campus-food facts, say "
    "that you do not have enough information rather than inventing an answer. "
    "When you use information from the context, reference the relevant source.\n\n"
    "Context:\n{context}\n\n"
    "Question: {user_question}"
)

EMPTY_CONTEXT = "(no context retrieved)"
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


def build_prompt(
    question: str,
    context: str,
    template: str | None = None,
) -> str:
    """Fill ``{user_question}`` / ``{context}`` placeholders in a template.

    Falls back to ``DEFAULT_SYSTEM_PROMPT`` when no template is provided.
    """
    prompt = template if template else DEFAULT_SYSTEM_PROMPT
    return prompt.format(user_question=question, context=context)


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
        if result.category:
            attributes.append(f"category={result.category}")
        if result.price_range:
            attributes.append(f"price={result.price_range}")
        if result.opening_hours:
            attributes.append(f"hours={result.opening_hours}")
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
        router: IntentRouter | None = None,
        sql_store: SqlStore | None = None,
        filter_extractor_llm: Callable[[str], StructuredFilter] | None = None,
        session: Session | None = None,
    ) -> None:
        self._embedder = embedder
        self._store = store
        self._model = model
        self._top_k = top_k
        self._generate_fn = generate
        self._router = router
        self._sql_store = sql_store
        self._filter_extractor_llm = filter_extractor_llm
        self._session = session
        self._client = None

    def answer(self, question: str) -> ChatResponse:
        if self._router is None:
            logger.info("No intent router configured; using Vector path")
            return self._answer_vector(question, match=None)

        match = self._router.classify(question)
        logger.info("Executing chatbot answer via search_type=%s", match.search_type)
        if match.search_type == "SQL":
            return self._answer_sql(question, match)
        if match.search_type == "SQL + Vector":
            return self._answer_hybrid(question, match)
        return self._answer_vector(question, match)

    def _answer_vector(
        self,
        question: str,
        match: IntentMatch | None,
    ) -> ChatResponse:
        vector_filters = self._build_vector_filters(question)
        results = self._search_direct_reddit(question, vector_filters)
        if not results:
            query_vector = self._embedder.embed([question])[0]
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
        )
        answer = self._generate(prompt)
        reddit_permalinks = self._resolve_reddit_permalinks(results)
        return ChatResponse(
            answer=answer,
            sources=[
                self._to_source(result, vendor_names, reddit_permalinks)
                for result in results
            ],
            search_type="Vector",
            intent=match.intent_key if match else None,
        )

    def _answer_sql(
        self,
        question: str,
        match: IntentMatch,
    ) -> ChatResponse:
        filters = self._resolve_filters(question)
        logger.info("SQL path filters: %s", _describe_filters(filters))
        results = self._sql_store.search(filters)
        logger.info("SQL path returned %d vendor result(s)", len(results))
        if not results and filters.query_kind == "list":
            logger.info(
                "SQL list path returned no vendors; falling back to Vector search"
            )
            return self._answer_vector(question, match=None)
        context = format_sql_context(results)
        prompt = build_prompt(
            question,
            context,
            template=match.prompt_template,
        )
        answer = self._generate(prompt)
        return ChatResponse(
            answer=answer,
            sources=[self._to_sql_source(result) for result in results],
            search_type="SQL",
            intent=match.intent_key,
        )

    def _answer_hybrid(
        self,
        question: str,
        match: IntentMatch,
    ) -> ChatResponse:
        filters = self._resolve_filters(question)
        logger.info("Hybrid path filters: %s", _describe_filters(filters))
        vendor_ids = self._sql_store.resolve_vendor_ids(filters)
        logger.info("Hybrid path resolved %d vendor_id(s): %s", len(vendor_ids), vendor_ids)
        query_vector = self._embedder.embed([question])[0]
        results = self._store.search(
            query_vector,
            limit=self._top_k,
            filters={
                **self._build_vector_filters(question),
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
        )
        answer = self._generate(prompt)
        reddit_permalinks = self._resolve_reddit_permalinks(results)
        return ChatResponse(
            answer=answer,
            sources=[
                self._to_source(result, vendor_names, reddit_permalinks)
                for result in results
            ],
            search_type="SQL + Vector",
            intent=match.intent_key,
        )

    def _resolve_filters(self, question: str) -> StructuredFilter:
        filters = extract_structured_filters(question)
        if not filters.has_constraints and self._filter_extractor_llm is not None:
            filters = extract_structured_filters_llm(
                question,
                self._filter_extractor_llm,
            )
        return filters

    def _build_vector_filters(self, question: str) -> dict:
        filters: dict[str, object] = {}
        normalized_question = question.casefold()
        if "reddit" in normalized_question:
            filters["source_type"] = "reddit"
        elif "google review" in normalized_question:
            filters["source_type"] = "google_review"

        if self._session is None:
            return filters

        vendors = self._session.execute(
            select(Vendor.id, Vendor.name)
        ).all()
        mentioned_vendor_ids = [
            vendor_id
            for vendor_id, vendor_name in vendors
            if vendor_name.casefold() in normalized_question
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
