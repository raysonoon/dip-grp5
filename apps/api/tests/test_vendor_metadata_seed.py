import csv
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import seed
from app.models import Vendor


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
)


def _write_vendor_csv(path: Path) -> None:
    path.write_text(
        "id,name,location,category,opening_hours,price_range,"
        "halal,vegetarian,website,phone\n"
        "V001,Existing Vendor,North Spine,Cafe,Daily,$1-10,"
        "TRUE,FALSE,https://old-vendor.example,61234567\n"
        "V002,Unknown Halal,South Spine,Food Court,Weekdays,$10-20,"
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
    assert refreshed_existing.unit_code == "North Spine"
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
        "id,name,location,category,opening_hours,price_range,halal,vegetarian\n"
        "V001,Gel��re,NS3-01-19,Desserts / caf��,Daily,$1-10,TRUE,TRUE\n",
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
    assert existing.location == "Existing Building"
    assert existing.unit_code == "North Spine"
    assert existing.category == "Cafe"
    assert existing.opening_hours == "Daily"
    assert existing.price_range == "$1-10"
    assert existing.halal is True
    assert existing.vegetarian is False


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
    assert existing_vendor.location == (
        "50 Nanyang Ave, NS3-01-23 North Spine Plaza, "
        "Singapore 639798"
    )
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


def test_parse_google_maps_coordinates() -> None:
    link = (
        "https://www.google.com/maps/place/"
        "CHICHA+San+Chen/"
        "data=!8m2!3d1.3467033!4d103.6806362"
    )

    assert seed._parse_google_maps_coordinates(link) == (
        1.3467033,
        103.6806362,
    )


def test_parse_google_maps_coordinates_rejects_invalid_values() -> None:
    assert seed._parse_google_maps_coordinates(
        "https://example.com/!3d999!4d103.68"
    ) is None

    assert seed._parse_google_maps_coordinates(
        "https://example.com/!3d1.34!4d999"
    ) is None

    assert seed._parse_google_maps_coordinates(
        "https://example.com/no-coordinates"
    ) is None
