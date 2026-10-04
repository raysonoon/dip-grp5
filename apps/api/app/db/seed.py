import csv
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from geoalchemy2.elements import WKTElement
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password
from app.db.chatbot_question_data import CHATBOT_QUESTION_ROWS
from app.db.seed_reddit import seed_reddit_comments
from app.db.session import SessionLocal
from app.models import (
    ChatbotPrompt,
    GoogleReview,
    RedditComment,
    Review,
    User,
    Vendor,
)
from app.models.knowledge import KnowledgeChunk


DEMO_VENDORS = (
    {
        "name": "Demo Vendor 1",
        "location": "Demo Canteen",
        "category": "Demo",
        "opening_hours": "09:00 - 21:00",
    },
    {
        "name": "Demo Vendor 2",
        "location": "Demo Canteen",
        "category": "Demo",
        "opening_hours": "10:00 - 22:00",
    },
)

# Demo vendor name -> (lat, lng).
DEMO_VENDOR_COORDINATES: dict[str, tuple[float, float]] = {
    "Demo Vendor 1": (1.3483, 103.6831),
    "Demo Vendor 2": (1.3483, 103.6831),
}

NTU_VENDOR_CSV = (
    Path(__file__).resolve().parents[4]
    / "data"
    / "fnb-directory-v2.csv"
)

GOOGLE_REVIEWS_CSV = (
    Path(__file__).resolve().parents[4]
    / "data"
    / "google_reviews"
    / "ntu_detailed_reviews_final.csv"
)

GOOGLE_RATINGS_CSV = (
    Path(__file__).resolve().parents[4]
    / "data"
    / "google_reviews"
    / "ntu_food_places_final.csv"
)

KNOWLEDGE_CHUNKS_CSV = (
    Path(__file__).resolve().parents[4]
    / "data"
    / "knowledge_chunks.csv"
)

MOJIBAKE_MARKERS = (
    "\ufffd",
    "\u00c3",
    "\u00c2",
    "\u00e2",
    "\u00f0\u0178",
)


GOOGLE_VENDOR_CORE_FIELD_MAP = (
    ("name", "name"),
    ("Level / unit", "unit_code"),
    ("main_category", "category"),
    ("Opening hours", "opening_hours"),
    ("price_range", "price_range"),
)


GOOGLE_VENDOR_METADATA_FIELD_MAP = (
    ("address", "address"),
    ("website", "website_url"),
    ("phone", "phone_number"),
)


GOOGLE_VENDOR_DIETARY_FIELD_MAP = (
    ("Halal", "halal"),
    ("Vegetarian", "vegetarian"),
)

CATEGORY_NORMALIZATION = {
    "coffee": "Drinks",
    "coffee shop": "Drinks",
    "tea and coffee shop": "Drinks",
    "bubble tea": "Drinks",
    "bubble tea store": "Drinks",
    "juice": "Drinks",
    "juice shop": "Drinks",
    "canteen": "Canteen",
    "cafeteria": "Canteen",
    "food court": "Canteen",
    "fast food/takeout": "Fast food restaurant",
    "fast food restaurant": "Fast food restaurant",
    "cafe": "Cafe",
}

VENDOR_CATEGORY_OVERRIDES = {
    "V005": "Restaurant",
    "V018": "Canteen",
    "V035": "Canteen",
}


def _normalize_vendor_category(
    category: str | None,
    directory_id: str | None = None,
) -> str | None:
    if directory_id is not None:
        override = VENDOR_CATEGORY_OVERRIDES.get(directory_id)
        if override is not None:
            return override

    if category is None:
        return None

    normalized = category.strip()

    if not normalized:
        return None

    return CATEGORY_NORMALIZATION.get(
        normalized.casefold(),
        normalized,
    )


def _parse_nullable_bool(
    raw_value: str,
    *,
    column_name: str,
    directory_id: str,
) -> bool | None:
    normalized = raw_value.strip().lower()

    if normalized in {"", "null"}:
        return None

    if normalized == "true":
        return True

    if normalized == "false":
        return False

    raise ValueError(
        f"Invalid {column_name} value for vendor {directory_id}: "
        f"{raw_value!r}"
    )


def _safe_csv_text(raw_value: str) -> tuple[str | None, bool]:
    """Return normalized text and whether it was rejected as mojibake."""
    normalized = raw_value.strip()

    if not normalized:
        return None, False

    if any(marker in normalized for marker in MOJIBAKE_MARKERS):
        return None, True

    return normalized, False


