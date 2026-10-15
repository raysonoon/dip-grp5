from playwright.sync_api import sync_playwright
import pandas as pd
import re
import time
import argparse
import hashlib
from io import BytesIO
from pathlib import Path
from urllib.parse import quote_plus
import requests
from PIL import Image, ImageOps, UnidentifiedImageError
from ddgs import DDGS


# ============================================================
# SETTINGS
# ============================================================

BASE_URL = (
    "https://www.ntu.edu.sg/life-at-ntu/leisure-and-dining/"
    "general-directory"
)

# NTU Food & Beverages filter
FOOD_TYPE = "02f94b0a-3ca5-4abb-9750-ed2ce1fb05ba"

# Number of NTU pages to scrape
START_PAGE = 1
END_PAGE = 7

OUTPUT_FILE = "ntu_food_stalls.csv"

# ============================================================
# GOOGLE MAPS COORDINATES
# ============================================================

COORDINATES_INPUT_FILE = "google_reviews/ntu_food_places_final.csv"
COORDINATES_OUTPUT_FILE = "google_reviews/ntu_food_places_final.csv"

# Google Maps usually stores coordinates as:
# !3d<latitude>!4d<longitude>
GOOGLE_MAPS_COORDINATES_PATTERN = re.compile(
    r"!3d(-?\d+(?:\.\d+)?)!4d(-?\d+(?:\.\d+)?)"
)

# ============================================================
# GOOGLE MAPS VENDOR PHOTOS
# ============================================================

DATA_DIR = Path(__file__).resolve().parent

PHOTO_VENDOR_CSV = DATA_DIR / "fnb-directory-v2.csv"
PHOTO_PLACES_CSV = DATA_DIR / "google_reviews" / "ntu_food_places_final.csv"
PHOTO_DIR = DATA_DIR / "vendor_photos"
PHOTO_DOWNLOAD_DIR = PHOTO_DIR / "downloads"
PHOTO_MANIFEST_CSV = PHOTO_DIR / "manifest.csv"
PHOTO_MISSING_CSV = PHOTO_DIR / "vendors_missing_photos.csv"

MAX_PHOTOS_PER_VENDOR = 3
PHOTO_MIN_WIDTH = 400
PHOTO_MIN_HEIGHT = 300
PHOTO_MAX_BYTES = 10 * 1024 * 1024

# Place photos only. Excludes reviewer avatars (/a/, /a-/).
GOOGLE_PHOTO_PATTERN = re.compile(
    r"^https://lh\d\.googleusercontent\.com/"
    r"(?:gps-cs-s|gps-cs|grass-cs|p)/"
)

# Size suffix requested for each downloaded photo
GOOGLE_PHOTO_SIZE = "=w1200-h900-k-no"

# Rough NTU campus bounding box: (min_lat, max_lat, min_lng, max_lng)
NTU_BOUNDS = (1.335, 1.360, 103.670, 103.695)

PHOTO_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def clean_text(text):
    """Remove unnecessary whitespace."""

    if not text:
        return ""

    return re.sub(r"\s+", " ", text).strip()


def extract_phone(text):
    """
    Try to find a Singapore phone number.

    Examples:
        6791 1744
        67911744
        9182 9307
        +65 6791 1744
        (65) 67911744
    """

    if not text:
        return None

    patterns = [
        r"\+65[\s\-]?\d{4}[\s\-]?\d{4}",
        r"\(65\)[\s\-]?\d{4}[\s\-]?\d{4}",
        r"\b[3689]\d{3}[\s\-]?\d{4}\b",
    ]

    for pattern in patterns:

        match = re.search(pattern, text)

        if match:
            phone = match.group(0)

            # Convert to a consistent format
            phone = re.sub(r"[^\d]", "", phone)

            # Remove Singapore country code
            if phone.startswith("65") and len(phone) == 10:
                phone = phone[2:]

            return phone

    return None


def normalise_url(url):
    """Convert relative NTU URLs into full URLs."""

    if not url:
        return None

    if url.startswith("/"):
        return "https://www.ntu.edu.sg" + url

    return url

