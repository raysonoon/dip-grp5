import json
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import RedditComment, Vendor
from app.services.vendor_matching import (
    VENDOR_ALIASES as VENDOR_ALIASES,
    match_vendor_mentions,
    normalize_vendor_text,
)


REDDIT_DATA_PATH = (
    Path(__file__).resolve().parents[4]
    / "data"
    / "reddit"
    / "ntu_food_reddit.json"
)


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(
        value.replace("Z", "+00:00")
    )


def _normalize(value: str) -> str:
    """Backward-compatible wrapper around the shared normalizer."""

    return normalize_vendor_text(value)


def _find_mentioned_vendors(
    text: str,
    vendors: list[Vendor],
) -> list[Vendor]:
    """Return ORM vendors using the shared tuple-based matching rules."""

    matches = match_vendor_mentions(
        text,
        [(vendor.id, vendor.name) for vendor in vendors],
        aliases=VENDOR_ALIASES,
    )
    vendors_by_id = {vendor.id: vendor for vendor in vendors}
    return [vendors_by_id[vendor_id] for vendor_id, _ in matches]


def seed_reddit_comments(
    session: Session,
) -> tuple[int, int, int]:
    created_count = 0
    skipped_count = 0
    ignored_count = 0

    with REDDIT_DATA_PATH.open(
        encoding="utf-8-sig",
    ) as file:
        records = json.load(file)

    posts = {
        record["id"]: record
        for record in records
        if (
            record.get("type") == "post"
            and record.get("subreddit") == "NTU"
        )
    }

    vendors = list(
        session.scalars(
            select(Vendor)
        ).all()
    )

    existing_ids = set(
        session.scalars(
            select(RedditComment.reddit_comment_id)
        ).all()
    )

    for record in records:
        if record.get("type") != "comment":
            continue

        comment_id = record.get("id")
        post_id = record.get("postId")
        body = (record.get("body") or "").strip()

        if post_id not in posts:
            ignored_count += 1
            continue

        if (
            not comment_id
            or body in {
                "",
                "[deleted]",
                "[removed]",
            }
        ):
            ignored_count += 1
            continue

        if comment_id in existing_ids:
            skipped_count += 1
            continue

        post = posts[post_id]

        matched_vendors = _find_mentioned_vendors(
            body,
            vendors,
        )

        mentioned_vendors = [
            vendor.name
            for vendor in matched_vendors
        ]

        # Only hard-link when exactly one vendor
        # is confidently identified.
        vendor_id = (
            matched_vendors[0].id
            if len(matched_vendors) == 1
            else None
        )

        comment = RedditComment(
            reddit_comment_id=comment_id,
            vendor_id=vendor_id,
            author=record.get("author"),
            subreddit=post["subreddit"],
            thread_id=post_id,
            thread_title=(
                record.get("postTitle")
                or post["title"]
            ),
            comment_text=body,
            created_at=_parse_datetime(
                record["createdAt"]
            ),
            mentioned_vendors=(
                mentioned_vendors
                if mentioned_vendors
                else None
            ),
            permalink=record.get("permalink"),
        )

        session.add(comment)
        existing_ids.add(comment_id)
        created_count += 1

    session.commit()

    return (
        created_count,
        skipped_count,
        ignored_count,
    )
