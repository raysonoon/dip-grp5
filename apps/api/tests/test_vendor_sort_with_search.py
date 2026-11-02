"""A search query (`q=`) must not override the user's explicit sort choice.

The search plan adds a relevance ordering that was previously placed ahead of
the chosen sort key, silently discarding the sort whenever a query was present.
"""

from sqlalchemy.orm import Session

from app.models import Review, User, Vendor


def _names(response) -> list[str]:
    assert response.status_code == 200, response.text
    return [item["name"] for item in response.json()["items"]]


def test_search_does_not_override_alphabetical_sort(client, session: Session) -> None:
    # Relevance (SQLite portable mode) ranks exact name > prefix > substring.
    session.add_all(
        [
            Vendor(name="chicken"),  # exact match  -> highest relevance
            Vendor(name="chicken rice"),  # prefix match -> middle
            Vendor(name="bbq chicken"),  # substring    -> lowest
        ]
    )
    session.commit()

    response = client.get(
        "/vendors", params={"q": "chicken", "sort": "alphabetical"}
    )

    assert _names(response) == ["bbq chicken", "chicken", "chicken rice"]


def test_search_does_not_override_rating_sort(client, session: Session) -> None:
    session.add_all(
        [
            Vendor(name="chicken", average_google_rating=3.0),
            Vendor(name="chicken rice", average_google_rating=5.0),
            Vendor(name="bbq chicken", average_google_rating=4.0),
        ]
    )
    session.commit()

    response = client.get("/vendors", params={"q": "chicken", "sort": "rating"})

    assert _names(response) == ["chicken rice", "bbq chicken", "chicken"]


def test_search_does_not_override_reviews_sort(client, session: Session) -> None:
    chicken = Vendor(name="chicken")
    chicken_rice = Vendor(name="chicken rice")
    bbq_chicken = Vendor(name="bbq chicken")
    session.add_all([chicken, chicken_rice, bbq_chicken])
    session.commit()

    # One review per (user, vendor) due to a unique constraint, so use distinct
    # users to reach the target review counts.
    for vendor, count in ((chicken, 1), (chicken_rice, 3), (bbq_chicken, 2)):
        for offset in range(count):
            user = User(
                display_name=f"sort-{vendor.name}-{offset}",
                email_address=f"sort-{vendor.name}-{offset}@test.com",
                email_canonical=f"sort-{vendor.name}-{offset}@test.com",
                password_hash="test",
                role="user",
            )
            session.add(user)
            session.flush()
            session.add(
                Review(user_id=user.id, vendor_id=vendor.id, rating_half_steps=8)
            )
    session.commit()

    response = client.get("/vendors", params={"q": "chicken", "sort": "reviews"})

    assert _names(response) == ["chicken rice", "bbq chicken", "chicken"]