def extract_map_coordinates(link):
    """
    Extract latitude and longitude from a Google Maps URL.

    Google Maps links usually contain:
        !3d<latitude>!4d<longitude>

    Returns:
        (latitude, longitude) if valid
        None if coordinates cannot be found
    """

    if not link:
        return None

    link = str(link)

    match = GOOGLE_MAPS_COORDINATES_PATTERN.search(link)

    if not match:
        return None

    latitude = float(match.group(1))
    longitude = float(match.group(2))

    # Validate coordinate ranges
    if not -90 <= latitude <= 90:
        return None

    if not -180 <= longitude <= 180:
        return None

    return latitude, longitude

def scrape_map_coordinates(
    input_file=COORDINATES_INPUT_FILE,
    output_file=COORDINATES_OUTPUT_FILE,
):
    """
    Read Google Maps links from ntu_food_places_final.csv,
    extract latitude/longitude, and write them back to the CSV.

    The coordinates are stored as:
        POINT(longitude latitude)

    which matches the PostGIS POINT format.
    """

    print()
    print("=" * 70)
    print("SCRAPING GOOGLE MAPS COORDINATES")
    print("=" * 70)

    # --------------------------------------------------------
    # Read CSV
    # --------------------------------------------------------

    df = pd.read_csv(input_file)

    if "link" not in df.columns:
        raise ValueError(
            "Column 'link' was not found in "
            f"{input_file}"
        )

    # --------------------------------------------------------
    # Extract coordinates
    # --------------------------------------------------------

    coordinates = []

    for index, row in df.iterrows():

        name = row.get("name", "")

        link = row.get("link")

        result = extract_map_coordinates(link)

        if result is None:

            print(
                f"[{index + 1}/{len(df)}] "
                f"{name}: coordinates not found"
            )

            coordinates.append(None)

            continue

        latitude, longitude = result

        # ----------------------------------------------------
        # Store as PostGIS-compatible POINT
        #
        # IMPORTANT:
        # lat, lng
        # ----------------------------------------------------

        coordinates_value = (
            f"({latitude}, {longitude})"
        )

        coordinates.append(coordinates_value)

        print(
            f"[{index + 1}/{len(df)}] "
            f"{name}: "
            f"({latitude}, {longitude})"
        )

    # --------------------------------------------------------
    # Add/update column
    # --------------------------------------------------------

    df["map_coordinates"] = coordinates

    # --------------------------------------------------------
    # Save CSV
    # --------------------------------------------------------

    df.to_csv(
        output_file,
        index=False,
        encoding="utf-8-sig"
    )

    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------

    successful = df["map_coordinates"].notna().sum()
    missing = df["map_coordinates"].isna().sum()

    print()
    print("=" * 70)
    print("COORDINATE SCRAPING COMPLETE")
    print("=" * 70)

    print(f"Total vendors:       {len(df)}")
    print(f"Coordinates found:   {successful}")
    print(f"Coordinates missing: {missing}")
    print(f"Output file:         {output_file}")


# ============================================================
# WEB SEARCH
# ============================================================

def search_web(stall_name):
    """
    Search the web for:

        "stall name" NTU

    Returns search results.
    """

    query = f'"{stall_name}" NTU'

    print(f"    Searching: {query}")

    try:

        with DDGS() as ddgs:

            results = list(
                ddgs.text(
                    query,
                    region="sg-en",
                    safesearch="off",
                    max_results=8
                )
            )

        return results

    except Exception as e:

        print(f"    Search error: {e}")

        return []


# ============================================================
# FIND PHONE ONLINE
# ============================================================

def find_phone_online(stall_name, results=None):
    """
    Search online for a phone number when NTU
    does not provide one.
    """

    if results is None:
        results = search_web(stall_name)

    for result in results:

        title = result.get("title", "")
        body = result.get("body", "")
        href = result.get("href", "")

        combined_text = (
            f"{title} {body} {href}"
        )

        phone = extract_phone(combined_text)

        if phone:
            return phone

    return None


# ============================================================
# FIND WEBSITE ONLINE
# ============================================================