def _set_if_changed(entity: object, field: str, value: object) -> bool:
    current_value = getattr(entity, field)

    if isinstance(current_value, datetime) and isinstance(value, datetime):
        normalized_current = (
            current_value.replace(tzinfo=timezone.utc)
            if current_value.tzinfo is None
            else current_value.astimezone(timezone.utc)
        )

        normalized_value = (
            value.replace(tzinfo=timezone.utc)
            if value.tzinfo is None
            else value.astimezone(timezone.utc)
        )

        if normalized_current == normalized_value:
            return False

    elif current_value == value:
        return False

    setattr(entity, field, value)
    return True


def _set_map_coordinates_if_changed(
    session: Session,
    vendor: Vendor,
    value: object,
) -> bool:
    if vendor.map_coordinates is None:
        vendor.map_coordinates = value
        return True

    if (
        session.bind is not None
        and session.bind.dialect.name == "sqlite"
    ):
        if vendor.map_coordinates == value:
            return False

        vendor.map_coordinates = value
        return True

    # PostgreSQL/PostGIS comparison.
    current_wkt = session.scalar(
        text(
            """
            SELECT ST_AsText(map_coordinates)
            FROM vendors
            WHERE id = :vendor_id
            """
        ),
        {"vendor_id": vendor.id},
    )

    if isinstance(value, WKTElement):
        new_wkt = value.data
    else:
        new_wkt = str(value)

    if current_wkt == new_wkt:
        return False

    vendor.map_coordinates = value
    return True


def _seed_user(
    session: Session,
    *,
    display_name: str,
    email_address: str,
    password: str,
    role: str,
) -> tuple[User, bool]:
    normalized_email = email_address.strip()
    canonical_email = normalized_email.lower()

    existing_user = session.scalar(
        select(User).where(
            User.email_canonical == canonical_email
        )
    )

    if existing_user is not None:
        changed = False

        if existing_user.display_name != display_name:
            existing_user.display_name = display_name
            changed = True

        if existing_user.email_address != normalized_email:
            existing_user.email_address = normalized_email
            changed = True

        if existing_user.role != role:
            existing_user.role = role
            changed = True

        if changed:
            session.commit()

        return existing_user, False

    user = User(
        display_name=display_name,
        email_address=normalized_email,
        password_hash=hash_password(password),
        role=role,
    )

    session.add(user)
    session.commit()
    session.refresh(user)

    return user, True


def seed_development_admin(session: Session) -> tuple[User, bool]:
    return _seed_user(
        session,
        display_name=settings.seed_admin_display_name,
        email_address=settings.seed_admin_email_address,
        password=settings.seed_admin_password.get_secret_value(),
        role="admin",
    )


def seed_development_user(session: Session) -> tuple[User, bool]:
    return _seed_user(
        session,
        display_name=settings.seed_test_display_name,
        email_address=settings.seed_test_email_address,
        password=settings.seed_test_password.get_secret_value(),
        role="user",
    )


def seed_demo_vendors(
    session: Session,
) -> list[tuple[Vendor, bool]]:
    results: list[tuple[Vendor, bool]] = []

    for vendor_data in DEMO_VENDORS:
        vendor = session.scalar(
            select(Vendor)
            .where(Vendor.name == vendor_data["name"])
            .limit(1)
        )

        if vendor is not None:
            results.append((vendor, False))
            continue

        vendor = Vendor(**vendor_data)
        session.add(vendor)
        session.commit()
        session.refresh(vendor)

        results.append((vendor, True))

    return results


