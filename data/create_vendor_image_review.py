from pathlib import Path
from io import BytesIO
import math
import requests
import pandas as pd
from PIL import Image, ImageDraw, ImageFont, ImageOps

BASE = Path(__file__).resolve().parent
INPUT = BASE / "vendor_photos" / "selected_vendor_images.csv"
OUTPUT_DIR = BASE / "vendor_photos" / "review"
CACHE_DIR = OUTPUT_DIR / "thumbnails"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR.mkdir(parents=True, exist_ok=True)

df = pd.read_csv(INPUT).reset_index(drop=True)

CELL_W = 300
CELL_H = 270
IMAGE_W = 280
IMAGE_H = 185
COLUMNS = 3
BATCH_SIZE = 15

font = ImageFont.load_default()

session = requests.Session()
session.headers.update({"User-Agent": "Mozilla/5.0"})

def fetch_thumbnail(row, index):
    cache_path = CACHE_DIR / f"{index:03d}.jpg"

    if cache_path.exists():
        try:
            with Image.open(cache_path) as cached:
                cached.verify()
            return cache_path
        except Exception:
            cache_path.unlink(missing_ok=True)

    url = str(row.get("image_url", "")).strip()

    if not url or url.lower() == "nan":
        return None

    try:
        response = session.get(url, timeout=15)
        response.raise_for_status()

        if not response.headers.get("Content-Type", "").lower().startswith("image/"):
            return None

        with Image.open(BytesIO(response.content)) as original:
            image = ImageOps.exif_transpose(original).convert("RGB")
            image.thumbnail((IMAGE_W, IMAGE_H))
            image.save(cache_path, "JPEG", quality=85)

        return cache_path

    except Exception as exc:
        print(f"Could not create thumbnail for row {index}: {type(exc).__name__}")
        return None

thumbnail_paths = []

for index, row in df.iterrows():
    thumbnail_paths.append(fetch_thumbnail(row, index))
    if (index + 1) % 10 == 0:
        print(f"Processed {index + 1}/{len(df)} candidates")

for batch_start in range(0, len(df), BATCH_SIZE):
    batch_end = min(batch_start + BATCH_SIZE, len(df))
    batch = df.iloc[batch_start:batch_end]

    rows = math.ceil(len(batch) / COLUMNS)
    sheet = Image.new(
        "RGB",
        (COLUMNS * CELL_W, rows * CELL_H),
        "white",
    )
    draw = ImageDraw.Draw(sheet)

    for offset, (_, row) in enumerate(batch.iterrows()):
        index = batch_start + offset
        x = (offset % COLUMNS) * CELL_W
        y = (offset // COLUMNS) * CELL_H

        draw.rectangle(
            [x + 5, y + 5, x + CELL_W - 5, y + CELL_H - 5],
            outline="gray",
        )

        path = thumbnail_paths[index]

        if path and path.exists():
            with Image.open(path) as image:
                image = image.convert("RGB")
                image.thumbnail((IMAGE_W, IMAGE_H))
                px = x + (CELL_W - image.width) // 2
                py = y + 10
                sheet.paste(image, (px, py))
        else:
            draw.text((x + 20, y + 30), "Preview unavailable", fill="black", font=font)

        vendor = str(row.get("vendor_name", "Unknown vendor"))
        vendor_id = str(row.get("vendor_directory_id", ""))
        alt = str(row.get("alt_text", ""))
        url = str(row.get("image_url", ""))

        text_y = y + IMAGE_H + 20
        draw.text((x + 10, text_y), f"{vendor_id}: {vendor[:36]}", fill="black", font=font)
        draw.text((x + 10, text_y + 18), f"Candidate row: {index + 1}", fill="black", font=font)
        draw.text((x + 10, text_y + 36), f"Alt: {alt[:40]}", fill="black", font=font)
        draw.text((x + 10, text_y + 54), f"URL: {url[:38]}", fill="black", font=font)

    output = OUTPUT_DIR / f"contact_sheet_{batch_start + 1:03d}_{batch_end:03d}.jpg"
    sheet.save(output, quality=90)
    print(f"Saved: {output}")

# Create a review CSV with editable human-review columns.
review = df.copy()
review["visual_approved"] = ""
review["permission_checked"] = ""
review["usage_permitted"] = ""
review["review_notes"] = ""
review.to_csv(OUTPUT_DIR / "image_review.csv", index=False)

print(f"\nReview folder: {OUTPUT_DIR}")
print(f"Candidates in review CSV: {len(review)}")
print("Review the contact sheets, then update image_review.csv.")
print("Do not set usage_permitted=true until reuse permission is confirmed.")
