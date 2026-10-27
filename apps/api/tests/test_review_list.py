from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Review, ReviewImage, ReviewVote, User, Vendor


@pytest.fixture
def review_list_records(session: Session) -> list[Review]:
    users = [
        User(
            display_name=f"Review voter {index}",
            email_address=f"review-voter-{index}@example.com",
            password_hash="test-hash",
        )
        for index in range(4)
    ]
    vendors = [Vendor(name="First Stall"), Vendor(name="Second Stall")]
    session.add_all([*users, *vendors])
    session.flush()

    # Insertion order differs from time and score order. Rows 2 and 3 tie on
    # time and net score; balanced votes must rank like no votes at all.
    days = [1, 4, 3, 3, 2, 3, 5]
    half_steps = [9, 8, 9, 9, 10, 9, 9]
    photo_counts = [2, 0, 1, 0, 1, 2, 1]
    votes = [
        ["up", "up"],
        ["down", "down"],
        ["up", "down"],
        [],
        ["up", "up", "down"],
        ["down"],
        [],
    ]
    reviews = []
    for index, day in enumerate(days):
        review = Review(
            user_id=users[0].id,
            vendor_id=vendors[index == 6].id,
            rating_half_steps=half_steps[index],
            comment=f"Review {index}",
            created_at=datetime(2026, 1, day, tzinfo=timezone.utc),
            images=[
                ReviewImage(
                    image_url=f"/media/review_images/{index}/{order}.jpg",
                    mime_type="image/jpeg",
                    file_size_bytes=100,
                    display_order=order,
                )
                for order in range(1, photo_counts[index] + 1)
            ],
        )
        session.add(review)
        session.flush()
        session.add_all([
            ReviewVote(review_id=review.id, user_id=user.id, vote_type=vote)
            for user, vote in zip(users, votes[index])
        ])
        reviews.append(review)
    session.commit()
    return reviews


@pytest.mark.parametrize(
    ("sort", "expected"),
    [
        (None, [6, 1, 5, 3, 2, 4, 0]),
        ("newest", [6, 1, 5, 3, 2, 4, 0]),
        ("oldest", [0, 4, 2, 3, 5, 1, 6]),
        ("best", [0, 4, 6, 3, 2, 5, 1]),
        ("controversial", [1, 5, 6, 3, 2, 4, 0]),
    ],
)
def test_review_list_sort_orders_before_pagination(
    client: TestClient, review_list_records: list[Review], sort, expected,
) -> None:
    params = {} if sort is None else {"sort": sort}
    response = client.get("/reviews", params=params)
    assert response.status_code == 200
    body = response.json()
    expected_ids = [review_list_records[index].id for index in expected]
    assert [item["id"] for item in body["items"]] == expected_ids
    assert body["total"] == 7

    page = client.get("/reviews", params={**params, "limit": 2, "offset": 1})
    assert page.status_code == 200
    assert [item["id"] for item in page.json()["items"]] == expected_ids[1:3]
    assert page.json()["total"] == 7


@pytest.mark.parametrize(
    ("rating", "expected"),
    [(4.5, [6, 5, 3, 2, 0]), (4, [1]), (5, [4]), (0.5, [])],
)
def test_review_list_filters_exact_rating(
    client: TestClient, review_list_records: list[Review], rating, expected,
) -> None:
    response = client.get("/reviews", params={"rating": rating})
    assert response.status_code == 200
    body = response.json()
    assert [item["id"] for item in body["items"]] == [
        review_list_records[index].id for index in expected
    ]
    assert body["total"] == len(expected)
    assert all(item["rating"] == rating for item in body["items"])


@pytest.mark.parametrize(
    ("media", "expected"),
    [
        ("all", [6, 1, 5, 3, 2, 4, 0]),
        ("with_photos", [6, 5, 2, 4, 0]),
        ("without_photos", [1, 3]),
    ],
)
def test_review_list_filters_media_without_duplicate_rows(
    client: TestClient, review_list_records: list[Review], media, expected,
) -> None:
    response = client.get("/reviews", params={"media": media})
    assert response.status_code == 200
    body = response.json()
    assert [item["id"] for item in body["items"]] == [
        review_list_records[index].id for index in expected
    ]
    assert body["total"] == len(expected)

    page = client.get("/reviews", params={"media": media, "limit": 1, "offset": 1})
    assert page.status_code == 200
    assert page.json()["total"] == len(expected)
    assert [item["id"] for item in page.json()["items"]] == [
        review_list_records[expected[1]].id
    ]


def test_review_list_combines_filters_and_preserves_paginated_total(
    client: TestClient, review_list_records: list[Review],
) -> None:
    expected = [0, 2, 5]
    for offset in range(4):
        response = client.get("/reviews", params={
            "vendor_id": review_list_records[0].vendor_id,
            "rating": 4.5,
            "media": "with_photos",
            "sort": "best",
            "limit": 1,
            "offset": offset,
        })
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 3
        assert body["limit"] == 1
        assert body["offset"] == offset
        assert [item["id"] for item in body["items"]] == [
            review_list_records[index].id for index in expected[offset:offset + 1]
        ]


@pytest.mark.parametrize("sort", ["invalid", "NEWEST", ""])
def test_review_list_rejects_invalid_sort(client: TestClient, sort: str) -> None:
    assert client.get("/reviews", params={"sort": sort}).status_code == 422


@pytest.mark.parametrize("rating", [0, 5.5, 4.3, -0.5, "nan", "inf"])
def test_review_list_rejects_invalid_rating(client: TestClient, rating) -> None:
    assert client.get("/reviews", params={"rating": rating}).status_code == 422


def test_review_list_rejects_invalid_media(client: TestClient) -> None:
    assert client.get("/reviews", params={"media": "photos"}).status_code == 422
