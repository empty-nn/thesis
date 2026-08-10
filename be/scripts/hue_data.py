# visithue_crawler.py

from typing import Dict, List, Set
from urllib.parse import urljoin, urlparse
import time

import requests
import trafilatura

from langdetect import detect, DetectorFactory, LangDetectException

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import (
    TimeoutException,
    StaleElementReferenceException,
    ElementClickInterceptedException,
)

from db.session import SessionLocal
from db.full_model import URLSource, URLStatus


# =========================================================
# CONFIG
# =========================================================

BASE_URL = "https://visithue.vn"


TARGETS = {
    "history", 
    "heritage",
    "hue-cuisine",
    "destinations",

    "shopping",
    "food-services",
    "accommodation",
}


CATEGORY_URLS = {

    "history": (
        "https://visithue.vn/chuyen-muc/history/"
        "?id=NjR8Y3NkbGRs0"
    ),

    "heritage": (
        "https://visithue.vn/chuyen-muc/heritage/"
        "?id=NjZ8Y3NkbGRs0"
    ),

    "hue-cuisine": (
        "https://visithue.vn/chuyen-muc/hue-cuisine/"
        "?id=Njd8Y3NkbGRs0"
    ),

    "destinations": (
        "https://visithue.vn/chuyen-muc/destination/"
        "?id=Njh8Y3NkbGRs0"
    ),


    # =====================================================
    # THINGS TO DO
    #
    # VisitHue currently does NOT expose these as clean,
    # separately indexed English category URLs in the same
    # way as the 64-68 Discover Hue block.
    #
    # Use these listing endpoints, but run them inside the
    # English browser session + keep final language filter.
    # =====================================================

    "tours": (
        "https://visithue.vn/dieu-can-lam/tour-du-lich/"
        "?id=MTE1MXxjc2RsZGw1"
    ),

    "shopping": (
        "https://visithue.vn/dieu-can-lam/mua-sam/"
        "?id=MTE1Mnxjc2RsZGw1"
    ),

    "food-services": (
        "https://visithue.vn/dieu-can-lam/dich-vu-an-uong/"
        "?id=MTE0OHxjc2RsZGw1"
    ),

    "accommodation": (
        "https://visithue.vn/dieu-can-lam/luu-tru/"
        "?id=MTE0N3xjc2RsZGw1"
    ),

    "transportation": (
        "https://visithue.vn/dieu-can-lam/van-chuyen/"
        "?id=NzR8Y3NkbGRs0"
    ),
}


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/131.0 Safari/537.36"
    )
}


TIMEOUT = 30

PAGE_LOAD_WAIT = 2

VIEW_MORE_WAIT = 1.5

MAX_VIEW_MORE_CLICKS = 100

MIN_LANGUAGE_TEXT_LENGTH = 200


# Make langdetect deterministic
DetectorFactory.seed = 0


http_session = requests.Session()
http_session.headers.update(HEADERS)


# =========================================================
# 1. CREATE SELENIUM DRIVER
# =========================================================

def create_driver() -> webdriver.Chrome:

    options = Options()

    options.add_argument(
        "--headless=new"
    )

    options.add_argument(
        "--window-size=1920,1080"
    )

    options.add_argument(
        "--disable-gpu"
    )

    options.add_argument(
        "--no-sandbox"
    )

    options.add_argument(
        "--disable-dev-shm-usage"
    )

    options.add_argument(
        "--disable-notifications"
    )

    options.add_argument(
        "--disable-popup-blocking"
    )

    options.add_argument(
        "--lang=en-US"
    )

    options.add_argument(
        "--user-agent="
        + HEADERS["User-Agent"]
    )

    driver = webdriver.Chrome(
        options=options
    )

    driver.set_page_load_timeout(
        60
    )

    return driver


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

    # Remove #fragment
    return parsed._replace(
        fragment=""
    ).geturl()


# =========================================================
# 3. CHECK VISITHUE DOMAIN
# =========================================================

