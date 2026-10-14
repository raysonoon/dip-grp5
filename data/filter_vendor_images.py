from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PHOTO_DIR = ROOT / "data" / "vendor_photos"

INPUT = PHOTO_DIR / "image_candidates.csv"
OUTPUT = PHOTO_DIR / "image_shortlist.csv"
SUMMARY = PHOTO_DIR / "candidate_summary.csv"

df = pd.read_csv(INPUT, dtype=str).fillna("")

for col in ["width", "height"]:
    df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

# Rank candidates; this is a heuristic, not image recognition.
positive_terms = {
    "food": 5,
    "dish": 5,
    "menu": 2,
    "meal": 5,
    "restaurant": 3,
    "dining": 5,
    "interior": 4,
    "cafe": 3,
    "coffee": 3,
    "drink": 4,
    "dessert": 5,
    "pizza": 5,
    "burger": 5,
    "noodle": 5,
    "rice": 4,
    "soup": 5,
    "chicken": 4,
    "bread": 4,
    "pastry": 5,
    "store": 2,
    "outlet": 3,
    "shop": 2,
}

negative_terms = {
    "logo": 12,
    "icon": 10,
    "mascot": 10,
    "grabfood": 10,
    "foodpanda": 10,
    "deliverylogo": 10,
    "favicon": 12,
    "sprite": 10,
    "avatar": 8,
    "placeholder": 10,
    "payment": 8,
    "social": 5,
    "qr-code": 10,
    "qrcode": 10,
}

def score(row):
    text = " ".join([
        str(row.get("alt_text", "")),
        str(row.get("image_url", "")),
    ]).lower()

    points = 0

    for term, value in positive_terms.items():
        if term in text:
            points += value

    for term, value in negative_terms.items():
        if term in text:
            points -= value

    width = row["width"]
    height = row["height"]

    if width >= 600 and height >= 400:
        points += 4
    elif width >= 300 and height >= 200:
        points += 2

    if width and height and width < 150 and height < 100:
        points -= 8

    return points

df["candidate_score"] = df.apply(score, axis=1)

# Keep candidates with plausible image relevance.
# A human must still check the image and its reuse permissions.
shortlist = (
    df[df["candidate_score"] > 0]
    .sort_values(
        ["vendor_directory_id", "candidate_score", "width", "height"],
        ascending=[True, False, False, False],
    )
    .groupby("vendor_directory_id", group_keys=False)
    .head(8)
    .copy()
)

shortlist["review_status"] = "Needs visual review"
shortlist["usage_permitted"] = ""
shortlist["review_notes"] = ""

shortlist.to_csv(OUTPUT, index=False)

summary = (
    df.groupby(["vendor_directory_id", "vendor_name"])
    .size()
    .reset_index(name="total_candidates")
)

ranked = (
    shortlist.groupby("vendor_directory_id")
    .size()
    .reset_index(name="shortlisted_candidates")
)

summary = summary.merge(ranked, on="vendor_directory_id", how="left")
summary["shortlisted_candidates"] = (
    summary["shortlisted_candidates"].fillna(0).astype(int)
)

summary.to_csv(SUMMARY, index=False)

print(f"Original candidates: {len(df)}")
print(f"Shortlisted candidates: {len(shortlist)}")
print(f"Vendors with shortlisted candidates: {shortlist['vendor_directory_id'].nunique()}")
print(f"\nShortlist: {OUTPUT}")
print(f"Summary: {SUMMARY}")

print("\nTop candidates:")
print(
    shortlist[
        ["vendor_directory_id", "vendor_name", "candidate_score", "alt_text", "image_url"]
    ].head(20).to_string(index=False)
)