def seed_ntu_vendors(
    session: Session,
) -> list[tuple[Vendor, bool]]:
    results: list[tuple[Vendor, bool]] = []
    seen_directory_ids: set[str] = set()

    with NTU_VENDOR_CSV.open(
        newline="",
        encoding="utf-8-sig",
    ) as file:
        reader = csv.DictReader(file)

        for row in reader:
            directory_id = row["id"].strip()
            seen_directory_ids.add(directory_id)
            vendor = session.scalar(
                select(Vendor).where(
                    Vendor.directory_id == directory_id
                )
            )

            vendor_directory_data: dict[str, object] = {}
            skip_new_vendor = False

            for source_column, target_field in (
                ("name", "name"),
                ("location", "location"),
                ("unit_number", "unit_code"),
                ("category", "category"),
                ("opening_hours", "opening_hours"),
                ("price_range", "price_range"),
                ("website", "website_url"),
                ("phone", "phone_number"),
            ):
                value, is_mojibake = _safe_csv_text(
                    row.get(source_column) or ""
                )

                if is_mojibake:
                    print(
                        "Skipping mojibake directory field: "
                        f"vendor={directory_id}, "
                        f"column={source_column}"
                    )

                    if vendor is None and target_field == "name":
                        skip_new_vendor = True

                    continue

                if target_field == "name" and value is None:
                    if vendor is None:
                        skip_new_vendor = True

                    continue

                if target_field == "category":
                    value = _normalize_vendor_category(
                        value,
                        directory_id,
                    )

                vendor_directory_data[target_field] = value

            if skip_new_vendor:
                print(
                    f"Skipping vendor {directory_id}: "
                    "safe name not available"
                )
                continue

            vendor_directory_data.update(
                halal=_parse_nullable_bool(
                    row["halal"],
                    column_name="halal",
                    directory_id=directory_id,
                ),
                vegetarian=_parse_nullable_bool(
                    row["vegetarian"],
                    column_name="vegetarian",
                    directory_id=directory_id,
                ),
            )

            if vendor is not None:
                for field, value in vendor_directory_data.items():
                    _set_if_changed(vendor, field, value)
                if (
                    vendor.location is None
                    and "unit_code" in vendor_directory_data
                ):
                    vendor.location = vendor_directory_data["unit_code"]
                session.commit()
                session.refresh(vendor)
                results.append((vendor, False))
                continue

            vendor = Vendor(
                directory_id=directory_id,
                **vendor_directory_data,
            )

            session.add(vendor)
            session.commit()
            session.refresh(vendor)

            results.append((vendor, True))

    session.commit()

    deleted_count, skipped_count = _delete_stale_ntu_vendors(
        session,
        seen_directory_ids,
    )
    if deleted_count or skipped_count:
        print(
            "Stale NTU vendors: "
            f"deleted={deleted_count}, "
            f"skipped_with_content={skipped_count}"
        )

    return results


def _delete_stale_ntu_vendors(
    session: Session,
    seen_directory_ids: set[str],
) -> tuple[int, int]:
    """Delete vendors whose directory_id is no longer in the directory CSV.

    Vendors with internal reviews or Google reviews are kept because those
    foreign keys use ON DELETE RESTRICT. Reddit comments are detached via
    ON DELETE SET NULL and vendor images are removed via ON DELETE CASCADE.
    """
    stale_vendors = session.scalars(
        select(Vendor).where(
            Vendor.directory_id.is_not(None),
            Vendor.directory_id.not_in(seen_directory_ids),
        )
    ).all()

    deleted_count = 0
    skipped_count = 0
    for vendor in stale_vendors:
        has_reviews = session.scalar(
            select(Review.id)
            .where(Review.vendor_id == vendor.id)
            .limit(1)
        ) is not None
        has_google_reviews = session.scalar(
            select(GoogleReview.id)
            .where(GoogleReview.vendor_id == vendor.id)
            .limit(1)
        ) is not None
        if has_reviews or has_google_reviews:
            print(
                f"Skipping stale vendor {vendor.directory_id}: "
                "still referenced by reviews or Google reviews"
            )
            skipped_count += 1
            continue
        session.delete(vendor)
        deleted_count += 1

    session.commit()
    return deleted_count, skipped_count