def is_visithue_url(
    url: str,
) -> bool:

    if not url:
        return False

    parsed = urlparse(
        url
    )

    return parsed.netloc.lower() in {
        "visithue.vn",
        "www.visithue.vn",
    }


# =========================================================
# 4. CHECK DETAIL URL
# =========================================================

def is_detail_url(
    url: str,
) -> bool:

    """
    VisitHue content/detail pages generally use:

        ?pid=...

    Examples:

        /article-name/?pid=...
        /article-name.html/?pid=...
        /ThingToDo/ShopDetail/?pid=...
        /ThingToDo/RestaurantDetail/?pid=...

    Category/list pages normally use:

        ?id=...
    """

    if not url:
        return False

    url = normalize_url(
        url
    )

    if not is_visithue_url(
        url
    ):
        return False

    parsed = urlparse(
        url
    )

    return "pid=" in parsed.query.lower()


# =========================================================
# 5. EXTRACT DETAIL URLS FROM CURRENT PAGE
# =========================================================

def extract_detail_urls(
    driver: webdriver.Chrome,
) -> Set[str]:

    urls = set()

    anchors = driver.find_elements(
        By.TAG_NAME,
        "a",
    )

    for anchor in anchors:

        try:

            href = anchor.get_attribute(
                "href"
            )

        except StaleElementReferenceException:
            continue

        if not href:
            continue

        href = normalize_url(
            href
        )

        if is_detail_url(
            href
        ):
            urls.add(
                href
            )

    return urls


# =========================================================
# 6. FIND LOAD MORE BUTTON
# =========================================================

def find_load_more_button(
    driver: webdriver.Chrome,
):

    """
    Try common VisitHue labels.

    The site can show Vietnamese or English text.
    """

    keywords = [
        "xem thêm",
        "view more",
        "load more",
    ]

    for keyword in keywords:

        xpath = (
            "//*[self::button or self::a]"
            "[contains("
            "translate(normalize-space(.), "
            "'ABCDEFGHIJKLMNOPQRSTUVWXYZ', "
            "'abcdefghijklmnopqrstuvwxyz'), "
            f"'{keyword}'"
            ")]"
        )

        elements = driver.find_elements(
            By.XPATH,
            xpath,
        )

        for element in elements:

            try:

                if (
                    element.is_displayed()
                    and element.is_enabled()
                ):
                    return element

            except StaleElementReferenceException:
                continue

    return None


# =========================================================
# 7. LOAD ALL ITEMS
# =========================================================

def load_all_items(
    driver: webdriver.Chrome,
) -> None:

    previous_count = -1
    no_change_count = 0

    for click_number in range(
        1,
        MAX_VIEW_MORE_CLICKS + 1,
    ):

        urls = extract_detail_urls(
            driver
        )

        current_count = len(
            urls
        )

        print(
            f"    Current detail URLs: "
            f"{current_count}"
        )

        if current_count == previous_count:
            no_change_count += 1
        else:
            no_change_count = 0

        previous_count = current_count

        button = find_load_more_button(
            driver
        )

        if button is None:

            print(
                "    No more button found."
            )

            break

        try:

            driver.execute_script(
                """
                arguments[0].scrollIntoView({
                    block: 'center'
                });
                """,
                button,
            )

            time.sleep(
                0.3
            )

            try:

                button.click()

            except (
                ElementClickInterceptedException,
                StaleElementReferenceException,
            ):

                button = find_load_more_button(
                    driver
                )

                if button is None:
                    break

                driver.execute_script(
                    "arguments[0].click();",
                    button,
                )

            print(
                f"    Click View More "
                f"#{click_number}"
            )

            time.sleep(
                VIEW_MORE_WAIT
            )

        except Exception as e:

            print(
                f"    [VIEW MORE ERROR] "
                f"{e}"
            )

            break

        # If clicking repeatedly adds nothing,
        # stop instead of infinite loop.
        if no_change_count >= 3:

            print(
                "    No new URLs after "
                "multiple clicks."
            )

            break


# =========================================================
# 8. CRAWL ONE CATEGORY
# =========================================================

