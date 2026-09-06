from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import seed
from app.models import Vendor


def _write_vendor_csv(path: Path) -> None:
    path.write_text(
        "id,name,location,category,opening_hours,price_range,halal,vegetarian\n"
        "V001,Existing Vendor,North Spine,Cafe,Daily,$1-10,TRUE,FALSE\n"
        "V002,Unknown Halal,South Spine,Food Court,Weekdays,$10-20,null,TRUE\n",
        encoding="utf-8",
    )


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
    assert refreshed_existing.price_range == "$1-10"
    assert refreshed_existing.halal is True
    assert refreshed_existing.vegetarian is False

    unknown_halal = session.scalar(
        select(Vendor).where(Vendor.directory_id == "V002")
    )
    assert unknown_halal is not None
    assert unknown_halal.price_range == "$10-20"
    assert unknown_halal.halal is None
    assert unknown_halal.vegetarian is True


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
