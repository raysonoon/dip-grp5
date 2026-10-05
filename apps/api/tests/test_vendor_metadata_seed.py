import csv
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import seed
from app.models import GoogleReview, Review, User, Vendor


GOOGLE_VENDOR_COLUMNS = (
    "ID",
    "Name",
    "Location",
    "Level / unit",
    "Cuisine / type",
    "Halal",
    "Vegetarian",
    "Opening hours",
    "place_id",
    "name",
    "rating",
    "reviews",
    "price_range",
    "address",
    "main_category",
    "categories",
    "website",
    "phone",
    "hours",
    "status",
    "is_temporarily_closed",
    "is_permanently_closed",
    "link",
    "query",
    "map_coordinates",
)


def _write_vendor_csv(path: Path) -> None:
    path.write_text(
        "id,name,location,unit_number,category,opening_hours,price_range,"
        "halal,vegetarian,website,phone\n"
        "V001,Existing Vendor,North Spine,NS3-01-07,Cafe,Daily,$1-10,"
        "TRUE,FALSE,https://old-vendor.example,61234567\n"
        "V002,Unknown Halal,South Spine,SS1-02-03,Food Court,Weekdays,$10-20,"
        "null,TRUE,https://new-vendor.example,61234567\n",
        encoding="utf-8",
    )


def _write_google_vendor_csv(
    path: Path,
    rows: list[dict[str, str]],
) -> None:
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=GOOGLE_VENDOR_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def test_seed_ntu_vendors_populates_metadata_for_new_and_existing_rows(
    session: Session,
    monkeypatch,
    tmp_path: Path,
) -> None:
    csv_path = tmp_path / "vendors.csv"
    _write_vendor_csv(csv_path)
    monkeypatch.setattr(seed, "NTU_VENDOR_CSV", csv_path)

    existing = Vendor(
        directory_id="V001",
        name="Existing Vendor",
        price_range=None,
        halal=None,
        vegetarian=None,
    )
    session.add(existing)
    session.commit()

    results = seed.seed_ntu_vendors(session)

    assert [created for _, created in results] == [False, True]

    refreshed_existing = session.scalar(
        select(Vendor).where(Vendor.directory_id == "V001")
    )

    assert refreshed_existing is not None
    assert refreshed_existing.name == "Existing Vendor"
    assert refreshed_existing.location == "North Spine"
    assert refreshed_existing.unit_code == "NS3-01-07"
    assert refreshed_existing.category == "Cafe"
    assert refreshed_existing.opening_hours == "Daily"
    assert refreshed_existing.price_range == "$1-10"
    assert refreshed_existing.halal is True
    assert refreshed_existing.vegetarian is False

    # New fields from fnb-directory-v2.csv
    assert refreshed_existing.website_url == (
        "https://old-vendor.example"
    )
    assert refreshed_existing.phone_number == "61234567"

    unknown_halal = session.scalar(
        select(Vendor).where(Vendor.directory_id == "V002")
    )

    assert unknown_halal is not None
    assert unknown_halal.location == "South Spine"
    assert unknown_halal.unit_code == "SS1-02-03"
    assert unknown_halal.price_range == "$10-20"
    assert unknown_halal.halal is None
    assert unknown_halal.vegetarian is True

    # New vendor fields
    assert unknown_halal.website_url == (
        "https://new-vendor.example"
    )
    assert unknown_halal.phone_number == "61234567"


