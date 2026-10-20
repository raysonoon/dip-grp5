from collections import defaultdict
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import GoogleReview, RedditComment, Review, Vendor
from app.models.knowledge import KnowledgeChunk
from app.models.vendor_embedding import VendorEmbedding
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

def _reddit_comment_documents(session: Session) -> list[KnowledgeDocument]:
    documents: list[KnowledgeDocument] = []

    comments = session.scalars(
        select(RedditComment)
    ).all()

    for comment in comments:
        content = (comment.comment_text or "").strip()

        if not content:
            continue

        documents.append(
            KnowledgeDocument(
                source_type="reddit",
                source_id=comment.reddit_comment_id,
                vendor_id=comment.vendor_id,
                content=content,
                metadata={
                    "author": comment.author,
                    "subreddit": comment.subreddit,
                    "thread_id": comment.thread_id,
                    "thread_title": comment.thread_title,
                    "created_at": comment.created_at.isoformat(),
                    "mentioned_vendors": comment.mentioned_vendors or [],
                    "permalink": comment.permalink,
                },
            )
        )

    return documents


def build_chunks(session: Session) -> list[KnowledgeDocument]:
    """Collect internal, Google, and Reddit chunks to embed."""
    return (
        _review_documents(session)
        + _google_review_documents(session)
        + _reddit_comment_documents(session)
    )


def reindex(
    session: Session,
    embedder: Embedder,
    *,
    force: bool = False,
    limit: int | None = None,
    source_type: str | None = None,
    batch_size: int = settings.embedding_batch_size,
) -> tuple[int, int]:
    """Index internal, Google, and Reddit chunks into ``knowledge_chunks``.

    Chunks are keyed by ``(source_type, source_id)``. By default already-indexed
    chunks are skipped so re-runs embed ~0 documents and consume ~0 requests;
    pass ``force=True`` to re-embed everything. Rows are committed per batch so
    a quota/429 failure preserves the progress already made.

    Returns ``(embedded, already_indexed)``.
    """
    documents = build_chunks(session)

    if source_type is not None:
        documents = [
            document
            for document in documents
            if document.source_type == source_type
    ]

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


VENDOR_DOCUMENT_CHAR_BUDGET = 6000
VENDOR_REVIEW_CHAR_LIMIT = 240
VENDOR_REVIEW_MIN_CHARS = 20
VENDOR_REVIEW_MAX_LINES = 30
VENDOR_EMBED_BATCH_CHAR_BUDGET = 6000


def _clean_review_text(text: str | None) -> str:
    """Normalise review text before adding it to a vendor embedding document."""

    if not text:
        return ""

    cleaned = " ".join(text.split())

    if len(cleaned) > VENDOR_REVIEW_CHAR_LIMIT:
        cleaned = cleaned[:VENDOR_REVIEW_CHAR_LIMIT].rstrip()

    return cleaned


@dataclass
class VendorReviewSnippet:
    text: str
    rating: float | None
    source: str
    sort_time: float
    sort_id: str


def _dedupe_review_snippets(
    snippets: list[VendorReviewSnippet],
) -> list[VendorReviewSnippet]:
    """Remove exact and near-duplicate review text."""

    deduped: list[VendorReviewSnippet] = []

    for snippet in sorted(
        snippets,
        key=lambda item: (
            item.sort_time,
            item.source,
            item.sort_id,
        ),
        reverse=True,
    ):
        normalized = snippet.text.casefold()

        is_duplicate = any(
            normalized == existing.text.casefold()
            or SequenceMatcher(
                None,
                normalized,
                existing.text.casefold(),
            ).ratio() >= 0.9
            for existing in deduped
        )

        if not is_duplicate:
            deduped.append(snippet)

    return deduped


