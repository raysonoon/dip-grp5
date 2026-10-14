import csv
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.image_storage import get_storage
from app.models import Vendor, VendorImage


REPO_ROOT = Path(__file__).resolve().parents[4]
VENDOR_CSV = REPO_ROOT / "data" / "fnb-directory-v2.csv"
PHOTO_DIR = REPO_ROOT / "data" / "vendor_photos"
DOWNLOAD_DIR = PHOTO_DIR / "downloads"
MANIFEST_PATH = PHOTO_DIR / "manifest.csv"

MIME_BY_EXTENSION = {
    ".jpg": ("image/jpeg", b"\xff\xd8\xff"),
    ".jpeg": ("image/jpeg", b"\xff\xd8\xff"),
    ".png": ("image/png", b"\x89PNG\r\n\x1a\n"),
}


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _is_permitted(value: str | None) -> bool:
    return (value or "").strip().casefold() in {"true", "yes", "1"}


def seed_vendor_images(
    session: Session,
) -> tuple[int, int, list[str]]:
    """Seed permitted vendor photos from the manifest.

    Existing images are never replaced. Display orders 1-3 are treated
    as fixed slots, so rerunning the seed does not duplicate images.
    """
    created = 0
    skipped = 0
    storage = get_storage()

    directory_rows = _read_csv(VENDOR_CSV)
    directory_names = {
        row["id"].strip(): row["name"].strip()
        for row in directory_rows
        if row.get("id") and row.get("name")
    }
    directory_ids = list(directory_names)

    vendors = session.scalars(
        select(Vendor).where(Vendor.directory_id.in_(directory_ids))
    ).all()

    vendors_by_directory_id = {
        vendor.directory_id: vendor
        for vendor in vendors
        if vendor.directory_id
    }

    for row in _read_csv(MANIFEST_PATH):
        directory_id = (row.get("vendor_directory_id") or "").strip()
        filename = (row.get("filename") or "").strip()
        mime_type = (row.get("mime_type") or "").strip().casefold()
        source_url = (row.get("source_url") or "").strip()

        try:
            display_order = int((row.get("display_order") or "").strip())
        except ValueError:
            skipped += 1
            continue

        vendor = vendors_by_directory_id.get(directory_id)

        # Only use files whose reuse permission has been confirmed.
        if (
            vendor is None
            or not filename
            or Path(filename).name != filename
            or not source_url
            or not _is_permitted(row.get("usage_permitted"))
            or display_order not in {1, 2, 3}
        ):
            skipped += 1
            continue

        extension = Path(filename).suffix.casefold()
        expected = MIME_BY_EXTENSION.get(extension)

        if expected is None or mime_type != expected[0]:
            skipped += 1
            continue

        image_path = (DOWNLOAD_DIR / filename).resolve()

        if (
            image_path.parent != DOWNLOAD_DIR.resolve()
            or not image_path.is_file()
        ):
            skipped += 1
            continue

        data = image_path.read_bytes()

        # Check the basic file signature as well as the extension.
        if len(data) < 8 or not data.startswith(expected[1]):
            skipped += 1
            continue

        used_orders = set(
            session.scalars(
                select(VendorImage.display_order).where(
                    VendorImage.vendor_id == vendor.id
                )
            ).all()
        )

        if display_order in used_orders:
            skipped += 1
            continue

        image = VendorImage(
            vendor_id=vendor.id,
            image_url="pending",
            mime_type=mime_type,
            file_size_bytes=len(data),
            display_order=display_order,
        )

        session.add(image)
        saved_reference = None

        try:
            session.flush()

            saved_reference = (
                f"/media/vendor_images/{vendor.id}/"
                f"{image.id}{extension}"
            )
            image.image_url = saved_reference

            storage.save(
                collection="vendor_images",
                owner_id=vendor.id,
                reference=saved_reference,
                data=data,
            )

            session.commit()
            created += 1

        except Exception:
            session.rollback()

            if saved_reference is not None:
                try:
                    storage.delete(
                        collection="vendor_images",
                        owner_id=vendor.id,
                        reference=saved_reference,
                    )
                except OSError:
                    pass

            raise

    # Report NTU directory vendors that still have no images.
    vendors = session.scalars(
        select(Vendor).where(Vendor.directory_id.in_(directory_ids))
    ).all()

    vendor_ids = [vendor.id for vendor in vendors]

    vendors_with_images = (
        set(
            session.scalars(
                select(VendorImage.vendor_id).where(
                    VendorImage.vendor_id.in_(vendor_ids)
                )
            ).all()
        )
        if vendor_ids
        else set()
    )

    missing_photos = [
        directory_names[vendor.directory_id]
        for vendor in vendors
        if (
            vendor.directory_id
            and vendor.id not in vendors_with_images
        )
    ]

    known_directory_ids = set(vendors_by_directory_id)

    missing_photos.extend(
        name
        for directory_id, name in directory_names.items()
        if directory_id not in known_directory_ids
    )

    return created, skipped, sorted(set(missing_photos))
