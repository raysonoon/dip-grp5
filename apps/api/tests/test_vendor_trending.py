from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import Review, User, Vendor


def _stamp(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)


def _add_user(session: Session, index: int) -> User:
    user = User(
        display_name=f"Trending Reviewer {index}",
        email_address=f"trending-reviewer-{index}@example.com",
        password_hash="test-hash",
        role="user",
    )
    session.add(user)
    session.commit()
    return user


def _names(response) -> list[str]:
    assert response.status_code == 200, response.text
    return [item["name"] for item in response.json()["items"]]


def test_trending_orders_by_weighted_score_and_respects_limit(
    client,
    session: Session,
) -> None:
    same_day = _stamp("2024-01-01")
    session.add_all(
        [
            Vendor(
                name="Top Rated",
                created_at=same_day,
                average_google_rating=5.0,
            ),
            Vendor(
                name="Mid Rated",
                created_at=same_day,
                average_google_rating=3.0,
            ),
            Vendor(
                name="Low Rated",
                created_at=same_day,
                average_google_rating=1.0,
            ),
        ]
    )
    session.commit()

    response = client.get("/vendors/trending", params={"limit": 2})

    assert _names(response) == ["Top Rated", "Mid Rated"]


def test_trending_rewards_recent_vendors_when_other_signals_match(
    client,
    session: Session,
) -> None:
    session.add_all(
        [
            Vendor(
                name="Older Vendor",
                created_at=_stamp("2024-01-01"),
                average_google_rating=4.0,
            ),
            Vendor(
                name="Newer Vendor",
                created_at=_stamp("2024-06-01"),
                average_google_rating=4.0,
            ),
        ]
    )
    session.commit()

    response = client.get("/vendors/trending")

    assert _names(response) == ["Newer Vendor", "Older Vendor"]


def test_trending_rewards_more_reviewed_vendors_when_other_signals_match(
    client,
    session: Session,
) -> None:
    popular = Vendor(
        name="Popular Vendor",
        created_at=_stamp("2024-01-01"),
        average_google_rating=4.0,
    )
    quiet = Vendor(
        name="Quiet Vendor",
        created_at=_stamp("2024-01-01"),
        average_google_rating=4.0,
    )
    session.add_all([popular, quiet])
    session.commit()

    first = _add_user(session, 1)
    second = _add_user(session, 2)
    session.add_all(
        [
            Review(
                user_id=first.id,
                vendor_id=popular.id,
                rating_half_steps=8,
            ),
            Review(
                user_id=second.id,
                vendor_id=popular.id,
                rating_half_steps=8,
            ),
        ]
    )
    session.commit()

    response = client.get("/vendors/trending")

    assert _names(response) == ["Popular Vendor", "Quiet Vendor"]


def test_trending_returns_empty_items_for_an_empty_catalog(client) -> None:
    response = client.get("/vendors/trending")

    assert response.status_code == 200
    assert response.json() == {"items": []}


def test_trending_rejects_out_of_range_limits(client) -> None:
    assert client.get("/vendors/trending?limit=0").status_code == 422
    assert client.get("/vendors/trending?limit=21").status_code == 422
