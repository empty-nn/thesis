# localvietnam_crawler.py

from collections import deque
from typing import Dict, Set
from urllib.parse import (
    urljoin,
    urlparse,
    urlunparse,
)
from urllib.robotparser import RobotFileParser

import re
import time
import requests

from bs4 import BeautifulSoup

from db.session import SessionLocal
from db.full_model import URLSource, URLStatus


# =========================================================
# CONFIG
# =========================================================

BASE_URL = "https://localvietnam.com"


# =========================================================
# DESTINATIONS
#
# Da Nang and Hue are intentionally excluded because:
#
# - Da Nang -> danangfantasticity.com
# - Hue     -> visithue.vn
# =========================================================

DESTINATIONS = {

    "hanoi": {
        "seed": (
            "https://localvietnam.com/hanoi/"
            "hanoi-best-things-to-do-travel-guide/"
        ),
        "prefix": "/hanoi/",
    },

    "ho-chi-minh-city": {
        "seed": (
            "https://localvietnam.com/ho-chi-minh-city/"
            "ho-chi-minh-city-best-things-to-do-travel-guide/"
        ),
        "prefix": "/ho-chi-minh-city/",
    },

    "nha-trang": {
        "seed": (
            "https://localvietnam.com/khanh-hoa/nha-trang/"
            "nha-trang-best-things-to-do-travel-guide/"
        ),
        "prefix": "/khanh-hoa/nha-trang/",
    },

    "dalat": {
        "seed": (
            "https://localvietnam.com/lam-dong/dalat/"
            "dalat-best-things-to-do-travel-guide/"
        ),
        "prefix": "/lam-dong/dalat/",
    },

    "hoi-an": {
        "seed": (
            "https://localvietnam.com/quang-nam/hoi-an/"
            "hoi-an-best-things-to-do-travel-guide/"
        ),
        "prefix": "/quang-nam/hoi-an/",
    },

    "ninh-binh": {
        "seed": (
            "https://localvietnam.com/ninh-binh/"
            "ninh-binh-best-things-to-do-travel-guide/"
        ),
        "prefix": "/ninh-binh/",
    },

    "halong-bay": {
        "seed": (
            "https://localvietnam.com/quang-ninh/halong-bay/"
            "halong-bay-best-things-to-do-travel-guide/"
        ),
        "prefix": "/quang-ninh/halong-bay/",
    },

    "phu-quoc": {
        "seed": (
            "https://localvietnam.com/phu-quoc/"
            "phu-quoc-best-things-to-do-travel-guide/"
        ),
        "prefix": "/phu-quoc/",
    },

    "sapa": {
        "seed": (
            "https://localvietnam.com/lao-cai/sapa/"
            "sapa-travel-guide-best-things-to-do/"
        ),
        "prefix": "/lao-cai/sapa/",
    },

    "phong-nha": {
        "seed": (
            "https://localvietnam.com/quang-binh/phong-nha/"
            "phong-nha-best-things-to-do-travel-guide/"
        ),
        "prefix": "/quang-binh/phong-nha/",
    },
}


# =========================================================
# CRAWLER SETTINGS
# =========================================================

MAX_DEPTH = 2

MAX_URLS_PER_DESTINATION = 250

REQUEST_DELAY = 0.5

TIMEOUT = 30


# Keep pages like:
#
# /from-hanoi-to-ninh-binh/
#
# False is recommended initially.
KEEP_TRANSPORT_PAGES = False


# Minimum visible text before we consider
# a page useful enough to insert.
MIN_PAGE_TEXT_LENGTH = 500


# =========================================================
# USER AGENT
# =========================================================

USER_AGENT = (
    "TravelRAGResearchBot/1.0 "
    "(academic research)"
)


HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept-Language": "en-US,en;q=0.9",
}


http = requests.Session()

http.headers.update(
    HEADERS
)


# =========================================================
# EXCLUDED PATHS
# =========================================================

EXCLUDED_PATH_PARTS = {

    # Commercial
    "/tour/",
    "/tours/",
    "/package-tour/",
    "/package-tours/",

    # Company
    "/about/",
    "/contact/",
    "/reviews/",
    "/booking/",

    # Generic site-wide
    "/vietnam-blog/",
    "/vietnam-tips/",
    "/regions/",

    # WordPress / technical
    "/author/",
    "/tag/",
    "/category/",
    "/feed/",
    "/wp-content/",
    "/wp-json/",
    "/wp-admin/",
    "/wp-login",

    # Pagination
    "/page/",
}


