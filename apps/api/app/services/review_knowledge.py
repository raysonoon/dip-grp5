from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Review
from app.models.knowledge import KnowledgeChunk
from app.services.embedding import Embedder


INTERNAL_REVIEW_SOURCE = "internal_review"


class KnowledgeSyncError(RuntimeError):
    """Raised when review text cannot be embedded for knowledge sync."""


class InternalReviewKnowledgeSync:
    """Keep one retrievable knowledge chunk in sync with an internal review."""

    def __init__(self, session: Session, embedder: Embedder) -> None:
        self._session = session
        self._embedder = embedder

    def sync(self, review: Review) -> None:
        if review.id is None:
            raise ValueError("review must be flushed before knowledge sync")

        existing = self._find(review.id)
        content = (review.comment or "").strip()
        if not content:
            if existing is not None:
                self._session.delete(existing)
            return

        embedding = None
        if existing is None or existing.content != content:
            try:
                embedding = self._embedder.embed([content])[0]
            except Exception as error:
                raise KnowledgeSyncError(
                    "Could not embed the internal review"
                ) from error

        metadata = {"rating": review.rating_half_steps / 2}
        if existing is None:
            self._session.add(
                KnowledgeChunk(
                    source_type=INTERNAL_REVIEW_SOURCE,
                    source_id=str(review.id),
                    vendor_id=review.vendor_id,
                    content=content,
                    embedding=embedding,
                    metadata_json=metadata,
                )
            )
            return

        existing.vendor_id = review.vendor_id
        existing.content = content
        existing.metadata_json = metadata
        if embedding is not None:
            existing.embedding = embedding

    def delete(self, review_id: int) -> None:
        existing = self._find(review_id)
        if existing is not None:
            self._session.delete(existing)

    def _find(self, review_id: int) -> KnowledgeChunk | None:
        return self._session.scalar(
            select(KnowledgeChunk).where(
                KnowledgeChunk.source_type == INTERNAL_REVIEW_SOURCE,
                KnowledgeChunk.source_id == str(review_id),
            )
        )
