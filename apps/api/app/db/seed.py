import csv
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password
from app.db.chatbot_question_data import CHATBOT_QUESTION_ROWS
from app.db.session import SessionLocal
from app.models import (
    ChatbotPrompt,
    GoogleReview,
    User,
    Vendor,
)


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
GOOGLE_VENDOR_CORE_FIELD_MAP = (
    ("name", "name"),
    ("address", "location"),
    ("Level / unit", "unit_code"),
    ("main_category", "category"),
    ("Opening hours", "opening_hours"),
    ("price_range", "price_range"),
)
GOOGLE_VENDOR_DIETARY_FIELD_MAP = (
    ("Halal", "halal"),
    ("Vegetarian", "vegetarian"),
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
            vendor = session.scalar(
                select(Vendor).where(
                    Vendor.directory_id == directory_id
                )
            )

            vendor_directory_data: dict[str, object] = {}
            skip_new_vendor = False
            for source_column, target_field in (
                ("name", "name"),
                ("location", "unit_code"),
                ("category", "category"),
                ("opening_hours", "opening_hours"),
                ("price_range", "price_range"),
            ):
                value, is_mojibake = _safe_csv_text(
                    row.get(source_column) or ""
                )
                if is_mojibake:
                    print(
                        "Skipping mojibake directory field: "
                        f"vendor={directory_id}, column={source_column}"
                    )
                    if vendor is None and target_field == "name":
                        skip_new_vendor = True
                    continue
                if target_field == "name" and value is None:
                    if vendor is None:
                        skip_new_vendor = True
                    continue
                vendor_directory_data[target_field] = value

            if skip_new_vendor:
                print(
                    f"Skipping vendor {directory_id}: safe name not available"
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
                location=vendor_directory_data.get("unit_code"),
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
    """Merge safe vendor fields from ntu_food_places_final.csv.

    Blank and mojibake values do not overwrite existing data.
    The return value contains matched vendors, missing vendors, changed fields,
    rejected mojibake fields, and skipped ambiguous dietary fields.
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

            for source_column, target_field in GOOGLE_VENDOR_CORE_FIELD_MAP:
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

            for source_column, target_field in GOOGLE_VENDOR_DIETARY_FIELD_MAP:
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
                elif target_field == "halal" and "halal" in normalized_value:
                    parsed_value = True
                elif target_field == "vegetarian" and (
                    "vegetarian" in normalized_value
                    or "meat-free" in normalized_value
                ):
                    parsed_value = True
                else:
                    skipped_ambiguous_count += 1
                    continue

                if _set_if_changed(vendor, target_field, parsed_value):
                    changed_field_count += 1

            rating_raw = (row.get("rating") or "").strip()
            if rating_raw:
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

    session.commit()
    return (
        matched_vendor_count,
        missing_vendor_count,
        changed_field_count,
        skipped_mojibake_count,
        skipped_ambiguous_count,
    )


def seed_google_reviews(session: Session) -> tuple[int, int, int]:
    created_count = 0
    skipped_count = 0
    missing_vendor_count = 0

    vendors_by_directory_id = {
        vendor.directory_id: vendor
        for vendor in session.scalars(
            select(Vendor).where(Vendor.directory_id.is_not(None))
        ).all()
    }

    existing_review_ids = set(
        session.scalars(
            select(GoogleReview.external_review_id)
        ).all()
    )

    with GOOGLE_REVIEWS_CSV.open(
        newline="",
        encoding="utf-8-sig",
    ) as file:
        reader = csv.DictReader(file)

        for row in reader:
            directory_id = row["ID"].strip()
            external_review_id = row["review_id"].strip()

            if external_review_id in existing_review_ids:
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
                published_at=published_at,
            )
            session.add(google_review)
            existing_review_ids.add(external_review_id)
            created_count += 1

    session.commit()

    return created_count, skipped_count, missing_vendor_count


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
            google_reviews_skipped,
            google_reviews_missing,
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
        f"created={chatbot_created}, updated={chatbot_updated}, "
        f"total={len(CHATBOT_QUESTION_ROWS)}"
    )


if __name__ == "__main__":
    main()
