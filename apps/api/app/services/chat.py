import logging
from collections.abc import Callable

from app.core.config import settings
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
    ) -> None:
        self._embedder = embedder
        self._store = store
        self._model = model
        self._top_k = top_k
        self._generate_fn = generate
        self._router = router
        self._sql_store = sql_store
        self._filter_extractor_llm = filter_extractor_llm
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
        query_vector = self._embedder.embed([question])[0]
        results = self._store.search(query_vector, limit=self._top_k)
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
        return ChatResponse(
            answer=answer,
            sources=[self._to_source(result, vendor_names) for result in results],
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
            filters={"vendor_ids": vendor_ids},
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
        return ChatResponse(
            answer=answer,
            sources=[self._to_source(result, vendor_names) for result in results],
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
        )

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