# =========================================================
# MONTHLY WEATHER FILTER
#
# Skip pages such as:
#
# hanoi-january-weather
# hoi-an-july-weather
#
# But keep general:
#
# best-time-to-visit-hanoi
# =========================================================

MONTH_NAMES = (
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
)


MONTH_WEATHER_RE = re.compile(
    rf"({'|'.join(MONTH_NAMES)}).*weather",
    re.IGNORECASE,
)


# =========================================================
# 1. ROBOTS.TXT
# =========================================================

def create_robot_parser():
    """
    Fetch robots.txt using our requests.Session.

    This avoids RobotFileParser.read() silently treating
    some HTTP errors as disallow_all.

    Return:
        RobotFileParser -> successfully fetched + parsed
        None            -> could not retrieve robots safely
    """

    robots_url = (
        f"{BASE_URL}/robots.txt"
    )

    print()
    print(
        "=================================================="
    )

    print(
        "[ROBOTS] Checking robots.txt"
    )

    print(
        "=================================================="
    )

    try:

        response = http.get(
            robots_url,
            timeout=TIMEOUT,
        )

        print(
            f"[ROBOTS] HTTP "
            f"{response.status_code}"
        )

        # -------------------------------------------------
        # Successfully retrieved
        # -------------------------------------------------

        if response.status_code == 200:

            parser = RobotFileParser()

            parser.set_url(
                robots_url
            )

            parser.parse(
                response.text.splitlines()
            )

            print(
                "[ROBOTS] Parsed successfully"
            )

            return parser

        # -------------------------------------------------
        # Could not reliably read robots.txt
        # -------------------------------------------------

        print(
            "[ROBOTS WARNING] "
            "Could not retrieve robots.txt "
            "with HTTP 200."
        )

        print(
            "[ROBOTS WARNING] "
            "Crawler will not assume permission "
            "from a failed robots request."
        )

        return None

    except Exception as e:

        print(
            f"[ROBOTS ERROR] "
            f"{e}"
        )

        return None


# =========================================================
# 2. NORMALIZE URL
# =========================================================

def normalize_url(
    url: str,
) -> str:

    if not url:
        return ""

    url = urljoin(
        BASE_URL,
        url.strip(),
    )

    parsed = urlparse(
        url
    )

    scheme = (
        parsed.scheme
        or "https"
    ).lower()

    host = (
        parsed.netloc
    ).lower()

    # Normalize www
    if host == "www.localvietnam.com":
        host = "localvietnam.com"

    path = parsed.path

    # Remove duplicate slashes
    path = re.sub(
        r"/+",
        "/",
        path,
    )

    # Add trailing slash to normal pages
    if (
        path
        and not path.endswith("/")
        and "." not in path.split("/")[-1]
    ):
        path += "/"

    # Remove:
    #
    # query parameters
    # fragments
    #
    return urlunparse(
        (
            scheme,
            host,
            path,
            "",
            "",
            "",
        )
    )


# =========================================================
# 3. DOMAIN CHECK
# =========================================================

def is_localvietnam_url(
    url: str,
) -> bool:

    if not url:
        return False

    try:

        host = (
            urlparse(url)
            .netloc
            .lower()
        )

        return host in {
            "localvietnam.com",
            "www.localvietnam.com",
        }

    except Exception:

        return False


# =========================================================
# 4. WEBPAGE CHECK
# =========================================================

def is_webpage_url(
    url: str,
) -> bool:

    path = (
        urlparse(url)
        .path
        .lower()
    )

    blocked_extensions = (
        ".jpg",
        ".jpeg",
        ".png",
        ".gif",
        ".webp",
        ".svg",

        ".pdf",
        ".zip",
        ".rar",

        ".xml",
        ".json",

        ".css",
        ".js",

        ".mp4",
        ".mp3",
        ".avi",
    )

    return not path.endswith(
        blocked_extensions
    )


# =========================================================
# 5. URL FILTER
# =========================================================

