from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import GoogleReview, Review, User, Vendor


def _rating(vendor: Vendor, session: Session) -> float | None:
    session.refresh(vendor)
    if vendor.average_rating is None:
        return None
    return float(vendor.average_rating)


def test_database_triggers_sync_internal_average_for_all_review_changes(
    session: Session,
) -> None:
    first_user = User(
        display_name="First Reviewer",
        email_address="first-reviewer@example.com",
        password_hash="test-hash",
        role="user",
    )
    second_user = User(
        display_name="Second Reviewer",
        email_address="second-reviewer@example.com",
        password_hash="test-hash",
        role="user",
    )
    vendor = Vendor(
        name="Internal Rating Vendor",
        average_google_rating=2.1,
    )
    session.add_all([first_user, second_user, vendor])
    session.commit()

    assert _rating(vendor, session) is None

    first_review = Review(
        user_id=first_user.id,
        vendor_id=vendor.id,
        rating_half_steps=7,
    )
    session.add(first_review)
    session.commit()
    assert _rating(vendor, session) == 3.5

    second_review = Review(
        user_id=second_user.id,
        vendor_id=vendor.id,
        rating_half_steps=10,
    )
    session.add(second_review)
    session.commit()
    assert _rating(vendor, session) == 4.3

    # Every review UPDATE runs synchronization, even when only text changes.
    vendor.average_rating = 1.0
    session.commit()
    first_review.comment = "Updated comment"
    session.commit()
    assert _rating(vendor, session) == 4.3

    first_review.rating_half_steps = 8
    session.commit()
    assert _rating(vendor, session) == 4.5

    session.delete(first_review)
    session.commit()
    assert _rating(vendor, session) == 5.0

    session.delete(second_review)
    session.commit()
    assert _rating(vendor, session) is None


def test_google_reviews_do_not_change_internal_average(
    session: Session,
) -> None:
    vendor = Vendor(name="Google-only Vendor", average_google_rating=4.8)
    session.add(vendor)
    session.flush()
    session.add(
        GoogleReview(
            vendor_id=vendor.id,
            external_review_id="google-only-review",
            rating=5,
            comment="External review",
            published_at=datetime.now(timezone.utc),
        )
    )
    session.commit()

    assert _rating(vendor, session) is None
    assert float(vendor.average_google_rating) == 4.8


def test_moving_a_review_recomputes_both_vendors(session: Session) -> None:
    user = User(
        display_name="Moving Reviewer",
        email_address="moving-reviewer@example.com",
        password_hash="test-hash",
        role="user",
    )
    old_vendor = Vendor(name="Old Vendor")
    new_vendor = Vendor(name="New Vendor")
    session.add_all([user, old_vendor, new_vendor])
    session.flush()
    review = Review(
        user_id=user.id,
        vendor_id=old_vendor.id,
        rating_half_steps=9,
    )
    session.add(review)
    session.commit()

    review.vendor_id = new_vendor.id
    session.commit()

    assert _rating(old_vendor, session) is None
    assert _rating(new_vendor, session) == 4.5
