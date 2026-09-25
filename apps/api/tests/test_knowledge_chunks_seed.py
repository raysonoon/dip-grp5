import os
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db import seed
from app.db.base import Base
from app.db.vector_base import VectorBase
from app.models import GoogleReview, RedditComment, Vendor
from app.models.knowledge import KnowledgeChunk

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

skip_without_test_db = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is not set; skipping vector integration test",
)

DIMENSION = 768


def _vector(marker: float) -> list[float]:
    vector = [0.0] * DIMENSION
    vector[0] = 1.0
    vector[1] = marker
    return vector


def test_parse_embedding_parses_pgvector_text() -> None:
    assert seed._parse_embedding("[0.1,-0.2,3.0]") == [0.1, -0.2, 3.0]
    assert seed._parse_embedding(" [1.0] ") == [1.0]
    assert seed._parse_embedding("[]") == []


def test_parse_embedding_rejects_malformed_text() -> None:
    with pytest.raises(ValueError):
        seed._parse_embedding("0.1,0.2")


def test_parse_knowledge_chunk_metadata() -> None:
    assert seed._parse_knowledge_chunk_metadata("") is None
    assert seed._parse_knowledge_chunk_metadata(" ") is None
    assert seed._parse_knowledge_chunk_metadata('{"rating": 5}') == {"rating": 5}


def test_parse_nullable_str() -> None:
    assert seed._parse_nullable_str("") is None
    assert seed._parse_nullable_str("  ") is None
    assert seed._parse_nullable_str("abc") == "abc"


def _write_knowledge_csv(path: Path) -> None:
    row1_embedding = "[0.1," + ",".join(["0.0"] * (DIMENSION - 1)) + "]"
    row2_embedding = "[0.9," + ",".join(["0.0"] * (DIMENSION - 1)) + "]"
    path.write_text(
        "source_type,source_id,content,embedding,metadata\n"
        f"google_review,GRID,great food,{row1_embedding},"
        '{{"rating": 5}}\n'
        f"reddit,REDDITID,nice noodles,{row2_embedding},\n",
        encoding="utf-8",
    )


@pytest.mark.vector
@skip_without_test_db
def test_seed_knowledge_chunks_imports_and_resolves_vendor_id(
    monkeypatch,
    tmp_path: Path,
) -> None:
    csv_path = tmp_path / "knowledge_chunks.csv"
    _write_knowledge_csv(csv_path)
    monkeypatch.setattr(seed, "KNOWLEDGE_CHUNKS_CSV", csv_path)

    engine = create_engine(TEST_DATABASE_URL)
    Base.metadata.create_all(engine)
    VectorBase.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            session.execute(KnowledgeChunk.__table__.delete())
            session.execute(GoogleReview.__table__.delete())
            session.execute(RedditComment.__table__.delete())
            session.execute(Vendor.__table__.delete())
            session.commit()

            vendor = Vendor(directory_id="V001", name="Test Vendor")
            session.add(vendor)
            session.commit()

            session.add(
                GoogleReview(
                    vendor_id=vendor.id,
                    external_review_id="GRID",
                    rating=5,
                    comment="Great food",
                    published_at=datetime.now(timezone.utc),
                )
            )
            session.add(
                RedditComment(
                    reddit_comment_id="REDDITID",
                    vendor_id=vendor.id,
                    subreddit="NTU",
                    thread_id="thread-1",
                    thread_title="Campus food",
                    comment_text="Nice noodles",
                    created_at=datetime.now(timezone.utc),
                )
            )
            session.commit()

            created, skipped, unresolved = seed.seed_knowledge_chunks(session)

            assert (created, skipped, unresolved) == (2, 0, 0)
            chunks = session.scalars(select(KnowledgeChunk)).all()
            by_source_id = {chunk.source_id: chunk for chunk in chunks}
            assert by_source_id["GRID"].vendor_id == vendor.id
            assert by_source_id["REDDITID"].vendor_id == vendor.id
            assert by_source_id["REDDITID"].metadata_json is None

            second_created, second_skipped, second_unresolved = (
                seed.seed_knowledge_chunks(session)
            )
            assert (second_created, second_skipped, second_unresolved) == (
                0,
                0,
                0,
            )

            session.execute(KnowledgeChunk.__table__.delete())
            session.execute(GoogleReview.__table__.delete())
            session.execute(RedditComment.__table__.delete())
            session.execute(Vendor.__table__.delete())
            session.commit()
    finally:
        engine.dispose()


@pytest.mark.vector
@skip_without_test_db
def test_seed_knowledge_chunks_skips_when_already_populated(
    monkeypatch,
    tmp_path: Path,
) -> None:
    csv_path = tmp_path / "knowledge_chunks.csv"
    _write_knowledge_csv(csv_path)
    monkeypatch.setattr(seed, "KNOWLEDGE_CHUNKS_CSV", csv_path)

    engine = create_engine(TEST_DATABASE_URL)
    VectorBase.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            session.execute(KnowledgeChunk.__table__.delete())
            session.add(
                KnowledgeChunk(
                    source_type="google_review",
                    source_id="GRID",
                    vendor_id=1,
                    content="great food",
                    embedding=_vector(0.1),
                )
            )
            session.commit()

            created, skipped, unresolved = seed.seed_knowledge_chunks(session)

            assert (created, skipped, unresolved) == (0, 0, 0)

            session.execute(KnowledgeChunk.__table__.delete())
            session.commit()
    finally:
        engine.dispose()