def should_keep_url(
    url: str,
    prefix: str,
) -> bool:

    if not url:
        return False

    url = normalize_url(
        url
    )

    # -----------------------------------------------------
    # Must be LocalVietnam
    # -----------------------------------------------------

    if not is_localvietnam_url(
        url
    ):
        return False

    # -----------------------------------------------------
    # Must be normal webpage
    # -----------------------------------------------------

    if not is_webpage_url(
        url
    ):
        return False

    parsed = urlparse(
        url
    )

    path = parsed.path.lower()

    prefix = prefix.lower()

    # -----------------------------------------------------
    # IMPORTANT:
    # Stay inside destination tree
    # -----------------------------------------------------

    if not path.startswith(
        prefix
    ):
        return False

    # -----------------------------------------------------
    # Excluded sections
    # -----------------------------------------------------

    for excluded in (
        EXCLUDED_PATH_PARTS
    ):

        if excluded in path:
            return False

    # -----------------------------------------------------
    # Get final slug
    # -----------------------------------------------------

    slug = (
        path
        .rstrip("/")
        .split("/")[-1]
    )

    # -----------------------------------------------------
    # Skip repetitive monthly weather articles
    # -----------------------------------------------------

    if MONTH_WEATHER_RE.search(
        slug
    ):

        return False

    # -----------------------------------------------------
    # Skip route articles by default
    #
    # Examples:
    #
    # from-hanoi-to-hoi-an
    # from-sapa-to-hanoi
    # -----------------------------------------------------

    if not KEEP_TRANSPORT_PAGES:

        if slug.startswith(
            "from-"
        ):

            return False

    return True


# =========================================================
# 6. ROBOTS CHECK
# =========================================================

def is_allowed_by_robots(
    robots,
    url: str,
) -> bool:
    """
    If robots.txt was successfully retrieved,
    obey its rules.

    If robots is None, we do not claim that crawling
    is allowed; fetch_page() will skip because permission
    couldn't be established from robots.txt.
    """

    if robots is None:

        print(
            f"[ROBOTS UNKNOWN] {url}"
        )

        return False

    try:

        allowed = robots.can_fetch(
            USER_AGENT,
            url,
        )

    except Exception as e:

        print(
            f"[ROBOTS ERROR] "
            f"{url}: {e}"
        )

        return False

    if not allowed:

        print(
            f"[ROBOTS SKIP] "
            f"{url}"
        )

        return False

    return True


# =========================================================
# 7. FETCH PAGE
# =========================================================

def fetch_page(
    url: str,
    robots,
) -> str | None:

    # -----------------------------------------------------
    # Respect robots.txt
    # -----------------------------------------------------

    if not is_allowed_by_robots(
        robots,
        url,
    ):

        return None

    # -----------------------------------------------------
    # Request page
    # -----------------------------------------------------

    try:

        response = http.get(
            url,
            timeout=TIMEOUT,
            allow_redirects=True,
        )

        response.raise_for_status()

        content_type = (
            response.headers
            .get(
                "Content-Type",
                "",
            )
            .lower()
        )

        if "text/html" not in content_type:

            print(
                f"[SKIP NON-HTML] "
                f"{url}"
            )

            return None

        return response.text

    except Exception as e:

        print(
            f"[FETCH ERROR] "
            f"{url}: "
            f"{e}"
        )

        return None


# =========================================================
# 8. EXTRACT INTERNAL LINKS
# =========================================================

def extract_links(
    html_text: str,
    current_url: str,
    prefix: str,
) -> Set[str]:

    soup = BeautifulSoup(
        html_text,
        "html.parser",
    )

    urls = set()

    for anchor in soup.find_all(
        "a",
        href=True,
    ):

        href = anchor.get(
            "href"
        )

        if not href:
            continue

        # Ignore javascript/mail/etc.
        href_lower = (
            href.strip().lower()
        )

        if href_lower.startswith(
            (
                "javascript:",
                "mailto:",
                "tel:",
                "#",
            )
        ):

            continue

        absolute_url = urljoin(
            current_url,
            href,
        )

        normalized = normalize_url(
            absolute_url
        )

        if should_keep_url(
            normalized,
            prefix,
        ):

            urls.add(
                normalized
            )

    return urls


# =========================================================
# 9. PAGE CONTENT VALIDATION
# =========================================================