def _select_review_snippets(
    snippets: list[VendorReviewSnippet],
) -> list[VendorReviewSnippet]:
    """Select balanced review highlights across rating buckets."""

    deduped = _dedupe_review_snippets(snippets)

    buckets: dict[int, list[VendorReviewSnippet]] = {
        5: [],
        4: [],
        3: [],
        2: [],
        1: [],
    }
    unrated: list[VendorReviewSnippet] = []

    for snippet in deduped:
        if snippet.rating is None:
            unrated.append(snippet)
            continue

        bucket = max(
            1,
            min(5, int(snippet.rating + 0.5)),
        )

        buckets[bucket].append(snippet)

    for bucket in buckets.values():
        bucket.sort(
            key=lambda item: (
                item.sort_time,
                item.source,
                item.sort_id,
            ),
            reverse=True,
        )

    unrated.sort(
        key=lambda item: (
            item.sort_time,
            item.source,
            item.sort_id,
        ),
        reverse=True,
    )

    selected: list[VendorReviewSnippet] = []

    while len(selected) < VENDOR_REVIEW_MAX_LINES:
        added = False

        for rating in (5, 4, 3, 2, 1):
            if buckets[rating]:
                selected.append(buckets[rating].pop(0))
                added = True

                if len(selected) >= VENDOR_REVIEW_MAX_LINES:
                    break

        if len(selected) >= VENDOR_REVIEW_MAX_LINES:
            break

        if unrated:
            selected.append(unrated.pop(0))
            added = True

        if not added:
            break

    return selected


def build_vendor_embedding_content(session: Session) -> dict[int, str]:
    """Build one searchable semantic document for each vendor."""

    review_snippets: dict[int, list[VendorReviewSnippet]] = defaultdict(list)

    google_review_counts: dict[int, int] = defaultdict(int)

    for review in session.scalars(select(Review)).all():
        text = _clean_review_text(review.comment)

        if len(text) < VENDOR_REVIEW_MIN_CHARS:
            continue

        review_snippets[review.vendor_id].append(
            VendorReviewSnippet(
                text=text,
                rating=review.rating_half_steps / 2,
                source="Internal",
                sort_time=review.created_at.timestamp(),
                sort_id=str(review.id),
            )
        )

    for review in session.scalars(select(GoogleReview)).all():
        google_review_counts[review.vendor_id] += 1
        text = _clean_review_text(review.comment)

        if len(text) < VENDOR_REVIEW_MIN_CHARS:
            continue

        review_snippets[review.vendor_id].append(
            VendorReviewSnippet(
                text=text,
                rating=float(review.rating) if review.rating is not None else None,
                source="Google",
                sort_time=(
                    review.published_at.timestamp()
                    if review.published_at is not None
                    else 0.0
                ),
                sort_id=review.external_review_id,
            )
        )

    for comment in session.scalars(select(RedditComment)).all():
        if comment.vendor_id is None:
            continue

        text = _clean_review_text(comment.comment_text)

        if len(text) < VENDOR_REVIEW_MIN_CHARS:
            continue

        review_snippets[comment.vendor_id].append(
            VendorReviewSnippet(
                text=text,
                rating=None,
                source="Reddit",
                sort_time=comment.created_at.timestamp(),
                sort_id=comment.reddit_comment_id,
            )
        )

    documents: dict[int, str] = {}

    for vendor in session.scalars(
        select(Vendor).order_by(Vendor.id.asc())
    ).all():
        parts: list[str] = [
            f"Name: {vendor.name}",
        ]

        if vendor.category:
            parts.append(f"Category: {vendor.category}")

        if vendor.location:
            parts.append(f"Location: {vendor.location}")

        if vendor.price_range:
            parts.append(f"Price: {vendor.price_range}")

        if vendor.dishes:
            dishes = ", ".join(
                dict.fromkeys(
                    dish.strip()
                    for dish in vendor.dishes.split(",")
                    if dish.strip()
                )
            )
            if dishes:
                parts.append(f"Dishes: {dishes}")

        dietary: list[str] = []

        if vendor.halal is True:
            dietary.append("halal")

        if vendor.vegetarian is True:
            dietary.append("vegetarian")

        if dietary:
            parts.append(f"Dietary: {', '.join(dietary)}")

        ratings: list[str] = []

        if vendor.average_rating is not None:
            ratings.append(
                f"internal {float(vendor.average_rating):.1f}/5"
            )

        if vendor.average_google_rating is not None:
            google_review_count = google_review_counts.get(vendor.id, 0)

            ratings.append(
                f"Google {float(vendor.average_google_rating):.1f}/5"
                f"({google_review_count} reviews)"
            )

        if ratings:
            parts.append(f"Ratings: {', '.join(ratings)}")

        selected_reviews = _select_review_snippets(
            review_snippets.get(vendor.id, [])
        )

        if selected_reviews:
            parts.append("")
            parts.append("Review highlights:")
            parts.append("")

            for snippet in selected_reviews:
                if snippet.rating is not None:
                    review_line = (
                        f"{snippet.text} "
                        f"({snippet.rating:g}/5 | {snippet.source})"
                    )
                else:
                    review_line = (
                        f"{snippet.text} ({snippet.source})"
                    )

                candidate = "\n".join(parts + [review_line])

                if len(candidate) > VENDOR_DOCUMENT_CHAR_BUDGET:
                    break

                parts.append(review_line)

        documents[vendor.id] = "\n".join(parts)

    return documents


