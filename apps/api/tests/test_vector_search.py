import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.vector_base import VectorBase
from app.models.knowledge import KnowledgeChunk
from app.services.embedding import Embedder
from app.services.retrieval import PgvectorKnowledgeStore

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.vector,
    pytest.mark.skipif(
        not TEST_DATABASE_URL,
        reason="TEST_DATABASE_URL is not set; skipping vector integration test",
    ),
]

DIMENSION = 768


def _vector(marker: float) -> list[float]:
    vector = [0.0] * DIMENSION
    vector[0] = 1.0
    vector[1] = marker
    return vector


class FakeEmbedder(Embedder):
    def embed(self, texts: list[str]) -> list[list[float]]:
        return [_vector(0.1) for _ in texts]


def test_pgvector_store_orders_results_by_cosine_distance() -> None:
    engine = create_engine(TEST_DATABASE_URL)
    VectorBase.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            session.execute(KnowledgeChunk.__table__.delete())
            session.add(
                KnowledgeChunk(
                    source_type="internal_review",
                    source_id="1",
                    vendor_id=1,
                    content="great chicken rice",
                    embedding=_vector(0.1),
                )
            )
            session.add(
                KnowledgeChunk(
                    source_type="google_review",
                    source_id="g1",
                    vendor_id=1,
                    content="noodles are the best",
                    embedding=_vector(0.9),
                )
            )
            session.commit()

            store = PgvectorKnowledgeStore(session)
            results = store.search(_vector(0.1), limit=2)

            assert [result.source_id for result in results] == ["1", "g1"]
            assert results[0].content == "great chicken rice"

            session.execute(KnowledgeChunk.__table__.delete())
            session.commit()
    finally:
        engine.dispose()