def seed_vendor_google_metadata(
    session: Session,
) -> tuple[int, int, int, int, int]:
    """Merge safe vendor fields from ntu_food_places_final.csv.

    Blank and mojibake values do not overwrite existing data.

    The return value contains matched vendors, missing vendors,
    changed fields, rejected mojibake fields, and skipped
    ambiguous dietary fields.
    """
    matched_vendor_count = 0
    missing_vendor_count = 0
    changed_field_count = 0
    skipped_mojibake_count = 0
    skipped_ambiguous_count = 0

    vendors_by_directory_id = {
        vendor.directory_id: vendor
        for vendor in session.scalars(
            select(Vendor).where(
                Vendor.directory_id.is_not(None)
            )
        ).all()
    }

    with GOOGLE_RATINGS_CSV.open(
        newline="",
        encoding="utf-8-sig",
    ) as file:
        for row in csv.DictReader(file):
            directory_id = row["ID"].strip()
            vendor = vendors_by_directory_id.get(directory_id)

            if vendor is None:
                missing_vendor_count += 1
                continue

            matched_vendor_count += 1

            # Core vendor metadata.
            for (
                source_column,
                target_field,
            ) in GOOGLE_VENDOR_CORE_FIELD_MAP:
                value, is_mojibake = _safe_csv_text(
                    row.get(source_column) or ""
                )

                if is_mojibake:
                    skipped_mojibake_count += 1
                    print(
                        "Skipping mojibake vendor field: "
                        f"vendor={directory_id}, "
                        f"column={source_column}"
                    )
                    continue

                if target_field == "category":
                    value = _normalize_vendor_category(
                        value,
                        directory_id,
                    )

                    if (
                        vendor.category == "Drinks"
                        and value == "Cafe"
                    ):
                        value = vendor.category

                if value is not None and _set_if_changed(
                    vendor,
                    target_field,
                    value,
                ):
                    changed_field_count += 1

            # Address, website and phone metadata.
            for (
                source_column,
                target_field,
            ) in GOOGLE_VENDOR_METADATA_FIELD_MAP:
                value, is_mojibake = _safe_csv_text(
                    row.get(source_column) or ""
                )

                if is_mojibake:
                    skipped_mojibake_count += 1
                    print(
                        "Skipping mojibake vendor field: "
                        f"vendor={directory_id}, "
                        f"column={source_column}"
                    )
                    continue
                if value is not None and _set_if_changed(
                    vendor,
                    target_field,
                    value,
                ):
                    changed_field_count += 1

            # Parse latitude/longitude from the CSV map_coordinates column.
            #
            # The column format is "(lat, lng)", e.g.
            # "(1.3473036, 103.6806168)". The returned WKT is:
            # POINT(103.6806168 1.3473036)
            #
            # PostGIS uses X=longitude and Y=latitude.
            raw_coordinates = row.get("map_coordinates") or ""
            coordinates = _parse_map_coordinates(raw_coordinates)

            if coordinates is not None:
                latitude, longitude = coordinates

                map_value = _make_map_coordinates(
                    session,
                    latitude,
                    longitude,
                )

                if _set_map_coordinates_if_changed(
                    session,
                    vendor,
                    map_value,
                ):
                    changed_field_count += 1

            # Dietary metadata.
            for (
                source_column,
                target_field,
            ) in GOOGLE_VENDOR_DIETARY_FIELD_MAP:
                value, is_mojibake = _safe_csv_text(
                    row.get(source_column) or ""
                )

                if is_mojibake:
                    skipped_mojibake_count += 1
                    print(
                        "Skipping mojibake vendor field: "
                        f"vendor={directory_id}, "
                        f"column={source_column}"
                    )
                    continue

                if value is None or value.casefold() in {
                    "not stated",
                    "unknown",
                    "n/a",
                }:
                    continue

                normalized_value = value.casefold()

                if normalized_value in {"yes", "true"}:
                    parsed_value = True

                elif normalized_value in {"no", "false"}:
                    parsed_value = False

                elif (
                    target_field == "halal"
                    and "halal" in normalized_value
                ):
                    parsed_value = True

                elif (
                    target_field == "vegetarian"
                    and (
                        "vegetarian" in normalized_value
                        or "meat-free" in normalized_value
                    )
                ):
                    parsed_value = True

                else:
                    skipped_ambiguous_count += 1
                    continue

                if _set_if_changed(
                    vendor,
                    target_field,
                    parsed_value,
                ):
                    changed_field_count += 1

            # Google rating.
            rating_raw = (row.get("rating") or "").strip()

            if rating_raw:
                rating_value = Decimal(rating_raw)

                normalized_rating = (
                    None
                    if rating_value == 0
                    else rating_value
                )

                if _set_if_changed(
                    vendor,
                    "average_google_rating",
                    normalized_rating,
                ):
                    changed_field_count += 1

    session.commit()

    return (
        matched_vendor_count,
        missing_vendor_count,
        changed_field_count,
        skipped_mojibake_count,
        skipped_ambiguous_count,
    )