def find_website_online(stall_name, results=None):
    """
    Search online for the stall's website.

    Websites such as Facebook, Instagram,
    Foodpanda, Grab, TripAdvisor, etc.
    are ignored.
    """

    if results is None:
        results = search_web(stall_name)

    ignored_domains = [
        "google.com",
        "googleusercontent.com",
        "facebook.com",
        "instagram.com",
        "tiktok.com",
        "youtube.com",
        "reddit.com",
        "tripadvisor.com",
        "foodpanda.sg",
        "grab.com",
        "deliveroo.com",
        "shopee.sg",
        "lazada.sg",
        "ntu.edu.sg",
    ]

    for result in results:

        url = result.get("href", "")

        if not url:
            continue

        url_lower = url.lower()

        # Ignore unwanted websites
        if any(
            domain in url_lower
            for domain in ignored_domains
        ):
            continue

        # Only accept normal web pages
        if url.startswith("http"):

            return url

    return None


# ============================================================
# SCRAPE ONE NTU PAGE
# ============================================================

def scrape_page(page, page_number):
    """
    Scrape one NTU directory page.
    """

    url = (
        f"{BASE_URL}"
        f"?locationTypes={FOOD_TYPE}"
        f"&locationCategories=all"
        f"&page={page_number}"
    )

    print()
    print("=" * 70)
    print(f"Scraping page {page_number}")
    print("=" * 70)
    print(url)

    page.goto(
        url,
        wait_until="networkidle",
        timeout=60000
    )

    # Allow dynamic content to finish loading
    page.wait_for_timeout(2000)

    stalls = []

    # --------------------------------------------------------
    # Find listing headings
    # --------------------------------------------------------

    headings = page.locator("h2, h3")

    count = headings.count()

    print(f"Found {count} headings")

    ignored = [
        "F&B, Retail and Services",
        "Filters",
        "Refine your results",
        "Announcements",
        "New on Campus!",
        "Parcel Collection Points",
    ]

    for i in range(count):

        heading = headings.nth(i)

        try:
            name = clean_text(
                heading.inner_text()
            )

        except Exception:
            continue

        if not name:
            continue

        # Ignore page/interface headings
        if name in ignored:
            continue

        # ----------------------------------------------------
        # Find the container containing the stall information
        # ----------------------------------------------------

        container = heading.locator(
            "xpath=.."
        )

        text = ""

        for _ in range(4):

            try:

                text = clean_text(
                    container.inner_text()
                )

                if len(text) > len(name) + 20:
                    break

                container = container.locator(
                    "xpath=.."
                )

            except Exception:
                break

        if not text:
            text = name

        # ----------------------------------------------------
        # Find links
        # ----------------------------------------------------

        links = container.locator("a")

        website = None
        listing_url = None

        for j in range(links.count()):

            link = links.nth(j)

            try:
                href = link.get_attribute("href")

            except Exception:
                href = None

            if not href:
                continue

            href = normalise_url(href)

            # NTU listing
            if "ntu.edu.sg" in href.lower():

                listing_url = href

            # External website
            elif href.startswith("http"):

                website = href

        # ----------------------------------------------------
        # Extract phone from NTU listing
        # ----------------------------------------------------

        phone = extract_phone(text)

        stalls.append({
            "name": name,
            "phone": phone,
            "website": website,
            "ntu_listing_url": listing_url,
            "raw_text": text,
        })

    return stalls


# ============================================================
# GOOGLE MAPS VENDOR PHOTOS
# ============================================================

