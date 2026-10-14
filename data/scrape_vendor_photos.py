import pandas as pd
from pathlib import Path
from urllib.parse import quote_plus

ROOT = Path(__file__).resolve().parents[1]
VENDOR_CSV = ROOT / "data" / "fnb-directory-v2.csv"
PHOTO_DIR = ROOT / "data" / "vendor_photos"
OUTPUT_CSV = PHOTO_DIR / "photo_discovery.csv"

PHOTO_DIR.mkdir(parents=True, exist_ok=True)

vendors = pd.read_csv(VENDOR_CSV, dtype=str).fillna("")

results = []

for _, vendor in vendors.iterrows():
    vendor_id = vendor["id"].strip()
    name = vendor["name"].strip()
    location = vendor.get("location", "").strip()
    unit = vendor.get("unit_number", "").strip()

    search_terms = " ".join(
        part for part in [name, unit, location, "NTU Singapore"] if part
    )

    results.append({
        "vendor_directory_id": vendor_id,
        "vendor_name": name,
        "location": location,
        "unit_number": unit,
        "google_maps_search_url": (
            "https://www.google.com/maps/search/?api=1&query="
            + quote_plus(search_terms)
        ),
        "photo_1_filename": "",
        "photo_1_source_url": "",
        "photo_1_usage_permitted": "",
        "photo_2_filename": "",
        "photo_2_source_url": "",
        "photo_2_usage_permitted": "",
        "photo_3_filename": "",
        "photo_3_source_url": "",
        "photo_3_usage_permitted": "",
        "notes": "",
    })

output = pd.DataFrame(results)
output.to_csv(OUTPUT_CSV, index=False)

print(f"Vendors processed: {len(output)}")
print(f"Discovery CSV: {OUTPUT_CSV}")
print("\nFirst 5 vendors:")
print(output[["vendor_directory_id", "vendor_name", "google_maps_search_url"]].head().to_string(index=False))
