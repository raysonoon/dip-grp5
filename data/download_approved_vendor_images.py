from pathlib import Path
from io import BytesIO
import hashlib
import re

import pandas as pd
import requests
from PIL import Image, ImageOps, UnidentifiedImageError

BASE = Path(__file__).resolve().parent
DATA_DIR = BASE
PHOTO_DIR = DATA_DIR / "vendor_photos"
REVIEW_CSV = PHOTO_DIR / "review" / "image_review.csv"
DOWNLOAD_DIR = PHOTO_DIR / "downloads"
MANIFEST_CSV = PHOTO_DIR / "manifest.csv"
VENDOR_CSV = DATA_DIR / "fnb-directory-v2.csv"

MAX_IMAGES_PER_VENDOR = 3
MAX_DOWNLOAD_BYTES = 12 * 1024 * 1024
TIMEOUT = 20

DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

YES_VALUES = {"yes", "y", "true", "1"}
TRUE_VALUES = {"true", "yes", "y", "1"}

def is_yes(value):
    return str(value).strip().lower() in YES_VALUES

def is_true(value):
    return str(value).strip().lower() in TRUE_VALUES

def safe_name(value):
    return re.sub(r"[^A-Za-z0-9_-]+", "_", str(value)).strip("_")

def main():
    if not REVIEW_CSV.exists():
        raise FileNotFoundError(f"Review CSV not found: {REVIEW_CSV}")

    review = pd.read_csv(REVIEW_CSV).fillna("")

    required = {
        "vendor_directory_id",
        "vendor_name",
        "image_url",
        "visual_approved",
        "permission_checked",
        "usage_permitted",
    }
    missing_columns = required - set(review.columns)
    if missing_columns:
        raise ValueError(f"Missing review columns: {sorted(missing_columns)}")

    # Only select candidates explicitly approved visually and for reuse.
    approved = review[
        review["visual_approved"].apply(is_yes)
        & review["permission_checked"].apply(is_yes)
        & review["usage_permitted"].apply(is_true)
    ].copy()

    print(f"Review candidates: {len(review)}")
    print(f"Approved for download: {len(approved)}")

    if approved.empty:
        print(
            "\nNo images meet all three approval checks. "
            "Update image_review.csv after verifying the images and "
            "their reuse permissions. Nothing was downloaded."
        )
        return

    approved["_vendor_id"] = approved["vendor_directory_id"].astype(str)
    approved = approved.drop_duplicates(
        subset=["_vendor_id", "image_url"]
    )

    # Prefer larger images when width and height are available.
    if "image_width" in approved.columns and "image_height" in approved.columns:
        approved["_pixels"] = (
            pd.to_numeric(approved["image_width"], errors="coerce").fillna(0)
            * pd.to_numeric(approved["image_height"], errors="coerce").fillna(0)
        )
        approved = approved.sort_values("_pixels", ascending=False)

    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0"})

    manifest_rows = []
    seen_hashes = set()
    vendor_counts = {}
    failures = []

    for _, row in approved.iterrows():
        vendor_id = str(row["vendor_directory_id"]).strip()
        vendor_name = str(row["vendor_name"]).strip()
        url = str(row["image_url"]).strip()

        if not vendor_id or not url or url.lower() == "nan":
            failures.append((vendor_name, "Missing vendor ID or image URL"))
            continue

        if vendor_counts.get(vendor_id, 0) >= MAX_IMAGES_PER_VENDOR:
            continue

        try:
            response = session.get(url, timeout=TIMEOUT, stream=True)
            response.raise_for_status()

            content_type = response.headers.get("Content-Type", "").split(";")[0].lower()
            if not content_type.startswith("image/"):
                failures.append((vendor_name, f"Not served as an image: {content_type}"))
                response.close()
                continue

            chunks = []
            total_bytes = 0

            for chunk in response.iter_content(chunk_size=64 * 1024):
                if not chunk:
                    continue
                total_bytes += len(chunk)
                if total_bytes > MAX_DOWNLOAD_BYTES:
                    raise ValueError("Image exceeds 12 MiB download limit")
                chunks.append(chunk)

            response.close()
            raw = b"".join(chunks)

            if not raw:
                raise ValueError("Empty response")

            digest = hashlib.sha256(raw).hexdigest()
            if digest in seen_hashes:
                failures.append((vendor_name, "Duplicate image bytes"))
                continue

            # Decode the file and allow only formats supported by the seeder.
            with Image.open(BytesIO(raw)) as original:
                original.load()
                image_format = (original.format or "").upper()

                if image_format == "JPEG":
                    extension = ".jpg"
                    mime_type = "image/jpeg"
                    final_bytes = raw
                elif image_format == "PNG":
                    extension = ".png"
                    mime_type = "image/png"
                    final_bytes = raw
                elif image_format in {"WEBP", "GIF", "BMP", "TIFF"}:
                    # Convert other valid image formats to JPEG.
                    image = ImageOps.exif_transpose(original)
                    if image.mode in ("RGBA", "LA") or "transparency" in image.info:
                        rgba = image.convert("RGBA")
                        background = Image.new("RGB", rgba.size, "white")
                        background.paste(rgba, mask=rgba.getchannel("A"))
                        image = background
                    else:
                        image = image.convert("RGB")

                    buffer = BytesIO()
                    image.save(buffer, format="JPEG", quality=92)
                    final_bytes = buffer.getvalue()
                    extension = ".jpg"
                    mime_type = "image/jpeg"
                else:
                    failures.append((vendor_name, f"Unsupported image format: {image_format}"))
                    continue

            order = vendor_counts.get(vendor_id, 0) + 1
            filename = f"{safe_name(vendor_id)}_{order}{extension}"
            destination = DOWNLOAD_DIR / filename

            destination.write_bytes(final_bytes)

            # Verify the saved file before including it in the manifest.
            with Image.open(destination) as saved:
                saved.verify()

            manifest_rows.append({
                "vendor_directory_id": vendor_id,
                "filename": filename,
                "mime_type": mime_type,
                "display_order": order,
                "source_url": url,
                "usage_permitted": "true",
            })

            seen_hashes.add(digest)
            vendor_counts[vendor_id] = order
            print(f"Downloaded: {vendor_name} -> {filename}")

        except (
            requests.RequestException,
            UnidentifiedImageError,
            OSError,
            ValueError,
        ) as exc:
            failures.append((vendor_name, f"{type(exc).__name__}: {exc}"))

    manifest_columns = [
        "vendor_directory_id",
        "filename",
        "mime_type",
        "display_order",
        "source_url",
        "usage_permitted",
    ]

    new_manifest = pd.DataFrame(manifest_rows, columns=manifest_columns)

    # Avoid silently overwriting an existing populated manifest.
    if MANIFEST_CSV.exists():
        existing = pd.read_csv(MANIFEST_CSV).fillna("")
        if len(existing) > 0:
            print(
                f"\nExisting manifest contains {len(existing)} rows. "
                "It has NOT been overwritten."
            )
            backup_path = PHOTO_DIR / "manifest_generated.csv"
            new_manifest.to_csv(backup_path, index=False)
            print(f"New entries saved separately to: {backup_path}")
        else:
            new_manifest.to_csv(MANIFEST_CSV, index=False)
            print(f"\nManifest saved to: {MANIFEST_CSV}")
    else:
        new_manifest.to_csv(MANIFEST_CSV, index=False)
        print(f"\nManifest saved to: {MANIFEST_CSV}")

    # Report directory vendors with no successfully downloaded image.
    vendors = pd.read_csv(VENDOR_CSV).fillna("")
    id_column = "id" if "id" in vendors.columns else "vendor_directory_id"
    name_column = "name" if "name" in vendors.columns else "vendor_name"

    missing = vendors[
        ~vendors[id_column].astype(str).isin(vendor_counts.keys())
    ]

    missing_path = PHOTO_DIR / "vendors_missing_photos.csv"
    missing[[id_column, name_column]].to_csv(missing_path, index=False)

    print("\nDownload summary")
    print("----------------")
    print(f"Images downloaded: {len(manifest_rows)}")
    print(f"Vendors with downloaded images: {len(vendor_counts)}")
    print(f"Vendors still missing images: {len(missing)}")
    print(f"Missing-vendor report: {missing_path}")

    if failures:
        failures_path = PHOTO_DIR / "download_failures.csv"
        pd.DataFrame(failures, columns=["vendor_name", "reason"]).to_csv(
            failures_path, index=False
        )
        print(f"Download failures: {len(failures)}")
        print(f"Failure report: {failures_path}")

    print(
        "\nNo database changes were made. Review the manifest and downloaded "
        "images before running the database seeder."
    )

if __name__ == "__main__":
    main()