def find_place_photo_urls(page, maps_url):
    """
    Open one Google Maps place and collect its photo URLs
    from the place photo gallery.

    Returns:
        (resolved_place_url, place_title, [photo_url, ...])
    """

    page.goto(
        maps_url,
        wait_until="domcontentloaded",
        timeout=60000
    )

    page.wait_for_timeout(4000)

    # EU-style consent screens block the map until dismissed
    for label in ["Reject all", "Accept all"]:

        button = page.get_by_role("button", name=label)

        if button.count():
            button.first.click()
            page.wait_for_timeout(3000)
            break

    # A search that matches several places shows a result list.
    # Open the top result; the caller checks it is the vendor.
    if "/maps/place/" not in page.url:

        first_result = page.locator(
            'div[role="feed"] a[href*="/maps/place/"]'
        )

        if not first_result.count():
            return page.url, "", []

        page.goto(
            first_result.first.get_attribute("href"),
            wait_until="domcontentloaded",
            timeout=60000
        )

        page.wait_for_timeout(4000)

    place_url = page.url

    # Place name heading, used to confirm search results
    heading = page.locator("h1")

    place_title = (
        clean_text(heading.first.inner_text())
        if heading.count()
        else ""
    )

    # --------------------------------------------------------
    # Open the photo gallery
    # --------------------------------------------------------

    gallery_buttons = [
        page.locator('button[aria-label^="Photo of"]'),
        page.get_by_role("button", name=re.compile(r"\d+\s+Photos?$")),
        page.get_by_role("button", name=re.compile(r"See photos")),
    ]

    opened = False

    for button in gallery_buttons:

        if button.count():

            try:
                button.first.click(timeout=5000)
                opened = True
                break

            except Exception:
                continue

    if not opened:
        return place_url, place_title, []

    page.wait_for_timeout(4000)

    # --------------------------------------------------------
    # Collect image URLs (img tags and background images)
    # --------------------------------------------------------

    raw_urls = page.evaluate(
        """
        () => {
            const urls = [];

            document.querySelectorAll("img").forEach(img => {
                if (img.src) urls.push(img.src);
            });

            document
                .querySelectorAll('[style*="background-image"]')
                .forEach(element => {
                    const match = element.style.backgroundImage
                        .match(/url\\("?(.*?)"?\\)/);
                    if (match) urls.push(match[1]);
                });

            return urls;
        }
        """
    )

    photo_urls = []
    seen = set()

    for url in raw_urls:

        if url.startswith("//"):
            url = "https:" + url

        if not GOOGLE_PHOTO_PATTERN.match(url):
            continue

        # Drop the size suffix so thumbnails and full images
        # of the same photo are treated as one
        base_url = url.split("=")[0]

        if base_url in seen:
            continue

        seen.add(base_url)

        photo_urls.append(base_url + GOOGLE_PHOTO_SIZE)

    return place_url, place_title, photo_urls


def place_name_matches(vendor_name, place_title):
    """
    Check that every meaningful word in a Google Maps place title
    also appears in the vendor name.

    Example:
        "Thai Dynasty Express" does not match "Wok Express"
    """

    ignored_words = {
        "the", "and", "at", "ntu", "cafe", "café", "food",
        "court", "stall", "from", "singapore", "google", "maps",
    }

    def words(text):
        return {
            word
            for word in re.findall(r"[a-z0-9']+", text.lower())
            if len(word) >= 3 and word not in ignored_words
        }

    title_words = words(place_title)

    return bool(title_words) and title_words <= words(vendor_name)


def google_place_id(maps_url):
    """Return the 0x...:0x... place ID from a Google Maps URL."""

    match = re.search(r"!1s(0x[0-9a-f]+:0x[0-9a-f]+)", maps_url or "")

    return match.group(1) if match else None


def is_on_campus(place_url):
    """Check that a Google Maps place URL points inside NTU."""

    result = extract_map_coordinates(place_url)

    if result is None:

        match = re.search(
            r"@(-?\d+\.\d+),(-?\d+\.\d+)",
            place_url
        )

        if not match:
            return False

        result = (
            float(match.group(1)),
            float(match.group(2))
        )

    latitude, longitude = result

    min_lat, max_lat, min_lng, max_lng = NTU_BOUNDS

    return (
        min_lat <= latitude <= max_lat
        and min_lng <= longitude <= max_lng
    )


def download_vendor_photo(session, url):
    """
    Download one photo and return JPEG bytes.

    Returns None when the photo is not usable.
    """

    try:

        response = session.get(url, timeout=30)
        response.raise_for_status()

        content_type = response.headers.get(
            "Content-Type",
            ""
        ).lower()

        if not content_type.startswith("image/"):
            return None

        raw = response.content

        if len(raw) > PHOTO_MAX_BYTES:
            return None

        with Image.open(BytesIO(raw)) as image:

            image.load()

            width, height = image.size

            # Skip tiny images (icons, logos, avatars)
            if (
                width < PHOTO_MIN_WIDTH
                or height < PHOTO_MIN_HEIGHT
            ):
                return None

            if image.format == "JPEG":
                return raw

            # The seeder accepts JPEG/PNG; normalise to JPEG
            image = ImageOps.exif_transpose(image).convert("RGB")

            buffer = BytesIO()
            image.save(buffer, format="JPEG", quality=90)

            return buffer.getvalue()

    except (
        requests.RequestException,
        UnidentifiedImageError,
        OSError,
        ValueError,
    ):
        return None


