import math
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Vendor
from app.models.knowledge import KnowledgeChunk


@dataclass
class KnowledgeResult:
    """A single retrieved knowledge chunk."""

    source_type: str
    source_id: str | None
    vendor_id: int | None
    content: str
    metadata: dict


class KnowledgeStore(Protocol):
    """Retrieval interface over the knowledge base."""

    def search(
        self,
        query_vector: list[float],
        *,
        limit: int,
        filters: dict | None = None,
    ) -> list[KnowledgeResult]: ...

    def resolve_vendor_names(
        self,
        vendor_ids: set[int],
    ) -> dict[int, str]: ...


class PgvectorKnowledgeStore:
    """pgvector-backed store using cosine similarity over ``knowledge_chunks``."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def search(
        self,
        query_vector: list[float],
        *,
        limit: int,
        filters: dict | None = None,
    ) -> list[KnowledgeResult]:
        statement = (
            select(KnowledgeChunk)
            .order_by(KnowledgeChunk.embedding.cosine_distance(query_vector))
            .limit(limit)
        )
        chunks = self._session.scalars(statement).all()
        return [self._to_result(chunk) for chunk in chunks]

    def resolve_vendor_names(
        self,
        vendor_ids: set[int],
    ) -> dict[int, str]:
        if not vendor_ids:
            return {}
        vendors = self._session.scalars(
            select(Vendor).where(Vendor.id.in_(vendor_ids))
        ).all()
        return {vendor.id: vendor.name for vendor in vendors}

    @staticmethod
    def _to_result(chunk: KnowledgeChunk) -> KnowledgeResult:
        return KnowledgeResult(
            source_type=chunk.source_type,
            source_id=chunk.source_id,
            vendor_id=chunk.vendor_id,
            content=chunk.content,
            metadata=chunk.metadata_json or {},
        )


def cosine_distance(a: list[float], b: list[float]) -> float:
    """Return ``1 - cosine_similarity``, matching pgvector's cosine distance."""
    if not a or not b or len(a) != len(b):
        return 1.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 1.0
    return 1.0 - (dot / (norm_a * norm_b))


class FakeKnowledgeStore:
    """In-memory store for tests; ranks by cosine distance."""

    def __init__(
        self,
        items: list[tuple[list[float], KnowledgeResult]] | None = None,
        vendor_names: dict[int, str] | None = None,
    ) -> None:
        self._items = items or []
        self._vendor_names = vendor_names or {}

    def search(
        self,
        query_vector: list[float],
        *,
        limit: int,
        filters: dict | None = None,
    ) -> list[KnowledgeResult]:
        ranked = sorted(
            self._items,
            key=lambda item: cosine_distance(query_vector, item[0]),
        )
        return [result for _, result in ranked[:limit]]

    def resolve_vendor_names(
        self,
        vendor_ids: set[int],
    ) -> dict[int, str]:
        return {
            vendor_id: self._vendor_names[vendor_id]
            for vendor_id in vendor_ids
            if vendor_id in self._vendor_names
        }