def seed_google_reviews(
    session: Session,
) -> tuple[int, int, int]:
    created_count = 0
    skipped_count = 0
    missing_vendor_count = 0

    vendors_by_directory_id = {
        vendor.directory_id: vendor
        for vendor in session.scalars(
            select(Vendor).where(
                Vendor.directory_id.is_not(None)
            )
        ).all()
    }

    existing_reviews = {
        review.external_review_id: review
        for review in session.scalars(
            select(GoogleReview)
        ).all()
    }

    with GOOGLE_REVIEWS_CSV.open(
        newline="",
        encoding="utf-8-sig",
    ) as file:
        reader = csv.DictReader(file)

        for row in reader:
            directory_id = row["ID"].strip()
            external_review_id = row["review_id"].strip()
            maps_url = (row.get("review_link") or "").strip() or None

            existing_review = existing_reviews.get(external_review_id)

            if existing_review is not None:
                _set_if_changed(
                    existing_review,
                    "maps_url",
                    maps_url,
                )
                skipped_count += 1
                continue

            vendor = vendors_by_directory_id.get(directory_id)

            if vendor is None:
                print(
                    f"Skipping review {external_review_id}: "
                    f"vendor {directory_id} not found"
                )
                missing_vendor_count += 1
                continue

            published_at = datetime.fromisoformat(
                row["published_at_date"].strip()
            )

            if published_at.tzinfo is None:
                published_at = published_at.replace(
                    tzinfo=timezone.utc
                )

            google_review = GoogleReview(
                vendor_id=vendor.id,
                external_review_id=external_review_id,
                rating=int(row["rating"]),
                comment=(row["review_text"] or "").strip() or None,
                maps_url=maps_url,
                published_at=published_at,
            )

            session.add(google_review)
            existing_reviews[external_review_id] = google_review
            created_count += 1

    session.commit()

    return (
        created_count,
        skipped_count,
        missing_vendor_count,
    )


DEMO_REVIEWS = (
    (
        "Demo Vendor 1",
        4.0,
        "Great chicken rice, generous portion and fast service.",
    ),
    (
        "Demo Vendor 1",
        3.5,
        "Decent halal options but a bit pricey.",
    ),
    (
        "Demo Vendor 2",
        5.0,
        "Best noodles on campus, definitely worth trying.",
    ),
    (
        "Demo Vendor 2",
        2.5,
        "Food was average and the queue was long.",
    ),
)


def seed_demo_reviews(
    session: Session,
) -> tuple[int, int]:
    """Seed a few app reviews with comments so internal chunks have content."""
    test_user = session.scalar(
        select(User).where(
            User.email_canonical
            == settings.seed_test_email_address.strip().lower()
        )
    )

    if test_user is None:
        return 0, 0

    vendors = {
        vendor.name: vendor
        for vendor in session.scalars(
            select(Vendor).where(
                Vendor.name.in_(
                    [name for name, _, _ in DEMO_REVIEWS]
                )
            )
        ).all()
    }

    created_count = 0
    skipped_count = 0

    for name, rating, comment in DEMO_REVIEWS:
        vendor = vendors.get(name)

        if vendor is None:
            skipped_count += 1
            continue

        existing = session.scalar(
            select(Review).where(
                Review.user_id == test_user.id,
                Review.vendor_id == vendor.id,
                Review.comment == comment,
            )
        )

        if existing is not None:
            skipped_count += 1
            continue

        session.add(
            Review(
                user_id=test_user.id,
                vendor_id=vendor.id,
                rating_half_steps=int(rating * 2),
                comment=comment,
            )
        )

        created_count += 1

    session.commit()

    return created_count, skipped_count


def seed_chatbot_questions(
    session: Session,
) -> tuple[int, int]:
    """Insert or refresh the curated workbook questions without prompts."""
    created_count = 0
    updated_count = 0

    for (
        question_id,
        question_text,
        search_type,
        question_scope,
        source_file,
    ) in CHATBOT_QUESTION_ROWS:
        intent_key = question_id.lower()

        existing = session.scalar(
            select(ChatbotPrompt).where(
                ChatbotPrompt.intent_key == intent_key
            )
        )

        if existing is None:
            session.add(
                ChatbotPrompt(
                    intent_key=intent_key,
                    question_scope=question_scope,
                    question_text=question_text,
                    search_type=search_type,
                    source_file=source_file,
                    prompt_template=None,
                )
            )

            created_count += 1
            continue

        changed = False

        for field, value in (
            ("question_scope", question_scope),
            ("question_text", question_text),
            ("search_type", search_type),
            ("source_file", source_file),
        ):
            if getattr(existing, field) != value:
                setattr(existing, field, value)
                changed = True

        if changed:
            updated_count += 1

    session.commit()

    return created_count, updated_count