def crawl_category(
    driver: webdriver.Chrome,
    category_name: str,
    category_url: str,
) -> Set[str]:

    print()
    print(
        "=================================================="
    )

    print(
        f"[CRAWL] {category_name}"
    )

    print(
        "=================================================="
    )

    try:

        driver.get(
            category_url
        )

    except TimeoutException:

        print(
            "[WARNING] Page timeout, "
            "continue with loaded content."
        )

    time.sleep(
        PAGE_LOAD_WAIT
    )

    # Scroll once to trigger lazy content
    driver.execute_script(
        "window.scrollTo(0, document.body.scrollHeight);"
    )

    time.sleep(
        1
    )

    driver.execute_script(
        "window.scrollTo(0, 0);"
    )

    # Load additional results
    load_all_items(
        driver
    )

    urls = extract_detail_urls(
        driver
    )

    print(
        f"[FOUND] "
        f"{category_name}: "
        f"{len(urls)} URLs"
    )

    return urls


# =========================================================
# 9. DISCOVER URLS FROM ALL TARGET CATEGORIES
# =========================================================

def discover_urls() -> Dict[str, Set[str]]:

    driver = create_driver()

    # URL -> categories
    all_urls: Dict[str, Set[str]] = {}

    try:

        for category_name in TARGETS:

            category_url = CATEGORY_URLS.get(
                category_name
            )

            if not category_url:

                print(
                    f"[WARNING] No URL configured "
                    f"for {category_name}"
                )

                continue

            try:

                urls = crawl_category(
                    driver,
                    category_name,
                    category_url,
                )

            except Exception as e:

                print(
                    f"[CATEGORY ERROR] "
                    f"{category_name}: "
                    f"{e}"
                )

                continue

            for url in urls:

                all_urls.setdefault(
                    url,
                    set(),
                ).add(
                    category_name
                )

            time.sleep(
                1
            )

    finally:

        driver.quit()

    print()
    print(
        "=================================================="
    )

    print(
        f"[DISCOVERY DONE] "
        f"Unique URLs: "
        f"{len(all_urls)}"
    )

    print(
        "=================================================="
    )

    return all_urls


# =========================================================
# 10. EXTRACT TEXT FOR LANGUAGE DETECTION
# =========================================================

def extract_page_text(
    url: str,
) -> str:

    try:

        response = http_session.get(
            url,
            timeout=TIMEOUT,
        )

        response.raise_for_status()

        text = trafilatura.extract(
            response.text,
            url=url,
            output_format="txt",
            include_comments=False,
            include_tables=False,
            include_links=False,
            include_images=False,
            deduplicate=True,
        )

        if not text:
            return ""

        return text.strip()

    except Exception as e:

        print(
            f"[FETCH ERROR] "
            f"{url}: {e}"
        )

        return ""


# =========================================================
# 11. DETECT ENGLISH
# =========================================================

def is_english_page(
    url: str,
) -> bool:

    text = extract_page_text(
        url
    )

    if not text:

        print(
            f"[SKIP EMPTY] {url}"
        )

        return False

    if len(text) < MIN_LANGUAGE_TEXT_LENGTH:

        print(
            f"[SKIP SHORT] "
            f"{len(text)} chars: "
            f"{url}"
        )

        return False

    # First 5000 chars is enough for language detection
    sample = text[
        :5000
    ]

    try:

        language = detect(
            sample
        )

    except LangDetectException:

        print(
            f"[LANG UNKNOWN] "
            f"{url}"
        )

        return False

    print(
        f"[LANG={language}] "
        f"{url}"
    )

    return language == "en"


# =========================================================
# 12. FILTER ENGLISH ONLY
# =========================================================

