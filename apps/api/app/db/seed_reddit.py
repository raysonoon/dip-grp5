import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import RedditComment, Vendor


REDDIT_DATA_PATH = (
    Path(__file__).resolve().parents[4]
    / "data"
    / "reddit"
    / "ntu_food_reddit.json"
)


# Common names students use on Reddit that may differ from
# the official vendor name stored in our database.
VENDOR_ALIASES = {
    # Individual vendors
    "hot hideout": "A Hot Hideout",
    "pasta express": "Pasta Express",
    "soup spoon": "The Soup Spoon Union",
    "connect 71": "Connect 71 Cafe (C71)",
    "connect71": "Connect 71 Cafe (C71)",
    "connect cafe": "Connect 71 Cafe (C71)",
    "mad roasters": "Mad Roaster at SHHK",
    "mad roaster": "Mad Roaster at SHHK",
    "thai dynasty": "Thai Dynasty Express",
    "encik tan": "Encik Tan",
    "qq rice": "QQ Rice",
    "mr bean": "Mr Bean",
    "subway": "Subway",
    "popeyes": "Popeyes",
    "boost juice": "Boost Juice Bars",
    "gelare": "Geláre",
    "ananda taj": "Ananda's TAJ Restaurant",
    "anandas taj": "Ananda's TAJ Restaurant",
    "bismillah": "Bismillah Biryani",
    "paiks bibim": "Paik's Bibim",
    "blue ocean": "Blue Ocean Kopi & Toast",
    "coffee faculty": "Coffee Faculty",
    "junes breathe cafe": "June's Breathe Cafe\n@ LKC Medicine",
    "june breathe cafe": "June's Breathe Cafe\n@ LKC Medicine",
    "wok express": "Wok Express",

    # Common NTU food court names
    "koufu": "North Spine Food Court & International Food Court (Koufu)",
    "north spine food court": "North Spine Food Court & International Food Court (Koufu)",
    "nie canteen": "Food Court @ NIE",
    "nie food court": "Food Court @ NIE",
    "quad cafe": "Quad Cafe (SBS)",
    "south spine": "South Spine Food Court (Foodies' Clan)",
    "north hill canteen": "North Hill Food Court (Colour Box)",
    "north hill food court": "North Hill Food Court (Colour Box)",

    # Canteen shorthand commonly used on Reddit
    "canteen 1": "Food Court 1",
    "can 1": "Food Court 1",
    "canteen 2": "Food Court 2",
    "can 2": "Food Court 2",
    "canteen 4": "Food Court 4",
    "can 4": "Food Court 4",
    "canteen 9": "Food Court 9",
    "can 9": "Food Court 9",
    "canteen 11": "Food Court 11",
    "can 11": "Food Court 11",
    "canteen 14": "Food Court 14",
    "can 14": "Food Court 14",
    "canteen 16": "Food Court 16",
    "can 16": "Food Court 16",
    "north hill fc": "North Hill Food Court (Colour Box)",
    "hall 14": "Food Court 14",
    "hall 11": "Food Court 11",
    "tama": "Nanyang Crescent Food Court",
    "tama canteen": "Nanyang Crescent Food Court",
    "north hill": "North Hill Food Court (Colour Box)", 

    # Crespion is commonly used to refer to the Hall 4 food court
    "crespion": "Food Court 4",
}


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(
        value.replace("Z", "+00:00")
    )


def _normalize(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = value.encode("ascii", "ignore").decode()
    value = value.lower()

    value = re.sub(r"[^a-z0-9]+", " ", value)

    return " ".join(value.split())


def _vendor_aliases(vendor: Vendor) -> set[str]:
    name = _normalize(vendor.name)

    aliases = {name}

    # Allows "Hot Hideout" to match "A Hot Hideout"
    if name.startswith("a "):
        aliases.add(name[2:])

    if name.startswith("the "):
        aliases.add(name[4:])

    return {
        alias
        for alias in aliases
        if len(alias) >= 4
    }


def _find_mentioned_vendors(
    text: str,
    vendors: list[Vendor],
) -> list[Vendor]:
    normalized_text = _normalize(text)

    matched: dict[int, Vendor] = {}

    # First match against official DB vendor names.
    for vendor in vendors:
        for alias in _vendor_aliases(vendor):
            pattern = (
                r"(?<![a-z0-9])"
                + re.escape(alias)
                + r"(?![a-z0-9])"
            )

            if re.search(pattern, normalized_text):
                matched[vendor.id] = vendor
                break

    # Then try common Reddit/NTU aliases.
    vendors_by_normalized_name = {
        _normalize(vendor.name): vendor
        for vendor in vendors
    }

    for alias, official_name in VENDOR_ALIASES.items():
        pattern = (
            r"(?<![a-z0-9])"
            + re.escape(_normalize(alias))
            + r"(?![a-z0-9])"
        )

        if not re.search(pattern, normalized_text):
            continue

        target = _normalize(official_name)

        # Exact official-name lookup first.
        vendor = vendors_by_normalized_name.get(target)

        # If exact spelling differs slightly in DB,
        # try containment as a best-effort fallback.
        if vendor is None:
            for candidate in vendors:
                candidate_name = _normalize(candidate.name)

                if (
                    target in candidate_name
                    or candidate_name in target
                ):
                    vendor = candidate
                    break

        if vendor is not None:
            matched[vendor.id] = vendor

    return list(matched.values())


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