def _vendor_embedding_batches(
    items: list[tuple[int, str]],
    *,
    batch_size: int,
) -> list[list[tuple[int, str]]]:
    """Group vendor documents without exceeding the request character budget."""

    batches: list[list[tuple[int, str]]] = []
    current_batch: list[tuple[int, str]] = []
    current_chars = 0

    for item in items:
        vendor_id, content = item
        content_chars = len(content)

        would_exceed_chars = (
            current_batch
            and current_chars + content_chars
            > VENDOR_EMBED_BATCH_CHAR_BUDGET
        )

        would_exceed_count = (
            current_batch
            and len(current_batch) >= batch_size
        )

        if would_exceed_chars or would_exceed_count:
            batches.append(current_batch)
            current_batch = []
            current_chars = 0

        current_batch.append((vendor_id, content))
        current_chars += content_chars

    if current_batch:
        batches.append(current_batch)

    return batches


def reindex_vendor_embeddings(
    session: Session,
    embedder: Embedder,
    *,
    force: bool = False,
    limit: int | None = None,
    batch_size: int = settings.embedding_batch_size,
) -> tuple[int, int]:
    """Build or refresh semantic embeddings for vendors.

    Existing embeddings are skipped when their source content has not changed.
    Passing ``force=True`` rebuilds all selected vendor embeddings.

    Returns ``(embedded, already_indexed)``.
    """

    documents = build_vendor_embedding_content(session)

    items = sorted(
        documents.items(),
        key=lambda item: item[0],
    )

    existing_rows = {
        row.vendor_id: row
        for row in session.scalars(select(VendorEmbedding)).all()
    }

    if force:
        to_embed = items
        already_indexed = 0
    else:
        to_embed = [
            (vendor_id, content)
            for vendor_id, content in items
            if vendor_id not in existing_rows
            or existing_rows[vendor_id].content != content
        ]
        already_indexed = len(items) - len(to_embed)

    if limit is not None:
        to_embed = to_embed[:limit]

    embedded = 0

    for batch in _vendor_embedding_batches(
        to_embed,
        batch_size=batch_size,
    ):

        vectors = embedder.embed(
            [content for _, content in batch]
        )

        for (vendor_id, content), vector in zip(batch, vectors):
            existing = existing_rows.get(vendor_id)

            if existing is not None:
                existing.content = content
                existing.embedding = vector
            else:
                row = VendorEmbedding(
                    vendor_id=vendor_id,
                    content=content,
                    embedding=vector,
                )
                session.add(row)
                existing_rows[vendor_id] = row

        session.commit()
        embedded += len(batch)

    return embedded, already_indexed