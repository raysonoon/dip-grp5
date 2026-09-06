import csv
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import seed
from app.models import GoogleReview, Vendor


GOOGLE_REVIEW_COLUMNS = (
    "ID",
    "Name",
    "place_id",
    "place_name",
    "review_id",
    "review_link",
    "name",
    "reviewer_id",
    "reviewer_profile",
    "rating",
    "review_text",
    "original_language",
    "review_translated_text",
    "translated_language",
    "published_at",
    "published_at_date",
    "response_from_owner_text",
    "response_from_owner_ago",
    "response_from_owner_date",
    "response_from_owner_translated_text",
    "avatar_link",
    "total_number_of_reviews_by_reviewer",
    "total_number_of_photos_by_reviewer",
    "is_local_guide",
    "experience_details",
    "review_photos",
    "review_origin",
)


def _review_row(**overrides: str) -> dict[str, str]:
    row = dict.fromkeys(GOOGLE_REVIEW_COLUMNS, "")
    row.update(
        {
            "ID": "V001",
            "Name": "Directory Vendor",
            "place_id": "place-1",
            "place_name": "Google Vendor",
            "review_id": "review-1",
            "rating": "5",
            "published_at_date": "2026-09-04T04:04:25",
            "total_number_of_reviews_by_reviewer": "0",
            "total_number_of_photos_by_reviewer": "0",
            "experience_details": "[]",
            "review_photos": "[]",
            "review_origin": "google",
        }
    )
    row.update(overrides)
    return row


def _write_reviews_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=GOOGLE_REVIEW_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def test_seed_google_reviews_creates_and_refreshes_all_review_metadata(
    session: Session,
    monkeypatch,
    tmp_path: Path,
) -> None:
    vendor = Vendor(directory_id="V001", name="Directory Vendor")
    session.add(vendor)
    session.flush()
    existing = GoogleReview(
        vendor_id=vendor.id,
        external_review_id="review-1",
        rating=1,
        comment="Old comment",
        published_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
    )
    session.add(existing)
    session.commit()

    csv_path = tmp_path / "reviews.csv"
    _write_reviews_csv(
        csv_path,
        [
            _review_row(
                review_link="https://maps.example.com/review-1",
                name="Review Author",
                reviewer_id="reviewer-1",
                reviewer_profile="https://maps.example.com/reviewer-1",
                review_text="Excellent food",
                original_language="en",
                review_translated_text="Translated review",
                translated_language="English",
                published_at="2 days ago",
                response_from_owner_text="Thank you",
                response_from_owner_ago="1 day ago",
                response_from_owner_date="2026-09-05T04:04:25",
                response_from_owner_translated_text="Translated response",
                avatar_link="https://example.com/avatar.jpg",
                total_number_of_reviews_by_reviewer="12",
                total_number_of_photos_by_reviewer="3",
                is_local_guide="1.0",
                experience_details='[{"name":"Food","value":5}]',
                review_photos='[{"id":"photo-1","url":"https://example.com/photo.jpg"}]',
            ),
            _review_row(
                review_id="review-2",
                rating="4",
                review_text="Good",
                published_at_date="2026-09-03T04:04:25",
            ),
            _review_row(
                ID="V999",
                review_id="missing-vendor-review",
            ),
        ],
    )
    monkeypatch.setattr(seed, "GOOGLE_REVIEWS_CSV", csv_path)

    result = seed.seed_google_reviews(session)

    assert result == (1, 1, 0, 1, 0)
    session.refresh(existing)
    assert existing.rating == 5
    assert existing.comment == "Excellent food"
    assert existing.review_link == "https://maps.example.com/review-1"
    assert existing.reviewer_name == "Review Author"
    assert existing.reviewer_id == "reviewer-1"
    assert existing.reviewer_profile_url.endswith("/reviewer-1")
    assert existing.original_language == "en"
    assert existing.translated_comment == "Translated review"
    assert existing.translated_language == "English"
    assert existing.published_at_text == "2 days ago"
    assert existing.published_at.year == 2026
    assert existing.owner_response_text == "Thank you"
    assert existing.owner_response_age_text == "1 day ago"
    assert existing.owner_response_at is not None
    assert existing.owner_response_at.year == 2026
    assert existing.owner_response_translated_text == "Translated response"
    assert existing.reviewer_avatar_url == "https://example.com/avatar.jpg"
    assert existing.reviewer_review_count == 12
    assert existing.reviewer_photo_count == 3
    assert existing.is_local_guide is True
    assert existing.experience_details == [{"name": "Food", "value": 5}]
    assert existing.review_photos[0]["id"] == "photo-1"
    assert existing.review_origin == "google"

    created = session.scalar(
        select(GoogleReview).where(
            GoogleReview.external_review_id == "review-2"
        )
    )
    assert created is not None
    assert created.rating == 4
    assert created.is_local_guide is None

    second_result = seed.seed_google_reviews(session)
    assert second_result == (0, 0, 2, 1, 0)


def test_seed_google_reviews_skips_mojibake_fields(
    session: Session,
    monkeypatch,
    tmp_path: Path,
) -> None:
    vendor = Vendor(directory_id="V001", name="Directory Vendor")
    session.add(vendor)
    session.flush()
    review = GoogleReview(
        vendor_id=vendor.id,
        external_review_id="review-1",
        rating=5,
        comment="Preserved comment",
        reviewer_name="Preserved author",
        published_at=datetime(2026, 9, 4, tzinfo=timezone.utc),
    )
    session.add(review)
    session.commit()

    csv_path = tmp_path / "reviews.csv"
    _write_reviews_csv(
        csv_path,
        [
            _review_row(
                name="FranÃ§ois",
                review_text="Great cafÃ©",
            )
        ],
    )
    monkeypatch.setattr(seed, "GOOGLE_REVIEWS_CSV", csv_path)

    result = seed.seed_google_reviews(session)

    assert result[4] == 2
    assert review.reviewer_name == "Preserved author"
    assert review.comment == "Preserved comment"