def looks_like_content_page(
    html_text: str,
) -> bool:

    if not html_text:
        return False

    soup = BeautifulSoup(
        html_text,
        "html.parser",
    )

    # Remove junk
    for element in soup.find_all(
        [
            "script",
            "style",
            "noscript",
            "svg",
        ]
    ):

        element.decompose()

    text = soup.get_text(
        " ",
        strip=True,
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return (
        len(text)
        >= MIN_PAGE_TEXT_LENGTH
    )


# =========================================================
# 10. CRAWL ONE DESTINATION
# =========================================================

def crawl_destination(
    destination: str,
    seed_url: str,
    prefix: str,
    robots,
) -> Set[str]:

    print()
    print(
        "=================================================="
    )

    print(
        f"[DESTINATION] "
        f"{destination}"
    )

    print(
        f"[SEED] "
        f"{seed_url}"
    )

    print(
        f"[PREFIX] "
        f"{prefix}"
    )

    print(
        "=================================================="
    )

    seed_url = normalize_url(
        seed_url
    )

    # -----------------------------------------------------
    # BFS queue
    #
    # (URL, depth)
    # -----------------------------------------------------

    queue = deque(
        [
            (
                seed_url,
                0,
            )
        ]
    )

    visited = set()

    valid_urls = set()

    while queue:

        url, depth = (
            queue.popleft()
        )

        # -------------------------------------------------
        # Already processed
        # -------------------------------------------------

        if url in visited:
            continue

        # -------------------------------------------------
        # Limit
        # -------------------------------------------------

        if (
            len(valid_urls)
            >= MAX_URLS_PER_DESTINATION
        ):

            print(
                f"[LIMIT] "
                f"{destination} reached "
                f"{MAX_URLS_PER_DESTINATION}"
            )

            break

        visited.add(
            url
        )

        print(
            f"[{destination}] "
            f"depth={depth} "
            f"{url}"
        )

        # -------------------------------------------------
        # Fetch
        # -------------------------------------------------

        html_text = fetch_page(
            url,
            robots,
        )

        if not html_text:
            continue

        # -------------------------------------------------
        # IMPORTANT:
        #
        # Seed page is also added here.
        # -------------------------------------------------

        if looks_like_content_page(
            html_text
        ):

            valid_urls.add(
                url
            )

            print(
                f"    [KEEP] "
                f"{len(valid_urls)}"
            )

        else:

            print(
                "    [SKIP THIN]"
            )

        # -------------------------------------------------
        # Don't discover deeper links
        # -------------------------------------------------

        if depth >= MAX_DEPTH:
            continue

        # -------------------------------------------------
        # Find next links
        # -------------------------------------------------

        links = extract_links(
            html_text,
            url,
            prefix,
        )

        print(
            f"    Found "
            f"{len(links)} "
            f"candidate links"
        )

        for link in sorted(
            links
        ):

            if link in visited:
                continue

            queue.append(
                (
                    link,
                    depth + 1,
                )
            )

        time.sleep(
            REQUEST_DELAY
        )

    print()
    print(
        f"[DONE] "
        f"{destination}: "
        f"{len(valid_urls)} URLs"
    )

    return valid_urls


# =========================================================
# 11. CRAWL ALL DESTINATIONS
# =========================================================

def crawl_all(
    robots,
) -> Dict[str, Set[str]]:

    # URL -> destinations
    all_urls: Dict[
        str,
        Set[str],
    ] = {}

    for destination, config in (
        DESTINATIONS.items()
    ):

        urls = crawl_destination(
            destination=destination,

            seed_url=(
                config["seed"]
            ),

            prefix=(
                config["prefix"]
            ),

            robots=robots,
        )

        for url in urls:

            all_urls.setdefault(
                url,
                set(),
            ).add(
                destination
            )

        time.sleep(
            1
        )

    return all_urls


# =========================================================
# 12. PRINT RESULTS
# =========================================================

def print_results(
    all_urls: Dict[str, Set[str]],
) -> None:

    counts = {
        destination: 0
        for destination
        in DESTINATIONS
    }

    for url, destinations in (
        all_urls.items()
    ):

        for destination in destinations:

            if destination in counts:

                counts[
                    destination
                ] += 1

    print()
    print(
        "=================================================="
    )

    print(
        "LOCALVIETNAM RESULT COUNTS"
    )

    print(
        "=================================================="
    )

    for destination in DESTINATIONS:

        print(
            f"{destination:<20}: "
            f"{counts[destination]}"
        )

    print(
        "--------------------------------------------------"
    )

    print(
        f"{'TOTAL UNIQUE':<20}: "
        f"{len(all_urls)}"
    )

    print(
        "=================================================="
    )


# =========================================================
# 13. GET EXISTING DB URLS
# =========================================================

def get_existing_urls(
    db,
) -> Set[str]:

    return {
        normalize_url(
            row[0]
        )
        for row in (
            db.query(
                URLSource.url
            )
            .all()
        )
    }


# =========================================================
# 14. SAVE TO DATABASE
# =========================================================

def save_urls_to_db(
    all_urls: Dict[str, Set[str]],
) -> None:

    if not all_urls:

        print(
            "[DB] No URLs to insert."
        )

        return

    db = SessionLocal()

    inserted = 0
    skipped = 0

    try:

        existing_urls = (
            get_existing_urls(
                db
            )
        )

        print()
        print(
            "=================================================="
        )

        print(
            "SAVING LOCALVIETNAM URLS"
        )

        print(
            "=================================================="
        )

        for url, destinations in (
            sorted(
                all_urls.items()
            )
        ):

            normalized = normalize_url(
                url
            )

            if normalized in existing_urls:

                skipped += 1

                print(
                    f"[SKIP DB] "
                    f"{url}"
                )

                continue

            db.add(
                URLSource(
                    url=normalized,
                    status=URLStatus.PENDING,
                )
            )

            existing_urls.add(
                normalized
            )

            inserted += 1

            print(
                f"[ADD] "
                f"[{', '.join(sorted(destinations))}] "
                f"{normalized}"
            )

        db.commit()

    except Exception:

        db.rollback()

        raise

    finally:

        db.close()

    print()
    print(
        "=================================================="
    )

    print(
        f"[DB] Inserted: "
        f"{inserted}"
    )

    print(
        f"[DB] Existing skipped: "
        f"{skipped}"
    )

    print(
        "=================================================="
    )


# =========================================================
# 15. TEST ROBOTS AGAINST SEEDS
# =========================================================

def test_seed_permissions(
    robots,
) -> bool:

    if robots is None:

        print(
            "[ROBOTS] Permission could not "
            "be established."
        )

        return False

    print()
    print(
        "=================================================="
    )

    print(
        "ROBOTS SEED TEST"
    )

    print(
        "=================================================="
    )

    allowed_any = False

    for destination, config in (
        DESTINATIONS.items()
    ):

        seed_url = normalize_url(
            config["seed"]
        )

        try:

            allowed = robots.can_fetch(
                USER_AGENT,
                seed_url,
            )

        except Exception:

            allowed = False

        print(
            f"{destination:<20}: "
            f"{allowed}"
        )

        if allowed:
            allowed_any = True

    print(
        "=================================================="
    )

    return allowed_any


# =========================================================
# 16. MAIN
# =========================================================

def main():

    print(
        "=================================================="
    )

    print(
        "LOCALVIETNAM TRAVEL CRAWLER"
    )

    print(
        "=================================================="
    )

    print(
        "Destinations:"
    )

    for destination in DESTINATIONS:

        print(
            f" - {destination}"
        )

    print()

    print(
        f"MAX_DEPTH: "
        f"{MAX_DEPTH}"
    )

    print(
        f"MAX_URLS_PER_DESTINATION: "
        f"{MAX_URLS_PER_DESTINATION}"
    )

    print(
        f"KEEP_TRANSPORT_PAGES: "
        f"{KEEP_TRANSPORT_PAGES}"
    )

    print(
        "=================================================="
    )

    # =====================================================
    # STEP 1
    # robots.txt
    # =====================================================

    robots = (
        create_robot_parser()
    )

    # =====================================================
    # STEP 2
    # Check whether the actual seed pages are permitted
    # =====================================================

    allowed_any = (
        test_seed_permissions(
            robots
        )
    )

    if not allowed_any:

        print()
        print(
            "=================================================="
        )

        print(
            "[STOP] No destination seeds "
            "are confirmed crawlable by robots.txt."
        )

        print(
            "No pages were requested."
        )

        print(
            "=================================================="
        )

        return

    # =====================================================
    # STEP 3
    # Crawl
    # =====================================================

    all_urls = crawl_all(
        robots
    )

    # =====================================================
    # STEP 4
    # Results
    # =====================================================

    print_results(
        all_urls
    )

    # =====================================================
    # STEP 5
    # DB
    # =====================================================

    save_urls_to_db(
        all_urls
    )

    # =====================================================
    # DONE
    # =====================================================

    print()
    print(
        "=================================================="
    )

    print(
        "LocalVietnam crawler completed."
    )

    print()

    print(
        "Next:"
    )

    print(
        "process_url_list_to_db()"
    )

    print(
        "=================================================="
    )


# =========================================================
# ENTRY POINT
# =========================================================

if __name__ == "__main__":
    main()