def filter_english_urls(
    discovered_urls: Dict[str, Set[str]],
) -> List[dict]:

    results = []

    total = len(
        discovered_urls
    )

    print()
    print(
        "=================================================="
    )

    print(
        "FILTERING ENGLISH CONTENT"
    )

    print(
        "=================================================="
    )

    for index, (
        url,
        categories,
    ) in enumerate(
        discovered_urls.items(),
        start=1,
    ):

        print()
        print(
            f"[{index}/{total}] "
            f"Checking..."
        )

        if not is_english_page(
            url
        ):

            print(
                "    [SKIP NON-ENGLISH]"
            )

            continue

        print(
            "    [KEEP ENGLISH]"
        )

        results.append(
            {
                "url": url,
                "categories": sorted(
                    categories
                ),
            }
        )

        # Small delay between requests
        time.sleep(
            0.2
        )

    print()
    print(
        "=================================================="
    )

    print(
        f"[ENGLISH DONE] "
        f"{len(results)}/{total} "
        f"URLs kept"
    )

    print(
        "=================================================="
    )

    return results


# =========================================================
# 13. PRINT RESULT COUNTS
# =========================================================

def print_results(
    results: List[dict],
) -> None:

    category_counts = {
        category: 0
        for category in TARGETS
    }

    print()
    print(
        "=================================================="
    )

    print(
        "ENGLISH URL RESULTS"
    )

    print(
        "=================================================="
    )

    for item in results:

        url = item["url"]

        categories = item[
            "categories"
        ]

        for category in categories:

            category_counts[
                category
            ] += 1

        print(
            f"[{', '.join(categories)}]"
        )

        print(
            f"    {url}"
        )

    print()
    print(
        "=================================================="
    )

    print(
        "COUNTS"
    )

    print(
        "=================================================="
    )

    for category in sorted(
        category_counts
    ):

        print(
            f"{category:<20}: "
            f"{category_counts[category]}"
        )

    print(
        "--------------------------------------------------"
    )

    print(
        f"{'TOTAL UNIQUE':<20}: "
        f"{len(results)}"
    )


# =========================================================
# 14. SAVE TO DATABASE
# =========================================================

def save_urls_to_db(
    results: List[dict],
) -> None:

    db = SessionLocal()

    inserted = 0
    skipped = 0

    try:

        existing_urls = {
            row[0]
            for row in (
                db.query(
                    URLSource.url
                )
                .all()
            )
        }

        print()
        print(
            "=================================================="
        )

        print(
            "SAVING ENGLISH URLS"
        )

        print(
            "=================================================="
        )

        for item in results:

            url = item[
                "url"
            ]

            categories = item[
                "categories"
            ]

            if url in existing_urls:

                skipped += 1

                print(
                    f"[SKIP] "
                    f"[{', '.join(categories)}] "
                    f"{url}"
                )

                continue

            db.add(
                URLSource(
                    url=url,
                    status=URLStatus.PENDING,
                )
            )

            existing_urls.add(
                url
            )

            inserted += 1

            print(
                f"[ADD] "
                f"[{', '.join(categories)}] "
                f"{url}"
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
        f"[DB] Inserted: {inserted}"
    )

    print(
        f"[DB] Existing skipped: "
        f"{skipped}"
    )

    print(
        "=================================================="
    )


# =========================================================
# 15. MAIN
# =========================================================

def main():

    print(
        "=================================================="
    )

    print(
        "VISITHUE ENGLISH TOURISM CRAWLER"
    )

    print(
        "=================================================="
    )

    print(
        "Targets:"
    )

    for target in sorted(
        TARGETS
    ):

        print(
            f"  - {target}"
        )

    print(
        "=================================================="
    )

    # -----------------------------------------------------
    # STEP 1
    # Discover all detail URLs
    # -----------------------------------------------------

    discovered_urls = (
        discover_urls()
    )

    # -----------------------------------------------------
    # STEP 2
    # Keep English content only
    # -----------------------------------------------------

    english_results = (
        filter_english_urls(
            discovered_urls
        )
    )

    # -----------------------------------------------------
    # STEP 3
    # Show results
    # -----------------------------------------------------

    print_results(
        english_results
    )

    # -----------------------------------------------------
    # STEP 4
    # Save PENDING URLs
    # -----------------------------------------------------

    save_urls_to_db(
        english_results
    )

    print()
    print(
        "=================================================="
    )

    print(
        "VisitHue crawler completed."
    )

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