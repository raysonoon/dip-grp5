import csv
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password
from app.db.chatbot_question_data import CHATBOT_QUESTION_ROWS
from app.db.session import SessionLocal
from app.models import ChatbotPrompt, GoogleReview, User, Vendor


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

MOJIBAKE_MARKERS = (
    "\ufffd",
    "\u00c3",
    "\u00c2",
    "\u00e2",
    "\u00f0\u0178",
)
GOOGLE_TEXT_FIELD_MAP = (
    ("Location", "location"),
    ("place_id", "google_place_id"),
    ("name", "google_name"),
    ("price_range", "google_price_range"),
    ("address", "google_address"),
    ("main_category", "google_main_category"),
    ("website", "website_url"),
    ("phone", "phone_number"),
    ("status", "google_status"),
    ("link", "google_maps_url"),
    ("query", "google_search_query"),
)
GOOGLE_DIRECTORY_DUPLICATE_FIELDS = (
    "Name",
    "Level / unit",
    "Cuisine / type",
    "Halal",
    "Vegetarian",
    "Opening hours",
)
GOOGLE_REVIEW_TEXT_FIELD_MAP = (
    ("review_link", "review_link"),
    ("name", "reviewer_name"),
    ("reviewer_id", "reviewer_id"),
    ("reviewer_profile", "reviewer_profile_url"),
    ("review_text", "comment"),
    ("original_language", "original_language"),
    ("review_translated_text", "translated_comment"),
    ("translated_language", "translated_language"),
    ("published_at", "published_at_text"),
    ("response_from_owner_text", "owner_response_text"),
    ("response_from_owner_ago", "owner_response_age_text"),
    (
        "response_from_owner_translated_text",
        "owner_response_translated_text",
    ),
    ("avatar_link", "reviewer_avatar_url"),
    ("review_origin", "review_origin"),
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
        select(User).where(User.email_canonical == canonical_email)
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


def seed_demo_vendors(session: Session) -> list[tuple[Vendor, bool]]:
    results: list[tuple[Vendor, bool]] = []

    for vendor_data in DEMO_VENDORS:
        vendor = session.scalar(
            select(Vendor).where(Vendor.name == vendor_data["name"]).limit(1)
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


def seed_ntu_vendors(session: Session) -> list[tuple[Vendor, bool]]:
    results: list[tuple[Vendor, bool]] = []

    with NTU_VENDOR_CSV.open(newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)

        for row in reader:
            directory_id = row["id"].strip()
            vendor_directory_data = {
                "name": row["name"].strip(),
                "level_unit": row["location"].strip() or None,
                "category": row["category"].strip() or None,
                "opening_hours": row["opening_hours"].strip() or None,
                "price_range": row["price_range"].strip() or None,
                "halal": _parse_nullable_bool(
                    row["halal"],
                    column_name="halal",
                    directory_id=directory_id,
                ),
                "vegetarian": _parse_nullable_bool(
                    row["vegetarian"],
                    column_name="vegetarian",
                    directory_id=directory_id,
                ),
            }

            vendor = session.scalar(
                select(Vendor).where(
                    Vendor.directory_id == directory_id
                )
            )

            if vendor is not None:
                for field, value in vendor_directory_data.items():
                    _set_if_changed(vendor, field, value)
                if vendor.location is None:
                    vendor.location = vendor_directory_data["level_unit"]
                session.commit()
                session.refresh(vendor)
                results.append((vendor, False))
                continue

            vendor = Vendor(
                directory_id=directory_id,
                location=vendor_directory_data["level_unit"],
                **vendor_directory_data,
            )
            session.add(vendor)
            session.commit()
            session.refresh(vendor)
            results.append((vendor, True))

    return results


def seed_vendor_google_metadata(
    session: Session,
) -> tuple[int, int, int, int, int]:
    """Synchronize safe fields from ntu_food_places_final.csv.

    Blank, ambiguous, and mojibake values do not overwrite existing data.
    The return value contains matched vendors, missing vendors, changed fields,
    rejected mojibake fields, and skipped ambiguous fields.
    """
    matched_vendor_count = 0
    missing_vendor_count = 0
    changed_field_count = 0
    skipped_mojibake_count = 0
    skipped_ambiguous_count = 0

    vendors_by_directory_id = {
        vendor.directory_id: vendor
        for vendor in session.scalars(
            select(Vendor).where(Vendor.directory_id.is_not(None))
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

            # The clean directory CSV owns these display fields. We still
            # inspect their duplicates here so corrupt source text is visible,
            # but do not let Google enrichment overwrite directory data.
            for source_column in GOOGLE_DIRECTORY_DUPLICATE_FIELDS:
                _, is_mojibake = _safe_csv_text(
                    row.get(source_column) or ""
                )
                if is_mojibake:
                    skipped_mojibake_count += 1
                    print(
                        "Skipping mojibake vendor field: "
                        f"vendor={directory_id}, column={source_column}"
                    )

            for source_column, target_field in GOOGLE_TEXT_FIELD_MAP:
                value, is_mojibake = _safe_csv_text(
                    row.get(source_column) or ""
                )
                if is_mojibake:
                    skipped_mojibake_count += 1
                    print(
                        "Skipping mojibake vendor field: "
                        f"vendor={directory_id}, column={source_column}"
                    )
                    continue
                if value is not None and _set_if_changed(
                    vendor,
                    target_field,
                    value,
                ):
                    changed_field_count += 1

            rating_raw, rating_is_mojibake = _safe_csv_text(
                row.get("rating") or ""
            )
            if rating_is_mojibake:
                skipped_mojibake_count += 1
                print(
                    "Skipping mojibake vendor field: "
                    f"vendor={directory_id}, column=rating"
                )
            elif rating_raw is not None:
                rating_value = Decimal(rating_raw)
                normalized_rating = (
                    None if rating_value == 0 else rating_value
                )
                if _set_if_changed(
                    vendor,
                    "average_google_rating",
                    normalized_rating,
                ):
                    changed_field_count += 1

            review_count_raw, reviews_is_mojibake = _safe_csv_text(
                row.get("reviews") or ""
            )
            if reviews_is_mojibake:
                skipped_mojibake_count += 1
                print(
                    "Skipping mojibake vendor field: "
                    f"vendor={directory_id}, column=reviews"
                )
            elif review_count_raw is not None and _set_if_changed(
                vendor,
                "google_review_count",
                int(review_count_raw),
            ):
                changed_field_count += 1

            for source_column, target_field in (
                ("categories", "google_categories"),
                ("hours", "google_hours"),
            ):
                json_raw, is_mojibake = _safe_csv_text(
                    row.get(source_column) or ""
                )
                if is_mojibake:
                    skipped_mojibake_count += 1
                    print(
                        "Skipping mojibake vendor field: "
                        f"vendor={directory_id}, column={source_column}"
                    )
                    continue
                if json_raw is not None and _set_if_changed(
                    vendor,
                    target_field,
                    json.loads(json_raw),
                ):
                    changed_field_count += 1

            for source_column, target_field, value_map in (
                (
                    "is_temporarily_closed",
                    "is_temporarily_closed",
                    {"true": True, "false": False},
                ),
                (
                    "is_permanently_closed",
                    "is_permanently_closed",
                    {"true": True, "false": False},
                ),
            ):
                value, is_mojibake = _safe_csv_text(
                    row.get(source_column) or ""
                )
                if is_mojibake:
                    skipped_mojibake_count += 1
                    print(
                        "Skipping mojibake vendor field: "
                        f"vendor={directory_id}, column={source_column}"
                    )
                    continue
                if value is None:
                    continue
                parsed_value = value_map.get(value.casefold())
                if parsed_value is None:
                    skipped_ambiguous_count += 1
                    continue
                if _set_if_changed(vendor, target_field, parsed_value):
                    changed_field_count += 1

    session.commit()
    return (
        matched_vendor_count,
        missing_vendor_count,
        changed_field_count,
        skipped_mojibake_count,
        skipped_ambiguous_count,
    )


def seed_google_reviews(session: Session) -> tuple[int, int, int, int, int]:
    """Create or refresh Google reviews from the detailed review export."""
    created_count = 0
    updated_count = 0
    unchanged_count = 0
    missing_vendor_count = 0
    skipped_mojibake_count = 0

    vendors_by_directory_id = {
        vendor.directory_id: vendor
        for vendor in session.scalars(
            select(Vendor).where(Vendor.directory_id.is_not(None))
        ).all()
    }

    existing_reviews = {
        review.external_review_id: review
        for review in session.scalars(select(GoogleReview)).all()
    }

    with GOOGLE_REVIEWS_CSV.open(
        newline="",
        encoding="utf-8-sig",
    ) as file:
        reader = csv.DictReader(file)

        for row in reader:
            directory_id = row["ID"].strip()
            external_review_id, review_id_is_mojibake = _safe_csv_text(
                row.get("review_id") or ""
            )
            if review_id_is_mojibake or external_review_id is None:
                skipped_mojibake_count += int(review_id_is_mojibake)
                continue

            vendor = vendors_by_directory_id.get(directory_id)

            if vendor is None:
                print(
                    f"Skipping review {external_review_id}: "
                    f"vendor {directory_id} not found"
                )
                missing_vendor_count += 1
                continue

            review_data: dict[str, object] = {
                "vendor_id": vendor.id,
                "rating": int(row["rating"]),
            }

            for source_column, target_field in GOOGLE_REVIEW_TEXT_FIELD_MAP:
                value, is_mojibake = _safe_csv_text(
                    row.get(source_column) or ""
                )
                if is_mojibake:
                    skipped_mojibake_count += 1
                    print(
                        "Skipping mojibake review field: "
                        f"review={external_review_id}, column={source_column}"
                    )
                    continue
                review_data[target_field] = value

            published_at_raw, published_at_is_mojibake = _safe_csv_text(
                row.get("published_at_date") or ""
            )
            if published_at_is_mojibake or published_at_raw is None:
                skipped_mojibake_count += int(published_at_is_mojibake)
                continue
            published_at = datetime.fromisoformat(published_at_raw)

            if published_at.tzinfo is None:
                published_at = published_at.replace(
                    tzinfo=timezone.utc
                )
            review_data["published_at"] = published_at

            owner_response_at_raw, response_date_is_mojibake = _safe_csv_text(
                row.get("response_from_owner_date") or ""
            )
            if response_date_is_mojibake:
                skipped_mojibake_count += 1
                print(
                    "Skipping mojibake review field: "
                    f"review={external_review_id}, "
                    "column=response_from_owner_date"
                )
            else:
                owner_response_at = (
                    datetime.fromisoformat(owner_response_at_raw)
                    if owner_response_at_raw is not None
                    else None
                )
                if (
                    owner_response_at is not None
                    and owner_response_at.tzinfo is None
                ):
                    owner_response_at = owner_response_at.replace(
                        tzinfo=timezone.utc
                    )
                review_data["owner_response_at"] = owner_response_at

            for source_column, target_field in (
                (
                    "total_number_of_reviews_by_reviewer",
                    "reviewer_review_count",
                ),
                (
                    "total_number_of_photos_by_reviewer",
                    "reviewer_photo_count",
                ),
            ):
                raw_value, is_mojibake = _safe_csv_text(
                    row.get(source_column) or ""
                )
                if is_mojibake:
                    skipped_mojibake_count += 1
                    print(
                        "Skipping mojibake review field: "
                        f"review={external_review_id}, column={source_column}"
                    )
                    continue
                review_data[target_field] = (
                    int(raw_value) if raw_value is not None else None
                )

            local_guide_raw, local_guide_is_mojibake = _safe_csv_text(
                row.get("is_local_guide") or ""
            )
            if local_guide_is_mojibake:
                skipped_mojibake_count += 1
                print(
                    "Skipping mojibake review field: "
                    f"review={external_review_id}, column=is_local_guide"
                )
            else:
                local_guide_values = {
                    None: None,
                    "1": True,
                    "1.0": True,
                    "true": True,
                    "0": False,
                    "0.0": False,
                    "false": False,
                }
                normalized_local_guide = (
                    None
                    if local_guide_raw is None
                    else local_guide_raw.casefold()
                )
                if normalized_local_guide not in local_guide_values:
                    raise ValueError(
                        "Invalid is_local_guide value for review "
                        f"{external_review_id}: {local_guide_raw!r}"
                    )
                review_data["is_local_guide"] = local_guide_values[
                    normalized_local_guide
                ]

            for source_column, target_field in (
                ("experience_details", "experience_details"),
                ("review_photos", "review_photos"),
            ):
                json_raw, is_mojibake = _safe_csv_text(
                    row.get(source_column) or ""
                )
                if is_mojibake:
                    skipped_mojibake_count += 1
                    print(
                        "Skipping mojibake review field: "
                        f"review={external_review_id}, column={source_column}"
                    )
                    continue
                review_data[target_field] = (
                    json.loads(json_raw) if json_raw is not None else None
                )

            google_review = existing_reviews.get(external_review_id)
            if google_review is not None:
                changed = False
                for field, value in review_data.items():
                    changed |= _set_if_changed(google_review, field, value)
                if changed:
                    updated_count += 1
                else:
                    unchanged_count += 1
                continue

            google_review = GoogleReview(
                external_review_id=external_review_id,
                **review_data,
            )
            session.add(google_review)
            existing_reviews[external_review_id] = google_review
            created_count += 1

    session.commit()

    return (
        created_count,
        updated_count,
        unchanged_count,
        missing_vendor_count,
        skipped_mojibake_count,
    )


def seed_chatbot_questions(session: Session) -> tuple[int, int]:
    """Insert or refresh the curated workbook questions without prompts."""
    created_count = 0
    updated_count = 0

    for (
        question_id,
        question_text,
        search_type,
        question_scope,
        source_file,
    ) in (
        CHATBOT_QUESTION_ROWS
    ):
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


def main() -> None:
    with SessionLocal() as session:
        admin, admin_created = seed_development_admin(session)
        test_user, test_user_created = seed_development_user(session)
        vendors = seed_demo_vendors(session)
        ntu_vendors = seed_ntu_vendors(session)
        (
            google_metadata_matched,
            google_metadata_missing,
            google_metadata_changed_fields,
            google_metadata_mojibake_skipped,
            google_metadata_ambiguous_skipped,
        ) = seed_vendor_google_metadata(session)
        (
            google_reviews_created,
            google_reviews_updated,
            google_reviews_unchanged,
            google_reviews_missing,
            google_reviews_mojibake_skipped,
        ) = seed_google_reviews(session)
        chatbot_created, chatbot_updated = seed_chatbot_questions(session)

    admin_action = "Created" if admin_created else "Confirmed"
    user_action = "Created" if test_user_created else "Confirmed"
    print(
        f"{admin_action} local administrator account: "
        f"{admin.display_name} <{admin.email_address}> (id={admin.id})"
    )
    print(
        f"{user_action} local test account: "
        f"{test_user.display_name} <{test_user.email_address}> "
        f"(id={test_user.id})"
    )
    for vendor, created in vendors:
        action = "Created" if created else "Confirmed"
        print(f"{action} demo vendor: {vendor.name} (id={vendor.id})")
    for vendor, created in ntu_vendors:
        action = "Created" if created else "Confirmed"
        print(
            f"{action} NTU vendor: {vendor.directory_id} - "
            f"{vendor.name} (id={vendor.id})"
    )
    print(
        "Google reviews: "
        f"created={google_reviews_created}, "
        f"updated={google_reviews_updated}, "
        f"unchanged={google_reviews_unchanged}, "
        f"missing_vendor={google_reviews_missing}, "
        f"mojibake_skipped={google_reviews_mojibake_skipped}"
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
        f"created={chatbot_created}, updated={chatbot_updated}, "
        f"total={len(CHATBOT_QUESTION_ROWS)}"
    )


if __name__ == "__main__":
    main()