def _parse_embedding(raw_value: str) -> list[float]:
    """Parse a pgvector text form like ``[0.1,-0.2,...]`` into floats."""
    stripped = raw_value.strip()
    if not stripped.startswith("[") or not stripped.endswith("]"):
        raise ValueError(f"Invalid embedding vector: {raw_value!r}")
    inner = stripped[1:-1].strip()
    if not inner:
        return []
    return [float(token) for token in inner.split(",")]


def _parse_knowledge_chunk_metadata(raw_value: str) -> dict | None:
    """Parse a CSV metadata field into a dict, or ``None`` when blank."""
    stripped = raw_value.strip()
    if not stripped:
        return None
    return json.loads(stripped)


def _parse_nullable_str(raw_value: str) -> str | None:
    stripped = raw_value.strip()
    return stripped or None


def seed_knowledge_chunks(session: Session) -> tuple[int, int, int]:
    """Seed ``knowledge_chunks`` from an exported CSV (skip guard + by-source_id).

    Imports Google review and Reddit chunks only. ``vendor_id`` is resolved at
    import time from the already-seeded ``GoogleReview`` / ``RedditComment``
    rows so it stays correct even when local ``vendors.id`` values differ.

    Returns ``(created, skipped, unresolved_vendor)``. Skipping happens when the
    table is already populated, the CSV is absent, or a row duplicates an
    existing ``(source_type, source_id)`` key.
    """
    existing_count = session.scalar(select(KnowledgeChunk.id).limit(1))
    if existing_count is not None:
        print(
            "Knowledge chunks already populated; skipping CSV seed "
            "(run python -m app.db.reindex --force to rebuild)."
        )
        return 0, 0, 0

    if not KNOWLEDGE_CHUNKS_CSV.exists():
        print(
            "Knowledge chunks CSV not found; skipping seed. "
            f"Expected at {KNOWLEDGE_CHUNKS_CSV} (run python -m app.db.reindex "
            "or generate the CSV to enable chatbot knowledge)."
        )
        return 0, 0, 0

    google_vendor_ids = {
        review.external_review_id: review.vendor_id
        for review in session.scalars(select(GoogleReview)).all()
    }
    reddit_vendor_ids = {
        comment.reddit_comment_id: comment.vendor_id
        for comment in session.scalars(select(RedditComment)).all()
    }

    existing_keys = set(
        session.execute(
            select(KnowledgeChunk.source_type, KnowledgeChunk.source_id)
        ).all()
    )

    created_count = 0
    skipped_count = 0
    unresolved_vendor_count = 0

    with KNOWLEDGE_CHUNKS_CSV.open(newline="", encoding="utf-8-sig") as file:
        for row in csv.DictReader(file):
            source_type = row["source_type"].strip()
            source_id = _parse_nullable_str(row["source_id"])
            if (source_type, source_id) in existing_keys:
                skipped_count += 1
                continue

            if source_type == "google_review":
                vendor_id = google_vendor_ids.get(source_id)
            elif source_type == "reddit":
                vendor_id = reddit_vendor_ids.get(source_id)
            else:
                vendor_id = None

            if vendor_id is None:
                unresolved_vendor_count += 1

            session.add(
                KnowledgeChunk(
                    source_type=source_type,
                    source_id=source_id,
                    vendor_id=vendor_id,
                    content=row["content"],
                    embedding=_parse_embedding(row["embedding"]),
                    metadata_json=_parse_knowledge_chunk_metadata(
                        row["metadata"]
                    ),
                )
            )
            existing_keys.add((source_type, source_id))
            created_count += 1

    session.commit()
    return created_count, skipped_count, unresolved_vendor_count


def _parse_map_coordinates(
    value: str | None,
) -> tuple[float, float] | None:
    """Parse ``(lat, lng)`` from the CSV map_coordinates column."""
    if not value:
        return None

    stripped = value.strip()

    if not (
        stripped.startswith("(")
        and stripped.endswith(")")
    ):
        return None

    inner = stripped[1:-1].strip()
    parts = [part.strip() for part in inner.split(",")]

    if len(parts) != 2:
        return None

    try:
        latitude = float(parts[0])
        longitude = float(parts[1])
    except ValueError:
        return None

    if not -90 <= latitude <= 90:
        return None

    if not -180 <= longitude <= 180:
        return None

    return latitude, longitude


