from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import GoogleReview, Review, Vendor
from app.models.knowledge import KnowledgeChunk
from app.services.embedding import Embedder


@dataclass
class KnowledgeDocument:
    """Normalized chunk before embedding."""

    source_type: str
    source_id: str | None
    vendor_id: int | None
    content: str
    metadata: dict = field(default_factory=dict)


def _review_documents(session: Session) -> list[KnowledgeDocument]:
    documents: list[KnowledgeDocument] = []
    for review in session.scalars(select(Review)).all():
        comment = (review.comment or "").strip()
        if not comment:
            continue
        documents.append(
            KnowledgeDocument(
                source_type="internal_review",
                source_id=str(review.id),
                vendor_id=review.vendor_id,
                content=comment,
                metadata={"rating": review.rating_half_steps / 2},
            )
        )
    return documents


def _google_review_documents(session: Session) -> list[KnowledgeDocument]:
    average_ratings = {
        vendor.id: vendor.average_google_rating
        for vendor in session.scalars(select(Vendor)).all()
    }

    documents: list[KnowledgeDocument] = []
    for review in session.scalars(select(GoogleReview)).all():
        comment = (review.comment or "").strip()
        if not comment:
            continue
        metadata = {
            "rating": review.rating,
            "published_at": (
                review.published_at.isoformat()
                if review.published_at is not None
                else None
            ),
        }
        average = average_ratings.get(review.vendor_id)
        if average is not None:
            metadata["vendor_average_google_rating"] = float(average)
        documents.append(
            KnowledgeDocument(
                source_type="google_review",
                source_id=review.external_review_id,
                vendor_id=review.vendor_id,
                content=comment,
                metadata=metadata,
            )
        )
    return documents


def build_chunks(session: Session) -> list[KnowledgeDocument]:
    """Collect the internal and Google review chunks to embed."""
    return _review_documents(session) + _google_review_documents(session)


def reindex(
    session: Session,
    embedder: Embedder,
    *,
    force: bool = False,
    limit: int | None = None,
    batch_size: int = settings.embedding_batch_size,
) -> tuple[int, int]:
    """Index internal and Google review chunks into ``knowledge_chunks``.

    Chunks are keyed by ``(source_type, source_id)``. By default already-indexed
    chunks are skipped so re-runs embed ~0 documents and consume ~0 requests;
    pass ``force=True`` to re-embed everything. Rows are committed per batch so
    a quota/429 failure preserves the progress already made.

    Returns ``(embedded, already_indexed)``.
    """
    documents = build_chunks(session)
    if limit is not None:
        documents = documents[:limit]

    if force:
        to_embed = documents
    else:
        existing_keys = set(
            session.execute(
                select(KnowledgeChunk.source_type, KnowledgeChunk.source_id)
            ).all()
        )
        to_embed = [
            document
            for document in documents
            if (document.source_type, document.source_id) not in existing_keys
        ]

    already_indexed = len(documents) - len(to_embed)

    embedded = 0
    for start in range(0, len(to_embed), batch_size):
        batch = to_embed[start : start + batch_size]
        if not batch:
            continue
        vectors = embedder.embed([document.content for document in batch])
        for document, vector in zip(batch, vectors):
            existing = session.scalar(
                select(KnowledgeChunk).where(
                    KnowledgeChunk.source_type == document.source_type,
                    KnowledgeChunk.source_id == document.source_id,
                )
            )
            if existing is not None:
                existing.embedding = vector
                existing.content = document.content
                existing.vendor_id = document.vendor_id
                existing.metadata_json = document.metadata or None
            else:
                session.add(
                    KnowledgeChunk(
                        source_type=document.source_type,
                        source_id=document.source_id,
                        vendor_id=document.vendor_id,
                        content=document.content,
                        embedding=vector,
                        metadata_json=document.metadata or None,
                    )
                )
        session.commit()
        embedded += len(batch)

    return embedded, already_indexed