from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import GoogleReview, Review, User, Vendor
from app.services.ingest import build_chunks


def _seed_data(session: Session) -> Vendor:
    user = User(
        display_name="Reviewer",
        email_address="reviewer@example.com",
        password_hash="x",
        role="user",
    )
    session.add(user)
    session.flush()

    vendor = Vendor(name="Demo Vendor 1", location="Demo Canteen")
    session.add(vendor)
    session.flush()

    session.add(
        Review(
            user_id=user.id,
            vendor_id=vendor.id,
            rating_half_steps=8,
            comment="Great chicken rice with generous portions.",
        )
    )
    session.add(
        Review(
            user_id=user.id,
            vendor_id=vendor.id,
            rating_half_steps=6,
            comment=None,
        )
    )
    session.add(
        GoogleReview(
            vendor_id=vendor.id,
            external_review_id="g_123",
            rating=5,
            comment="Best noodles on campus, very filling.",
            published_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        )
    )
    session.commit()
    return vendor


def test_build_chunks_maps_internal_and_google_reviews(session: Session) -> None:
    vendor = _seed_data(session)
    vendor.average_google_rating = 4.5
    session.commit()

    chunks = build_chunks(session)

    internal = [c for c in chunks if c.source_type == "internal_review"]
    google = [c for c in chunks if c.source_type == "google_review"]

    assert len(internal) == 1
    assert internal[0].content == "Great chicken rice with generous portions."
    assert internal[0].metadata["rating"] == 4.0
    assert internal[0].vendor_id == vendor.id

    assert len(google) == 1
    assert google[0].content == "Best noodles on campus, very filling."
    assert google[0].metadata["rating"] == 5
    assert google[0].metadata["published_at"].startswith("2026-08-01T00:00:00")
    assert google[0].metadata["vendor_average_google_rating"] == 4.5


def test_build_chunks_skips_blank_comments(session: Session) -> None:
    _seed_data(session)

    chunks = build_chunks(session)

    assert all(chunk.content for chunk in chunks)
    assert all(chunk.source_id is not None for chunk in chunks)