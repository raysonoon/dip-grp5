from playwright.sync_api import sync_playwright
import pandas as pd
import re
import time
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


# ============================================================
# RUN PROGRAM
# ============================================================

if __name__ == "__main__":
    main()