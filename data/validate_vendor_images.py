from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse
import io

import pandas as pd
import requests
from PIL import Image, UnidentifiedImageError

ROOT = Path(__file__).resolve().parents[1]
PHOTO_DIR = ROOT / "data" / "vendor_photos"
INPUT = PHOTO_DIR / "image_shortlist.csv"
OUTPUT = PHOTO_DIR / "image_validation.csv"

df = pd.read_csv(INPUT, dtype=str).fillna("")

MAX_BYTES = 12 * 1024 * 1024
TIMEOUT = 15

session = requests.Session()
session.headers.update({
    "User-Agent": "NTUFoodGuideImageReview/1.0"
})

def validate(row):
    url = row["image_url"]
    result = {
        "vendor_directory_id": row["vendor_directory_id"],
        "vendor_name": row["vendor_name"],
        "image_url": url,
        "alt_text": row.get("alt_text", ""),
        "candidate_score": row.get("candidate_score", ""),
        "http_status": "",
        "content_type": "",
        "file_size_bytes": "",
        "image_width": "",
        "image_height": "",
        "validation_status": "",
        "usage_permitted": "",
    }

    try:
        with session.get(
            url,
            stream=True,
            timeout=TIMEOUT,
            allow_redirects=True,
        ) as response:
            result["http_status"] = response.status_code
            result["content_type"] = response.headers.get(
                "Content-Type", ""
            ).split(";")[0].strip().lower()

            if response.status_code != 200:
                result["validation_status"] = "HTTP error"
                return result

            content_type = result["content_type"]
            if not content_type.startswith("image/"):
                result["validation_status"] = "Not served as an image"
                return result

            declared_length = response.headers.get("Content-Length")
            if declared_length:
                try:
                    if int(declared_length) > MAX_BYTES:
                        result["validation_status"] = "File too large"
                        return result
                except ValueError:
                    pass

            data = bytearray()
            for chunk in response.iter_content(chunk_size=65536):
                data.extend(chunk)
                if len(data) > MAX_BYTES:
                    result["validation_status"] = "File too large"
                    return result

        result["file_size_bytes"] = len(data)

        try:
            with Image.open(io.BytesIO(data)) as image:
                image.verify()

            with Image.open(io.BytesIO(data)) as image:
                width, height = image.size
                result["image_width"] = width
                result["image_height"] = height

            if width < 200 or height < 150:
                result["validation_status"] = "Valid image; low resolution"
            else:
                result["validation_status"] = "Valid image"

        except (UnidentifiedImageError, OSError, ValueError):
            result["validation_status"] = "Invalid or unsupported image"

    except requests.RequestException as exc:
        result["validation_status"] = (
            f"Request failed: {type(exc).__name__}"
        )

    return result

rows = df.to_dict(orient="records")

with ThreadPoolExecutor(max_workers=4) as pool:
    results = list(pool.map(validate, rows))

validated = pd.DataFrame(results)
validated.to_csv(OUTPUT, index=False)

print(f"Candidates checked: {len(validated)}")
print(f"Results saved to: {OUTPUT}")
print("\nValidation summary:")
print(validated["validation_status"].value_counts().to_string())

print("\nValid images by vendor:")
valid = validated[
    validated["validation_status"].isin(
        ["Valid image", "Valid image; low resolution"]
    )
]
counts = (
    valid.groupby(["vendor_directory_id", "vendor_name"])
    .size()
    .sort_values(ascending=False)
)
print(counts.to_string() if len(counts) else "No valid images found.")

print(
    "\nReminder: a valid image file is not proof of permission "
    "to reuse it."
)