def _make_map_coordinates(
    session: Session,
    latitude: float,
    longitude: float,
) -> object:
    """
    Return a PostGIS WKTElement for PostgreSQL,
    or a plain WKT string for SQLite tests.
    """
    wkt = f"POINT({longitude} {latitude})"

    if (
        session.bind is not None
        and session.bind.dialect.name == "sqlite"
    ):
        return wkt

    return WKTElement(
        wkt,
        srid=4326,
    )


def seed_demo_vendor_coordinates(session: Session) -> int:
    """Backfill ``map_coordinates`` for demo vendors that lack them."""
    if session.get_bind().dialect.name != "postgresql":
        return 0

    updated = 0

    for name, (lat, lng) in DEMO_VENDOR_COORDINATES.items():
        vendor = session.scalar(
            select(Vendor).where(Vendor.name == name)
        )

        if vendor is None:
            continue

        map_value = _make_map_coordinates(
            session,
            lat,
            lng,
        )

        if _set_map_coordinates_if_changed(
            session,
            vendor,
            map_value,
        ):
            updated += 1

    session.commit()
    return updated


def main() -> None:
    with SessionLocal() as session:
        admin, admin_created = seed_development_admin(session)
        test_user, test_user_created = seed_development_user(session)

        vendors = seed_demo_vendors(session)
        ntu_vendors = seed_ntu_vendors(session)
        demo_coords_backfilled = seed_demo_vendor_coordinates(session)

        (
            google_metadata_matched,
            google_metadata_missing,
            google_metadata_changed_fields,
            google_metadata_mojibake_skipped,
            google_metadata_ambiguous_skipped,
        ) = seed_vendor_google_metadata(session)

        (
            google_reviews_created,
            google_reviews_skipped,
            google_reviews_missing,
        ) = seed_google_reviews(session)

        chatbot_created, chatbot_updated = seed_chatbot_questions(
            session
        )

        reviews_created, reviews_skipped = seed_demo_reviews(
            session
        )

        (
            reddit_created,
            reddit_skipped,
            reddit_ignored,
        ) = seed_reddit_comments(session)
        (
            knowledge_created,
            knowledge_skipped,
            knowledge_unresolved,
        ) = seed_knowledge_chunks(session)

    admin_action = "Created" if admin_created else "Confirmed"
    user_action = "Created" if test_user_created else "Confirmed"

    print(
        f"{admin_action} local administrator account: "
        f"{admin.display_name} <{admin.email_address}> "
        f"(id={admin.id})"
    )

    print(
        f"{user_action} local test account: "
        f"{test_user.display_name} <{test_user.email_address}> "
        f"(id={test_user.id})"
    )

    for vendor, created in vendors:
        action = "Created" if created else "Confirmed"
        print(
            f"{action} demo vendor: "
            f"{vendor.name} (id={vendor.id})"
        )

    for vendor, created in ntu_vendors:
        action = "Created" if created else "Confirmed"
        print(
            f"{action} NTU vendor: "
            f"{vendor.directory_id} - "
            f"{vendor.name} (id={vendor.id})"
        )

    print(
        "Google reviews: "
        f"created={google_reviews_created}, "
        f"skipped={google_reviews_skipped}, "
        f"missing_vendor={google_reviews_missing}"
    )

    print(
        "Vendor Google metadata: "
        f"matched={google_metadata_matched}, "
        f"missing_vendor={google_metadata_missing}, "
        f"changed_fields={google_metadata_changed_fields}, "
        f"mojibake_skipped={google_metadata_mojibake_skipped}, "
        f"ambiguous_skipped={google_metadata_ambiguous_skipped}"
    )

    print(
        "Chatbot workbook questions: "
        f"created={chatbot_created}, "
        f"updated={chatbot_updated}, "
        f"total={len(CHATBOT_QUESTION_ROWS)}"
    )

    print(
        "Demo app reviews: "
        f"created={reviews_created}, "
        f"skipped={reviews_skipped}"
    )

    print(
        "Reddit comments: "
        f"created={reddit_created}, "
        f"skipped={reddit_skipped}, "
        f"ignored={reddit_ignored}"
    )
    print(
        "Knowledge chunks: "
        f"created={knowledge_created}, skipped={knowledge_skipped}, "
        f"unresolved_vendor={knowledge_unresolved}"
    )
    print(f"Vendor map coordinates: demo_backfilled={demo_coords_backfilled}")


if __name__ == "__main__":
    main()