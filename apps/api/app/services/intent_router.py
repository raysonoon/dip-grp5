"""Multi-tier intent router for the chatbot.

The router maps a user question to a ``ChatbotPrompt`` intent and its
``search_type`` (``SQL``, ``Vector``, or ``SQL + Vector``), using three tiers:

1. **Deterministic** — exact match against ``question_text`` plus structural
   rules (counts, rankings, budgets) that force the SQL path.
2. **Embedding similarity** — cosine match against pre-embedded ``question_text``
   above a confidence threshold.
3. **LLM fallback** — an injected classifier picks the ``search_type``.
"""

import logging
from dataclasses import dataclass
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from app.models import ChatbotPrompt
from app.services.embedding import Embedder
from app.services.retrieval import cosine_distance
from app.services.structured_filters import SIMILARITY_THRESHOLD

SEARCH_TYPES = {"SQL", "Vector", "SQL + Vector"}

# Structural cues that can only be satisfied by a structured SQL lookup.
_STRUCTURAL_COUNT = ("how many", "how much")
_STRUCTURAL_RANK = ("top ", "cheapest", "most expensive", "highest rated")


@dataclass
class IntentMatch:
    """Result of routing a question to an intent."""

    search_type: str
    intent_key: str | None = None
    question_scope: str | None = None
    prompt_template: str | None = None
    tier: int = 0
    similarity: float | None = None


class IntentRouter:
    """Classify a user question into a chatbot intent and search path."""

    def __init__(
        self,
        session: Session,
        *,
        embedder: Embedder | None = None,
        classify_llm: Callable[[str, list[ChatbotPrompt]], str] | None = None,
        threshold: float = SIMILARITY_THRESHOLD,
    ) -> None:
        self._session = session
        self._embedder = embedder
        self._classify_llm = classify_llm
        self._threshold = threshold
        self._embedding_cache: list[tuple[list[float], ChatbotPrompt]] | None = (
            None
        )

    def classify(self, question: str) -> IntentMatch:
        logger.info("Classifying chatbot question: %r", question)
        prompts = self._load_prompts()

        tier1 = self._tier1(question, prompts)
        if tier1 is not None:
            self._log_match(question, tier1)
            return tier1

        try:
            tier2 = self._tier2(question, prompts)
        except Exception:
            logger.warning(
                "Embedding intent routing unavailable; falling back to LLM routing",
                exc_info=True,
            )
            tier2 = None
        if tier2 is not None:
            self._log_match(question, tier2)
            return tier2

        result = self._tier3(question, prompts)
        self._log_match(question, result)
        return result

    def _log_match(self, question: str, match: IntentMatch) -> None:
        logger.info(
            "Routed question %r -> search_type=%s intent=%s tier=%s "
            "similarity=%s",
            question,
            match.search_type,
            match.intent_key,
            match.tier,
            (
                f"{match.similarity:.3f}"
                if match.similarity is not None
                else "n/a"
            ),
        )

    def _load_prompts(self) -> list[ChatbotPrompt]:
        return list(
            self._session.scalars(
                select(ChatbotPrompt).where(
                    ChatbotPrompt.is_active.is_(True),
                    ChatbotPrompt.question_text.is_not(None),
                )
            ).all()
        )

    def _tier1(
        self,
        question: str,
        prompts: list[ChatbotPrompt],
    ) -> IntentMatch | None:
        normalized = question.strip().casefold()
        for prompt in prompts:
            candidate = (prompt.question_text or "").strip().casefold()
            if candidate and candidate == normalized:
                return self._from_prompt(prompt, tier=1)

        lowered = question.casefold()
        if any(word in lowered for word in _STRUCTURAL_COUNT):
            return IntentMatch(search_type="SQL", tier=1)
        if any(word in lowered for word in _STRUCTURAL_RANK):
            return IntentMatch(search_type="SQL", tier=1)
        return None

    def _tier2(
        self,
        question: str,
        prompts: list[ChatbotPrompt],
    ) -> IntentMatch | None:
        if self._embedder is None:
            return None
        cache = self._embedding_cache
        if cache is None:
            texts = [prompt.question_text for prompt in prompts if prompt.question_text]
            vectors = self._embedder.embed(texts) if texts else []
            cache = list(zip(vectors, prompts))
            self._embedding_cache = cache
        if not cache:
            return None

        query_vector = self._embedder.embed([question])[0]
        best = min(
            cache,
            key=lambda item: cosine_distance(query_vector, item[0]),
        )
        similarity = 1.0 - cosine_distance(query_vector, best[0])
        if similarity > self._threshold:
            match = self._from_prompt(best[1], tier=2)
            match.similarity = similarity
            return match
        return None

    def _tier3(
        self,
        question: str,
        prompts: list[ChatbotPrompt],
    ) -> IntentMatch:
        if self._classify_llm is None:
            return IntentMatch(search_type="Vector", tier=3)
        search_type = self._classify_llm(question, prompts)
        if search_type not in SEARCH_TYPES:
            search_type = "Vector"
        return IntentMatch(search_type=search_type, tier=3)

    @staticmethod
    def _from_prompt(prompt: ChatbotPrompt, *, tier: int) -> IntentMatch:
        return IntentMatch(
            search_type=prompt.search_type or "Vector",
            intent_key=prompt.intent_key,
            question_scope=prompt.question_scope,
            prompt_template=prompt.prompt_template,
            tier=tier,
        )
