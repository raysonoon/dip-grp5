from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ChatbotPrompt
from app.services.embedding import Embedder
from app.services.intent_router import IntentRouter

DIMENSION = 768


def _vector(index: int) -> list[float]:
    vector = [0.0] * DIMENSION
    vector[index % DIMENSION] = 1.0
    return vector


class FakeEmbedder(Embedder):
    """Maps identical text to the same orthogonal vector."""

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [_vector(_index(text)) for text in texts]


def _index(text: str) -> int:
    return sum(ord(char) for char in text) % DIMENSION


class ParaphraseEmbedder(Embedder):
    """Maps texts mentioning 'best food' to the same vector as the target."""

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [
            _vector(0) if "best food" in text else _vector(1)
            for text in texts
        ]


class FailingEmbedder(Embedder):
    def embed(self, texts: list[str]) -> list[list[float]]:
        raise RuntimeError("embedding quota exhausted")


def _seed_prompt(
    session: Session,
    *,
    intent_key: str,
    question_text: str,
    search_type: str,
) -> None:
    session.add(
        ChatbotPrompt(
            intent_key=intent_key,
            question_scope="Scope",
            question_text=question_text,
            search_type=search_type,
            source_file="DIP AI chatbot questions.xlsx",
        )
    )
    session.commit()


def test_tier1_exact_match_routes_to_sql(session: Session) -> None:
    _seed_prompt(
        session,
        intent_key="Q001",
        question_text="Where can I find halal food?",
        search_type="SQL",
    )
    router = IntentRouter(session)

    match = router.classify("  where can i find halal food?  ")

    assert match.search_type == "SQL"
    assert match.intent_key == "q001"
    assert match.tier == 1


def test_tier1_structural_count_forces_sql(session: Session) -> None:
    router = IntentRouter(session)
    match = router.classify("How many halal places are there?")
    assert match.search_type == "SQL"
    assert match.tier == 1
    assert match.intent_key is None


def test_tier1_structural_rank_forces_sql(session: Session) -> None:
    router = IntentRouter(session)
    match = router.classify("Show me the top 10 best stalls")
    assert match.search_type == "SQL"
    assert match.tier == 1


def test_tier2_embedding_above_threshold_routes_to_search_type(
    session: Session,
) -> None:
    _seed_prompt(
        session,
        intent_key="Q021",
        question_text="Which place has the best food?",
        search_type="Vector",
    )
    router = IntentRouter(session, embedder=ParaphraseEmbedder())

    match = router.classify("What place has the best food around?")

    assert match.search_type == "Vector"
    assert match.tier == 2
    assert match.similarity == 1.0
    assert match.intent_key == "q021"


def test_tier2_below_threshold_falls_through(session: Session) -> None:
    _seed_prompt(
        session,
        intent_key="Q001",
        question_text="Where can I find halal food?",
        search_type="SQL",
    )
    router = IntentRouter(session, embedder=FakeEmbedder(), threshold=0.99)

    match = router.classify("completely unrelated unrelated question")

    assert match.tier == 3
    assert match.search_type == "Vector"


def test_tier3_llm_classifier_used_as_fallback(session: Session) -> None:
    def classify_llm(question: str, prompts) -> str:
        return "SQL + Vector"

    router = IntentRouter(session, classify_llm=classify_llm)
    match = router.classify("something unusual")
    assert match.search_type == "SQL + Vector"
    assert match.tier == 3


def test_embedding_failure_falls_through_to_llm_classifier(
    session: Session,
) -> None:
    _seed_prompt(
        session,
        intent_key="Q001",
        question_text="Where can I find halal food?",
        search_type="SQL",
    )
    router = IntentRouter(
        session,
        embedder=FailingEmbedder(),
        classify_llm=lambda _question, _prompts: "SQL",
    )

    match = router.classify("Show me something different")

    assert match.search_type == "SQL"
    assert match.tier == 3


def test_tier3_invalid_llm_result_defaults_to_vector(session: Session) -> None:
    router = IntentRouter(
        session,
        classify_llm=lambda question, prompts: "Keyword",
    )
    match = router.classify("something unusual")
    assert match.search_type == "Vector"


def test_exact_match_wins_over_embedding(session: Session) -> None:
    _seed_prompt(
        session,
        intent_key="Q021",
        question_text="Which place has the best food?",
        search_type="Vector",
    )
    router = IntentRouter(session, embedder=FakeEmbedder())
    match = router.classify("which place has the best food?")
    assert match.tier == 1
    assert match.search_type == "Vector"