def scrape_vendor_photos(vendor_ids=None):
    """
    Scrape up to three Google Maps photos for every vendor in
    fnb-directory-v2.csv.

    Outputs (read by apps/api/app/db/seed_vendor_images.py):
        vendor_photos/downloads/<vendor id>_<n>.jpg
        vendor_photos/manifest.csv
        vendor_photos/vendors_missing_photos.csv

    vendor_ids:
        Optional list of vendor IDs to re-scrape. Manifest rows for
        other vendors are kept.
    """

    print()
    print("=" * 70)
    print("SCRAPING GOOGLE MAPS VENDOR PHOTOS")
    print("=" * 70)

    PHOTO_DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

    vendors = pd.read_csv(
        PHOTO_VENDOR_CSV,
        dtype=str,
        encoding="utf-8-sig"
    ).fillna("")

    places = pd.read_csv(
        PHOTO_PLACES_CSV,
        dtype=str,
        encoding="utf-8-sig"
    ).fillna("")

    # Place links found by the Google review scrape, keyed by vendor ID
    place_links = {
        row["ID"].strip(): row["link"].strip()
        for _, row in places.iterrows()
        if row.get("ID") and row.get("link")
    }

    # Places already linked to a vendor; a search result that lands
    # on one of these belongs to a different vendor
    known_place_ids = {
        google_place_id(link)
        for link in place_links.values()
    } - {None}

    if vendor_ids:

        wanted = {vendor_id.strip() for vendor_id in vendor_ids}

        selected = vendors[vendors["id"].isin(wanted)]

    else:

        selected = vendors

    session = requests.Session()
    session.headers.update({"User-Agent": PHOTO_USER_AGENT})

    manifest_rows = []
    report_rows = []

    with sync_playwright() as p:

        browser = p.chromium.launch(
            headless=True
        )

        page = browser.new_page(
            viewport={"width": 1280, "height": 900},
            locale="en-US",
            user_agent=PHOTO_USER_AGENT,
        )

        for index, (_, vendor) in enumerate(
            selected.iterrows(),
            start=1
        ):

            vendor_id = vendor["id"].strip()
            name = vendor["name"].strip()

            print()
            print(
                f"[{index}/{len(selected)}] "
                f"{vendor_id} {name}"
            )

            maps_url = place_links.get(vendor_id)
            from_search = False

            if not maps_url:

                # No known place link: fall back to a Maps search
                query = " ".join(
                    part
                    for part in [
                        name,
                        vendor.get("location", "").strip(),
                        "NTU Singapore",
                    ]
                    if part
                )

                maps_url = (
                    "https://www.google.com/maps/search/"
                    + quote_plus(query)
                )

                from_search = True

            status = ""
            photo_urls = []
            place_url = maps_url
            place_title = ""

            try:

                place_url, place_title, photo_urls = (
                    find_place_photo_urls(page, maps_url)
                )

                if "/maps/place/" not in place_url:
                    status = "Search did not find a place"

                elif (
                    from_search
                    and google_place_id(place_url) in known_place_ids
                ):
                    status = "Search result is another vendor's place"
                    photo_urls = []

                elif from_search and not is_on_campus(place_url):
                    status = "Search result is outside NTU"
                    photo_urls = []

                elif from_search and not place_name_matches(
                    name,
                    place_title
                ):
                    status = (
                        "Search result name does not match: "
                        f"{place_title}"
                    )
                    photo_urls = []

                elif not photo_urls:
                    status = "No photos on Google Maps"

            except Exception as e:

                status = f"Browser error: {type(e).__name__}"

            # Remove photos from an earlier run of this vendor
            for old_file in PHOTO_DOWNLOAD_DIR.glob(
                f"{vendor_id}_*"
            ):
                old_file.unlink()

            saved = 0
            seen_hashes = set()

            for photo_url in photo_urls:

                if saved >= MAX_PHOTOS_PER_VENDOR:
                    break

                data = download_vendor_photo(session, photo_url)

                if data is None:
                    continue

                digest = hashlib.sha256(data).hexdigest()

                if digest in seen_hashes:
                    continue

                seen_hashes.add(digest)
                saved += 1

                filename = f"{vendor_id}_{saved}.jpg"

                (PHOTO_DOWNLOAD_DIR / filename).write_bytes(data)

                manifest_rows.append({
                    "vendor_directory_id": vendor_id,
                    "filename": filename,
                    "mime_type": "image/jpeg",
                    "display_order": saved,
                    "source_url": photo_url,
                    "usage_permitted": "true",
                    "source": "google_maps",
                    "maps_url": place_url,
                })

            if saved:
                status = f"Downloaded {saved} photo(s)"

            elif not status:
                status = "No usable photos"

            print(f"  {status}")

            report_rows.append({
                "vendor_directory_id": vendor_id,
                "vendor_name": name,
                "photos_downloaded": saved,
                "status": status,
                "maps_url": place_url,
            })

            # Be polite to Google Maps
            time.sleep(2)

        browser.close()

    # ========================================================
    # WRITE MANIFEST
    # ========================================================

    manifest_columns = [
        "vendor_directory_id",
        "filename",
        "mime_type",
        "display_order",
        "source_url",
        "usage_permitted",
        "source",
        "maps_url",
    ]

    manifest = pd.DataFrame(manifest_rows, columns=manifest_columns)

    # Keep rows for vendors that were not re-scraped this run
    if vendor_ids and PHOTO_MANIFEST_CSV.exists():

        existing = pd.read_csv(
            PHOTO_MANIFEST_CSV,
            dtype=str
        ).fillna("")

        existing = existing[
            ~existing["vendor_directory_id"].isin(
                selected["id"]
            )
        ]

        manifest = pd.concat(
            [existing, manifest],
            ignore_index=True
        )[manifest_columns]

    manifest = manifest.sort_values(
        ["vendor_directory_id", "display_order"]
    )

    manifest.to_csv(PHOTO_MANIFEST_CSV, index=False)

    # ========================================================
    # REPORT VENDORS LEFT FOR MANUAL UPLOAD
    # ========================================================

    report = pd.DataFrame(
        report_rows,
        columns=[
            "vendor_directory_id",
            "vendor_name",
            "photos_downloaded",
            "status",
            "maps_url",
        ],
    )

    with_photos = set(manifest["vendor_directory_id"])

    missing = vendors[~vendors["id"].isin(with_photos)][
        ["id", "name"]
    ].merge(
        report[["vendor_directory_id", "status", "maps_url"]],
        left_on="id",
        right_on="vendor_directory_id",
        how="left",
    ).drop(columns=["vendor_directory_id"])

    missing.to_csv(PHOTO_MISSING_CSV, index=False)

    print()
    print("=" * 70)
    print("VENDOR PHOTO SCRAPING COMPLETE")
    print("=" * 70)

    print(f"Vendors processed:       {len(selected)}")
    print(f"Photos in manifest:      {len(manifest)}")
    print(f"Vendors with photos:     {len(with_photos)}")
    print(f"Vendors missing photos:  {len(missing)}")
    print(f"Manifest:                {PHOTO_MANIFEST_CSV}")
    print(f"Missing-photo report:    {PHOTO_MISSING_CSV}")

    if len(missing):

        print()
        print("Left for manual upload:")
        print(missing[["id", "name", "status"]].to_string(index=False))


