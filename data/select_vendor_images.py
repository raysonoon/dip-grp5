from pathlib import Path
import pandas as pd
import hashlib
import requests
from io import BytesIO
from PIL import Image, UnidentifiedImageError

BASE = Path(__file__).resolve().parent
INPUT = BASE / "vendor_photos" / "image_validation.csv"
OUTPUT = BASE / "vendor_photos" / "selected_vendor_images.csv"

MAX_IMAGES_PER_VENDOR = 3
VALID_STATUSES = {"Valid image", "Valid image; low resolution"}

df = pd.read_csv(INPUT)
df = df[df["validation_status"].isin(VALID_STATUSES)].copy()

# Prefer higher-resolution images.
df["image_width"] = pd.to_numeric(df["image_width"], errors="coerce")
df["image_height"] = pd.to_numeric(df["image_height"], errors="coerce")
df["pixel_count"] = df["image_width"] * df["image_height"]

# Track exact duplicate image files by their downloaded bytes.
hash_cache = {}
kept = []
seen_per_vendor = {}

for _, row in df.sort_values("pixel_count", ascending=False).iterrows():
    vendor_id = str(row["vendor_directory_id"])
    url = str(row.get("image_url", row.get("source_url", ""))).strip()

    if not url or url.lower() == "nan":
        continue

    if seen_per_vendor.get(vendor_id, 0) >= MAX_IMAGES_PER_VENDOR:
        continue

    try:
        response = requests.get(
            url,
            timeout=15,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        response.raise_for_status()

        if not response.headers.get("Content-Type", "").lower().startswith("image/"):
            continue

        digest = hashlib.sha256(response.content).hexdigest()

        # Avoid selecting identical image files across the entire set.
        if digest in hash_cache:
            continue

        with Image.open(BytesIO(response.content)) as image:
            image.verify()

        hash_cache[digest] = url
        record = row.to_dict()
        record["sha256"] = digest
        record["review_status"] = "Needs visual and permission review"
        kept.append(record)
        seen_per_vendor[vendor_id] = seen_per_vendor.get(vendor_id, 0) + 1

    except (requests.RequestException, UnidentifiedImageError, OSError, ValueError):
        continue

selected = pd.DataFrame(kept)
selected.to_csv(OUTPUT, index=False)

print(f"Selected candidates: {len(selected)}")
print(f"Vendors with candidates: {selected['vendor_directory_id'].nunique() if not selected.empty else 0}")
print(f"Saved to: {OUTPUT}")

if not selected.empty:
    print("\nSelected images by vendor:")
    print(
        selected.groupby(["vendor_directory_id", "vendor_name"])
        .size()
        .to_string()
    )

print(
    "\nIMPORTANT: This script removes exact byte-for-byte duplicates only. "
    "Visually similar images still require review, and no reuse permissions "
    "have been verified."
)
