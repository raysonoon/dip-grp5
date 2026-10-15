from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import image_storage
from app.db.seed_vendor_images import seed_vendor_images
from app.models import Vendor, VendorImage


MANIFEST_HEADER = (
    "vendor_directory_id,filename,mime_type,display_order,"
    "source_url,usage_permitted,source,maps_url\n"
)


def _jpeg_bytes() -> bytes:
    # The seeder only checks the JPEG file signature.
    return b"\xff\xd8\xff\xe0" + b"\x00" * 16


def _setup(tmp_path: Path, session: Session, monkeypatch) -> dict:
    monkeypatch.setattr(image_storage, "UPLOADS_ROOT", tmp_path / "uploads")

    vendor_csv = tmp_path / "vendors.csv"
    vendor_csv.write_text(
        "id,name\nV001,Photo Vendor\nV002,No Photo Vendor\n",
        encoding="utf-8",
    )

    download_dir = tmp_path / "downloads"
    download_dir.mkdir()

    session.add_all([
        Vendor(name="Photo Vendor", directory_id="V001"),
        Vendor(name="No Photo Vendor", directory_id="V002"),
    ])
    session.commit()

    return {
        "vendor_csv": vendor_csv,
        "manifest_path": tmp_path / "manifest.csv",
        "download_dir": download_dir,
    }


def test_seeds_scraped_photos_and_reports_missing_vendors(
    tmp_path: Path,
    session: Session,
    monkeypatch,
) -> None:
    paths = _setup(tmp_path, session, monkeypatch)

    for order in (1, 2):
        (paths["download_dir"] / f"V001_{order}.jpg").write_bytes(
            _jpeg_bytes()
        )

    paths["manifest_path"].write_text(
        MANIFEST_HEADER
        + "".join(
            f"V001,V001_{order}.jpg,image/jpeg,{order},"
            f"https://lh3.googleusercontent.com/p/{order},true,"
            "google_maps,https://www.google.com/maps/place/x\n"
            for order in (1, 2)
        ),
        encoding="utf-8",
    )

    created, skipped, missing = seed_vendor_images(session, **paths)

    assert (created, skipped) == (2, 0)
    assert missing == ["No Photo Vendor"]

    images = session.scalars(
        select(VendorImage).order_by(VendorImage.display_order)
    ).all()
    assert [image.display_order for image in images] == [1, 2]

    for image in images:
        stored_path, _ = image_storage.resolve_image_path(
            image.image_url,
            collection="vendor_images",
            owner_id=image.vendor_id,
        )
        assert stored_path.is_file()

    # Rerunning the seed does not duplicate images.
    created, skipped, _ = seed_vendor_images(session, **paths)

    assert (created, skipped) == (0, 2)


def test_missing_manifest_leaves_all_vendors_for_manual_upload(
    tmp_path: Path,
    session: Session,
    monkeypatch,
) -> None:
    paths = _setup(tmp_path, session, monkeypatch)

    created, skipped, missing = seed_vendor_images(session, **paths)

    assert (created, skipped) == (0, 0)
    assert missing == ["No Photo Vendor", "Photo Vendor"]