def test_seed_ntu_vendors_rejects_invalid_boolean_metadata(
    session: Session,
    monkeypatch,
    tmp_path: Path,
) -> None:
    csv_path = tmp_path / "vendors.csv"
    csv_path.write_text(
        "id,name,location,category,opening_hours,price_range,halal,vegetarian\n"
        "V001,Bad Vendor,North Spine,Cafe,Daily,$1-10,maybe,TRUE\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(seed, "NTU_VENDOR_CSV", csv_path)

    try:
        seed.seed_ntu_vendors(session)
    except ValueError as error:
        assert "Invalid halal value for vendor V001" in str(error)
    else:
        raise AssertionError("invalid boolean metadata should be rejected")


def test_seed_ntu_vendors_preserves_existing_mojibake_fields(
    session: Session,
    monkeypatch,
    tmp_path: Path,
) -> None:
    csv_path = tmp_path / "vendors.csv"
    csv_path.write_text(
        "id,name,location,unit_number,category,opening_hours,price_range,"
        "halal,vegetarian\n"
        "V001,Gel��re,North Spine,NS3-01-19,Desserts / caf��,Daily,$1-10,"
        "TRUE,TRUE\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(seed, "NTU_VENDOR_CSV", csv_path)

    existing = Vendor(
        directory_id="V001",
        name="Geláre",
        category="Dessert",
    )
    session.add(existing)
    session.commit()

    seed.seed_ntu_vendors(session)

    assert existing.name == "Geláre"
    assert existing.category == "Dessert"
    assert existing.location == "North Spine"
    assert existing.unit_code == "NS3-01-19"


def test_seed_ntu_vendors_refreshes_directory_metadata(
    session: Session,
    monkeypatch,
    tmp_path: Path,
) -> None:
    csv_path = tmp_path / "vendors.csv"
    _write_vendor_csv(csv_path)
    monkeypatch.setattr(seed, "NTU_VENDOR_CSV", csv_path)

    existing = Vendor(
        directory_id="V001",
        name="Stale Vendor",
        location="Existing Building",
        unit_code="Old Unit",
        category="Old Category",
        opening_hours="Old Hours",
        price_range="$20-30",
        halal=False,
        vegetarian=True,
    )
    session.add(existing)
    session.commit()

    seed.seed_ntu_vendors(session)

    assert existing.name == "Existing Vendor"
    assert existing.location == "North Spine"
    assert existing.unit_code == "NS3-01-07"
    assert existing.category == "Cafe"
    assert existing.opening_hours == "Daily"
    assert existing.price_range == "$1-10"
    assert existing.halal is True
    assert existing.vegetarian is False


def test_seed_ntu_vendors_deletes_stale_vendors_but_keeps_referenced(
    session: Session,
    monkeypatch,
    tmp_path: Path,
) -> None:
    csv_path = tmp_path / "vendors.csv"
    _write_vendor_csv(csv_path)
    monkeypatch.setattr(seed, "NTU_VENDOR_CSV", csv_path)

    stale = Vendor(
        directory_id="V999",
        name="Stale Vendor",
        unit_code="XYZ-01-01",
    )
    referenced = Vendor(
        directory_id="V998",
        name="Referenced Vendor",
        unit_code="XYZ-01-02",
    )
    session.add_all([stale, referenced])
    session.commit()

    user = User(
        display_name="Tester",
        email_address="tester@test",
        password_hash="x",
        role="user",
    )
    session.add(user)
    session.commit()
    session.add(
        Review(
            user_id=user.id,
            vendor_id=referenced.id,
            rating_half_steps=8,
        )
    )
    session.commit()

    seed.seed_ntu_vendors(session)

    assert (
        session.scalar(
            select(Vendor).where(Vendor.directory_id == "V999")
        )
        is None
    )
    assert (
        session.scalar(
            select(Vendor).where(Vendor.directory_id == "V998")
        )
        is not None
    )


def test_seed_google_vendor_metadata_fills_safe_fields_and_skips_mojibake(
    session: Session,
    monkeypatch,
    tmp_path: Path,
) -> None:
    csv_path = tmp_path / "google-vendors.csv"

    _write_google_vendor_csv(
        csv_path,
        [
            {
                "ID": "V001",
                "Name": "Updated Vendor",
                "Location": "North Spine Plaza",
                "Level / unit": "NS3-01-01",
                "Cuisine / type": "Cafe",
                "Halal": "No",
                "Vegetarian": "Vegetarian option(s) available",
                "Opening hours": "Daily: 9am to 6pm",
                "place_id": "place-1",
                "name": "Updated Vendor on Google",
                "rating": "4.8",
                "reviews": "123",
                "price_range": "$1-10",
                "address": (
                    "50 Nanyang Ave, NS3-01-23 North Spine Plaza, "
                    "Singapore 639798"
                ),
                "main_category": "Restaurant",
                "categories": '["Restaurant", "Cafe"]',
                "website": "https://www.chichasanchen.com.sg/",
                "phone": "88570172",
                "hours": '[{"day": "Monday", "times": ["9 am-6 pm"]}]',
                "status": "Open",
                "is_temporarily_closed": "false",
                "is_permanently_closed": "false",
                "link": (
                    "https://www.google.com/maps/place/"
                    "CHICHA+San+Chen/"
                    "data=!8m2!3d1.3467033!4d103.6806362"
                ),
                "query": "updated vendor ntu",
                "map_coordinates": "(1.3467033, 103.6806362)",
            },
            {
                "ID": "V002",
                "Name": "GelÃ¡re",
                "Location": "North Spine Plazaâ€‹",
                "Cuisine / type": "Desserts / cafÃ©",
                "Halal": "Yes â€” halal certified",
                "Vegetarian": "Not stated",
                "name": "Gelare @ NTU",
            },
        ],
    )

    monkeypatch.setattr(seed, "GOOGLE_RATINGS_CSV", csv_path)

    existing_vendor = Vendor(
        directory_id="V001",
        name="Directory Vendor",
        unit_code="Directory Unit",
        category="Directory Category",
        opening_hours="Directory Hours",
        price_range="$20-30",
        halal=True,
        vegetarian=False,
        website_url="https://old.example",
        phone_number="60000000",
        address="Old address",
        map_coordinates="POINT(103.6800000 1.3400000)",
    )

    mojibake_vendor = Vendor(
        directory_id="V002",
        name="Geláre",
        location="NS3-01-19",
        category="Desserts / café",
        halal=True,
    )

    session.add_all([existing_vendor, mojibake_vendor])
    session.commit()

    result = seed.seed_vendor_google_metadata(session)

    assert result[0] == 2
    assert result[1] == 0
    assert result[2] > 0
    assert result[3] == 1
    assert result[4] == 0

    # Existing vendor gets updated Google metadata.
    assert existing_vendor.name == "Updated Vendor on Google"
    assert existing_vendor.location is None
    assert existing_vendor.unit_code == "NS3-01-01"
    assert existing_vendor.category == "Restaurant"
    assert existing_vendor.opening_hours == "Daily: 9am to 6pm"
    assert existing_vendor.price_range == "$1-10"
    assert existing_vendor.halal is False
    assert existing_vendor.vegetarian is True
    assert float(existing_vendor.average_google_rating) == 4.8

    assert existing_vendor.website_url == (
        "https://www.chichasanchen.com.sg/"
    )
    assert existing_vendor.phone_number == "88570172"
    assert existing_vendor.address == (
        "50 Nanyang Ave, NS3-01-23 North Spine Plaza, "
        "Singapore 639798"
    )
    assert existing_vendor.map_coordinates == (
        "POINT(103.6806362 1.3467033)"
    )

    assert mojibake_vendor.name == "Gelare @ NTU"
    assert mojibake_vendor.location == "NS3-01-19"
    assert mojibake_vendor.category == "Desserts / café"
    assert mojibake_vendor.halal is True
    assert mojibake_vendor.average_google_rating is None

    second_result = seed.seed_vendor_google_metadata(session)
    assert second_result[2] == 0


def test_parse_map_coordinates() -> None:
    assert seed._parse_map_coordinates(
        "(1.3467033, 103.6806362)"
    ) == (1.3467033, 103.6806362)

    assert seed._parse_map_coordinates(" (1.0, 2.0) ") == (1.0, 2.0)


def test_parse_map_coordinates_rejects_invalid_values() -> None:
    assert seed._parse_map_coordinates("") is None
    assert seed._parse_map_coordinates("   ") is None
    assert seed._parse_map_coordinates("1.0, 2.0") is None
    assert seed._parse_map_coordinates("(1.0)") is None
    assert seed._parse_map_coordinates("(1.0, 2.0, 3.0)") is None
    assert seed._parse_map_coordinates("(999.0, 2.0)") is None
    assert seed._parse_map_coordinates("(1.0, 999.0)") is None
    assert seed._parse_map_coordinates("(abc, def)") is None


def test_seed_google_reviews_imports_and_backfills_maps_url(
    session: Session,
    monkeypatch,
    tmp_path: Path,
) -> None:
    csv_path = tmp_path / "google-reviews.csv"

    with csv_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "ID",
                "review_id",
                "rating",
                "review_text",
                "published_at_date",
                "review_link",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "ID": "V001",
                "review_id": "review-1",
                "rating": "5",
                "review_text": "Great food",
                "published_at_date": "2026-09-01T12:00:00+00:00",
                "review_link": "https://maps.example.com/review-1",
            }
        )

    monkeypatch.setattr(seed, "GOOGLE_REVIEWS_CSV", csv_path)

    vendor = Vendor(
        directory_id="V001",
        name="Test Vendor",
    )
    session.add(vendor)
    session.commit()

    created, skipped, missing_vendor = seed.seed_google_reviews(session)

    assert created == 1
    assert skipped == 0
    assert missing_vendor == 0

    review = session.scalar(
        select(GoogleReview).where(
            GoogleReview.external_review_id == "review-1"
        )
    )

    assert review is not None
    assert review.maps_url == "https://maps.example.com/review-1"

    review.maps_url = None
    session.commit()

    created, skipped, missing_vendor = seed.seed_google_reviews(session)

    assert created == 0
    assert skipped == 1
    assert missing_vendor == 0

    session.refresh(review)

    assert review.maps_url == "https://maps.example.com/review-1"


