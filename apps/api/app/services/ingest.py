from collections.abc import Iterator
from dataclasses import dataclass, field
from difflib import SequenceMatcher
import re

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


def _clean_review_text(text: str | None) -> str:
    """Normalise review text before adding it to a vendor embedding document."""

    if not text:
        return ""

    cleaned = " ".join(text.split())

    if len(cleaned) > VENDOR_REVIEW_CHAR_LIMIT:
        cleaned = cleaned[:VENDOR_REVIEW_CHAR_LIMIT].rstrip()

    return cleaned


def _is_obvious_noise(text: str) -> bool:
    """Return whether cleaned review text is clearly not useful content."""

    if not text or not any(character.isalnum() for character in text):
        return True

    if re.fullmatch(r"(?:https?://|www\.)\S+", text, re.IGNORECASE):
        return True

    compact = re.sub(r"\s+", "", text.casefold())
    if compact and len(set(compact)) == 1:
        return True

    return False


@dataclass
class VendorReviewSnippet:
    text: str
    rating: float | None
    source: str
    sort_time: float
    sort_id: str


def _dedupe_exact_review_snippets(
    snippets: list[VendorReviewSnippet],
) -> list[VendorReviewSnippet]:
    """Remove exact duplicates, retaining the most recent occurrence."""

    deduped: list[VendorReviewSnippet] = []
    seen: set[str] = set()

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
        if normalized in seen:
            continue

        seen.add(normalized)
        deduped.append(snippet)

    return deduped


def _dedupe_near_review_snippets(
    snippets: list[VendorReviewSnippet],
) -> list[VendorReviewSnippet]:
    """Remove near-duplicate review text after exact deduplication."""

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


def _dedupe_review_snippets(
    snippets: list[VendorReviewSnippet],
) -> list[VendorReviewSnippet]:
    """Remove exact duplicates before more expensive near-duplicate checks."""

    return _dedupe_near_review_snippets(
        _dedupe_exact_review_snippets(snippets)
    )


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


def iter_vendor_embedding_content(
    session: Session,
) -> Iterator[tuple[int, str]]:
    """Yield one searchable semantic document for each vendor."""

    for vendor in session.scalars(
        select(Vendor).order_by(Vendor.id.asc())
    ).all():
        print(f"Building vendor embedding content for vendor {vendor.id}")
        review_snippets: list[VendorReviewSnippet] = []

        for review in session.scalars(
            select(Review).where(Review.vendor_id == vendor.id)
        ).all():
            text = _clean_review_text(review.comment)

            if (
                len(text) < VENDOR_REVIEW_MIN_CHARS
                or _is_obvious_noise(text)
            ):
                continue

            review_snippets.append(
                VendorReviewSnippet(
                    text=text,
                    rating=review.rating_half_steps / 2,
                    source="Internal",
                    sort_time=review.created_at.timestamp(),
                    sort_id=str(review.id),
                )
            )

        google_review_count = 0
        for review in session.scalars(
            select(GoogleReview).where(GoogleReview.vendor_id == vendor.id)
        ).all():
            google_review_count += 1
            text = _clean_review_text(review.comment)

            if (
                len(text) < VENDOR_REVIEW_MIN_CHARS
                or _is_obvious_noise(text)
            ):
                continue

            review_snippets.append(
                VendorReviewSnippet(
                    text=text,
                    rating=(
                        float(review.rating)
                        if review.rating is not None
                        else None
                    ),
                    source="Google",
                    sort_time=(
                        review.published_at.timestamp()
                        if review.published_at is not None
                        else 0.0
                    ),
                    sort_id=review.external_review_id,
                )
            )

        for comment in session.scalars(
            select(RedditComment).where(RedditComment.vendor_id == vendor.id)
        ).all():
            text = _clean_review_text(comment.comment_text)

            if (
                len(text) < VENDOR_REVIEW_MIN_CHARS
                or _is_obvious_noise(text)
            ):
                continue

            review_snippets.append(
                VendorReviewSnippet(
                    text=text,
                    rating=None,
                    source="Reddit",
                    sort_time=comment.created_at.timestamp(),
                    sort_id=comment.reddit_comment_id,
                )
            )

        parts: list[str] = [
            f"Name: {vendor.name}",
        ]

        if vendor.category:
            parts.append(f"Category: {vendor.category}")

        if vendor.cuisine:
            parts.append(f"Cuisine: {vendor.cuisine}")

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
            ratings.append(
                f"Google {float(vendor.average_google_rating):.1f}/5"
                f"({google_review_count} reviews)"
            )

        if ratings:
            parts.append(f"Ratings: {', '.join(ratings)}")

        selected_reviews = _select_review_snippets(
            review_snippets
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

        yield vendor.id, "\n".join(parts)


def build_vendor_embedding_content(session: Session) -> dict[int, str]:
    """Build one searchable semantic document for each vendor."""

    return dict(iter_vendor_embedding_content(session))


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
    Each vendor is embedded and committed independently so completed work is
    preserved if the process is interrupted.

    Returns ``(embedded, already_indexed)``.
    """

    existing_rows = {
        row.vendor_id: row
        for row in session.scalars(select(VendorEmbedding)).all()
    }
    existing_contents = {
        vendor_id: row.content
        for vendor_id, row in existing_rows.items()
    }
    print(f"Found {len(existing_rows)} existing vendor embedding rows")

    print(
        "Starting streaming vendor reindex"
        + (f", limit={limit}" if limit is not None else "")
        + (", force=True" if force else "")
    )

    embedded = 0
    already_indexed = 0
    selected_for_embedding = 0

    for vendor_number, (vendor_id, content) in enumerate(
        iter_vendor_embedding_content(session),
        start=1,
    ):
        existing = existing_rows.get(vendor_id)
        needs_embedding = (
            force
            or existing is None
            or existing_contents[vendor_id] != content
        )

        if not needs_embedding:
            already_indexed += 1
            print(f"Vendor {vendor_id} already indexed ({vendor_number})")
            continue

        if limit is not None and selected_for_embedding >= limit:
            print(
                "Vendor embedding limit reached after "
                f"{selected_for_embedding} vendor(s)"
            )
            break

        print(
            f"Embedding vendor {vendor_id} ({vendor_number}): "
            f"{len(content)} characters"
        )

        vectors = embedder.embed([content])
        if len(vectors) != 1:
            raise RuntimeError(
                "vendor embedding service returned an unexpected number "
                f"of vectors: expected 1, got {len(vectors)}"
            )

        vector = vectors[0]

        if existing is not None:
            existing.content = content
            existing.embedding = vector
        else:
            existing = VendorEmbedding(
                vendor_id=vendor_id,
                content=content,
                embedding=vector,
            )
            session.add(existing)
            existing_rows[vendor_id] = existing

        session.commit()
        existing_contents[vendor_id] = content
        embedded += 1
        selected_for_embedding += 1
        print(f"Committed vendor {vendor_id}; embedded={embedded}")

    print(
        f"Vendor reindex complete: embedded={embedded}, "
        f"already_indexed={already_indexed}"
        + (f", limit={limit}" if limit is not None else "")
    )
    return embedded, already_indexed
