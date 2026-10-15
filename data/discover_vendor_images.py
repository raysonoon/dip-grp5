import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import pandas as pd
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
VENDOR_CSV = ROOT / "data" / "fnb-directory-v2.csv"
PHOTO_DIR = ROOT / "data" / "vendor_photos"
OUTPUT_CSV = PHOTO_DIR / "image_candidates.csv"
REPORT_CSV = PHOTO_DIR / "discovery_report.csv"

PHOTO_DIR.mkdir(parents=True, exist_ok=True)

vendors = pd.read_csv(VENDOR_CSV, dtype=str).fillna("")
candidates = []
report = []

def is_http_url(url):
    return url.startswith(("https://", "http://"))

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(
        viewport={"width": 1280, "height": 900},
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
    )

    for _, vendor in vendors.iterrows():
        vendor_id = vendor["id"].strip()
        name = vendor["name"].strip()
        website = vendor.get("website_url", "").strip()

        print(f"[{vendor_id}] {name}")

        if not website:
            report.append({
                "vendor_directory_id": vendor_id,
                "vendor_name": name,
                "website_url": "",
                "status": "No website URL; additional discovery needed",
                "candidate_count": 0,
            })
            continue

        parsed = urlparse(website)

        # Avoid treating a PDF menu as a normal website.
        if parsed.path.lower().endswith(".pdf"):
            report.append({
                "vendor_directory_id": vendor_id,
                "vendor_name": name,
                "website_url": website,
                "status": "PDF URL; review separately",
                "candidate_count": 0,
            })
            continue

        # Social platforms may block automated access or require login.
        if parsed.netloc.lower().endswith(
            ("instagram.com", "facebook.com", "tiktok.com")
        ):
            report.append({
                "vendor_directory_id": vendor_id,
                "vendor_name": name,
                "website_url": website,
                "status": "Social media; manual review may be needed",
                "candidate_count": 0,
            })
            continue

        found_before = len(candidates)
        status = "Completed"

        try:
            response = page.goto(
                website,
                wait_until="domcontentloaded",
                timeout=20000,
            )

            if response and response.status >= 400:
                status = f"HTTP {response.status}"
            else:
                page.wait_for_timeout(1500)

                page_data = page.evaluate("""
                    () => {
                        const images = Array.from(document.images).map(img => ({
                            url: img.currentSrc || img.src || "",
                            alt: img.alt || "",
                            width: img.naturalWidth || img.width || 0,
                            height: img.naturalHeight || img.height || 0
                        }));

                        const meta = Array.from(
                            document.querySelectorAll(
                                'meta[property="og:image"], ' +
                                'meta[name="twitter:image"]'
                            )
                        ).map(m => ({
                            url: m.content || "",
                            alt: m.getAttribute("name") ||
                                 m.getAttribute("property") || ""
                        }));

                        return { images, meta };
                    }
                """)

                seen = set()

                entries = [
                    {
                        "url": item["url"],
                        "alt": item.get("alt", ""),
                        "width": item.get("width", 0),
                        "height": item.get("height", 0),
                        "discovery_method": "HTML img",
                    }
                    for item in page_data["images"]
                ]

                entries.extend([
                    {
                        "url": item["url"],
                        "alt": item.get("alt", ""),
                        "width": 0,
                        "height": 0,
                        "discovery_method": "Open Graph/Twitter metadata",
                    }
                    for item in page_data["meta"]
                ])

                for item in entries:
                    image_url = urljoin(website, item["url"]).strip()

                    if not is_http_url(image_url) or image_url in seen:
                        continue

                    seen.add(image_url)

                    # Ignore tiny icons, tracking pixels and likely thumbnails.
                    width = int(item.get("width") or 0)
                    height = int(item.get("height") or 0)

                    if width and height and (width < 150 or height < 100):
                        continue

                    candidates.append({
                        "vendor_directory_id": vendor_id,
                        "vendor_name": name,
                        "website_url": website,
                        "source_page_url": page.url,
                        "image_url": image_url,
                        "alt_text": item.get("alt", ""),
                        "width": width,
                        "height": height,
                        "discovery_method": item["discovery_method"],
                        "usage_permitted": "",
                        "review_notes": "",
                    })

                if len(candidates) == found_before:
                    status = "Visited website; no image candidates found"

        except Exception as exc:
            status = f"Could not inspect website: {type(exc).__name__}"

        report.append({
            "vendor_directory_id": vendor_id,
            "vendor_name": name,
            "website_url": website,
            "status": status,
            "candidate_count": len(candidates) - found_before,
        })

        # Avoid sending rapid requests to multiple websites.
        time.sleep(1.5)

    browser.close()

pd.DataFrame(
    candidates,
    columns=[
        "vendor_directory_id",
        "vendor_name",
        "website_url",
        "source_page_url",
        "image_url",
        "alt_text",
        "width",
        "height",
        "discovery_method",
        "usage_permitted",
        "review_notes",
    ],
).to_csv(OUTPUT_CSV, index=False)

pd.DataFrame(report).to_csv(REPORT_CSV, index=False)

print("\nDiscovery finished.")
print(f"Vendors processed: {len(vendors)}")
print(f"Image candidates found: {len(candidates)}")
print(f"Candidate file: {OUTPUT_CSV}")
print(f"Discovery report: {REPORT_CSV}")