def test_vendor_category_normalization_and_overrides(
    session: Session,
    monkeypatch,
    tmp_path: Path,
) -> None:
    csv_path = tmp_path / "vendors.csv"
    csv_path.write_text(
        "id,name,location,unit_number,category,opening_hours,price_range,"
        "halal,vegetarian\n"
        "V001,Coffee Vendor,North Spine,NS1,Coffee,Daily,$1-10,TRUE,FALSE\n"
        "V002,Food Court Vendor,South Spine,SS1,Cafeteria,Daily,$1-10,TRUE,FALSE\n"
        "V005,ANDES by ASTONS,Hall 13,H13,Cafe,Daily,$1-10,TRUE,FALSE\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(seed, "NTU_VENDOR_CSV", csv_path)

    seed.seed_ntu_vendors(session)

    coffee_vendor = session.scalar(
        select(Vendor).where(Vendor.directory_id == "V001")
    )
    canteen_vendor = session.scalar(
        select(Vendor).where(Vendor.directory_id == "V002")
    )
    andes = session.scalar(
        select(Vendor).where(Vendor.directory_id == "V005")
    )

    assert coffee_vendor is not None
    assert coffee_vendor.category == "Drinks"

    assert canteen_vendor is not None
    assert canteen_vendor.category == "Canteen"

    assert andes is not None
    assert andes.category == "Restaurant"


def test_google_metadata_keeps_canonical_category_and_backfills_existing_row(
    session: Session,
    monkeypatch,
    tmp_path: Path,
) -> None:
    csv_path = tmp_path / "google-vendors.csv"

    _write_google_vendor_csv(
        csv_path,
        [
            {
                "ID": "V053",
                "Name": "Venture Drive Coffee",
                "main_category": "Cafe",
            },
            {
                "ID": "V018",
                "Name": "Food Court 1",
                "main_category": "Coffee shop",
            },
        ],
    )

    monkeypatch.setattr(seed, "GOOGLE_RATINGS_CSV", csv_path)

    drinks_vendor = Vendor(
        directory_id="V053",
        name="Venture Drive Coffee",
        category="Drinks",
    )
    stale_vendor = Vendor(
        directory_id="V018",
        name="Food Court 1",
        category="Coffee shop",
    )

    session.add_all([drinks_vendor, stale_vendor])
    session.commit()

    seed.seed_vendor_google_metadata(session)

    assert drinks_vendor.category == "Drinks"
    assert stale_vendor.category == "Canteen"

    second_result = seed.seed_vendor_google_metadata(session)

    assert second_result[2] == 0
    assert drinks_vendor.category == "Drinks"
    assert stale_vendor.category == "Canteen"