# ============================================================
# MAIN
# ============================================================

def main():

    all_stalls = []

    with sync_playwright() as p:

        browser = p.chromium.launch(
            headless=False
        )

        page = browser.new_page()

        # ----------------------------------------------------
        # Scrape NTU pages
        # ----------------------------------------------------

        for page_number in range(
            START_PAGE,
            END_PAGE + 1
        ):

            try:

                stalls = scrape_page(
                    page,
                    page_number
                )

                all_stalls.extend(stalls)

                print(
                    f"Page {page_number}: "
                    f"{len(stalls)} listings"
                )

            except Exception as e:

                print(
                    f"Error on page {page_number}: "
                    f"{e}"
                )

        browser.close()

    # ========================================================
    # REMOVE DUPLICATES
    # ========================================================

    unique = {}

    for stall in all_stalls:

        key = stall["name"].lower().strip()

        if key not in unique:

            unique[key] = stall

        else:

            # Keep phone if another copy has one
            if (
                not unique[key]["phone"]
                and stall["phone"]
            ):
                unique[key]["phone"] = stall["phone"]

            # Keep website if another copy has one
            if (
                not unique[key]["website"]
                and stall["website"]
            ):
                unique[key]["website"] = stall["website"]

            # Keep NTU listing URL
            if (
                not unique[key]["ntu_listing_url"]
                and stall["ntu_listing_url"]
            ):
                unique[key]["ntu_listing_url"] = (
                    stall["ntu_listing_url"]
                )

    results = list(unique.values())

    print()
    print("=" * 70)
    print(f"Unique stalls found: {len(results)}")
    print("=" * 70)


    # ========================================================
    # ONLINE SEARCH FOR MISSING INFORMATION
    # ========================================================

    for index, stall in enumerate(
        results,
        start=1
    ):

        name = stall["name"]

        print()
        print(
            f"[{index}/{len(results)}] {name}"
        )

        # ----------------------------------------------------
        # Search web only when needed
        # ----------------------------------------------------

        needs_phone = not stall["phone"]
        needs_website = not stall["website"]

        # If both already exist, no need to search
        if not needs_phone and not needs_website:

            print("  Phone and website already found.")

            continue

        # ----------------------------------------------------
        # Search once and reuse results
        # ----------------------------------------------------

        search_results = search_web(name)

        # ----------------------------------------------------
        # Missing phone
        # ----------------------------------------------------

        if needs_phone:

            phone = find_phone_online(
                name,
                search_results
            )

            stall["phone"] = phone

            if phone:

                print(
                    f"  Phone found online: {phone}"
                )

            else:

                print(
                    "  Phone not found: null"
                )

        # ----------------------------------------------------
        # Missing website
        # ----------------------------------------------------

        if needs_website:

            website = find_website_online(
                name,
                search_results
            )

            stall["website"] = website

            if website:

                print(
                    f"  Website found: {website}"
                )

            else:

                print(
                    "  Website not found: null"
                )

        # ----------------------------------------------------
        # Be polite to search engine
        # ----------------------------------------------------

        time.sleep(2)


    # ========================================================
    # CREATE DATAFRAME
    # ========================================================

    df = pd.DataFrame(results)

    # Replace empty strings with null/None
    df["phone"] = df["phone"].replace(
        "",
        None
    )

    df["website"] = df["website"].replace(
        "",
        None
    )

    # ========================================================
    # SAVE CLEAN CSV
    # ========================================================

    df[
        [
            "name",
            "phone",
            "website",
            "ntu_listing_url",
        ]
    ].to_csv(
        OUTPUT_FILE,
        index=False,
        encoding="utf-8-sig"
    )

    # ========================================================
    # DISPLAY RESULTS
    # ========================================================

    print()
    print("=" * 70)
    print("SCRAPING COMPLETE")
    print("=" * 70)

    print(
        f"Total stalls: {len(df)}"
    )

    print(
        f"Output file: {OUTPUT_FILE}"
    )

    print()
    print(
        df[
            [
                "name",
                "phone",
                "website"
            ]
        ].to_string(index=False)
    )

    # ========================================================
    # SCRAPE GOOGLE MAPS COORDINATES
    # ========================================================

    scrape_map_coordinates()

    # ========================================================
    # SCRAPE GOOGLE MAPS VENDOR PHOTOS
    # ========================================================

    scrape_vendor_photos()


# ============================================================
# RUN PROGRAM
# ============================================================

if __name__ == "__main__":

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--photos-only",
        action="store_true",
        help="Only scrape Google Maps vendor photos",
    )

    parser.add_argument(
        "--vendor",
        action="append",
        help="Vendor ID to re-scrape photos for (repeatable)",
    )

    args = parser.parse_args()

    if args.photos_only or args.vendor:
        scrape_vendor_photos(args.vendor)
    else:
        main()