# danang_fantasticity_crawler.py

from typing import Dict, List, Set
import html
import time

import requests

from db.session import SessionLocal
from db.full_model import URLSource, URLStatus


# =========================================================
# CONFIG
# =========================================================

BASE_URL = "https://danangfantasticity.com"

CATEGORY_API = f"{BASE_URL}/wp-json/wp/v2/categories"
POST_API = f"{BASE_URL}/wp-json/wp/v2/posts"


# Actual English menu category IDs
TARGET_CATEGORIES = {
    "see-do": 13046,
    "eat-drink": 13114,
    "shopping": 13124,
    "stay": 82,
}


# Categories we do NOT want in the RAG database
EXCLUDED_CATEGORY_NAMES = {
    "danang ocop products",
}


REQUEST_DELAY = 0.25
TIMEOUT = 30


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/131.0 Safari/537.36"
    )
}


# =========================================================
# HTTP SESSION
# =========================================================

session = requests.Session()
session.headers.update(HEADERS)


# =========================================================
# 1. FETCH ALL WORDPRESS CATEGORIES
# =========================================================

def fetch_all_categories() -> List[dict]:

    categories = []

    page = 1
    per_page = 100

    while True:

        print(
            f"[CATEGORY] Fetching page {page}"
        )

        response = session.get(
            CATEGORY_API,
            params={
                "page": page,
                "per_page": per_page,
                "hide_empty": False,
            },
            timeout=TIMEOUT,
        )

        # WordPress sometimes returns 400 if page > total pages
        if response.status_code == 400:
            break

        response.raise_for_status()

        items = response.json()

        if not items:
            break

        categories.extend(
            items
        )

        total_pages = int(
            response.headers.get(
                "X-WP-TotalPages",
                "1",
            )
        )

        print(
            f"  -> page {page}/{total_pages}"
        )

        if page >= total_pages:
            break

        page += 1

        time.sleep(
            REQUEST_DELAY
        )

    print(
        f"[CATEGORY] Total categories: "
        f"{len(categories)}"
    )

    return categories


# =========================================================
# 2. BUILD CATEGORY CHILD MAP
# =========================================================

def build_children_map(
    categories: List[dict],
) -> Dict[int, List[int]]:

    children_map = {}

    for category in categories:

        parent_id = category.get(
            "parent",
            0,
        )

        children_map.setdefault(
            parent_id,
            [],
        ).append(
            category["id"]
        )

    return children_map


# =========================================================
# 3. GET ROOT + ALL CHILD CATEGORY IDS
# =========================================================

def get_descendant_category_ids(
    root_id: int,
    categories: List[dict],
) -> Set[int]:

    children_map = build_children_map(
        categories
    )

    result = {
        root_id
    }

    stack = [
        root_id
    ]

    while stack:

        current_id = stack.pop()

        children = children_map.get(
            current_id,
            [],
        )

        for child_id in children:

            if child_id in result:
                continue

            result.add(
                child_id
            )

            stack.append(
                child_id
            )

    return result


# =========================================================
# 4. FIND EXCLUDED CATEGORY IDS
# =========================================================

def get_excluded_category_ids(
    categories: List[dict],
) -> Set[int]:

    excluded_ids = set()

    for category in categories:

        category_name = html.unescape(
            category.get(
                "name",
                "",
            )
        ).strip().lower()

        if category_name not in EXCLUDED_CATEGORY_NAMES:
            continue

        root_id = category["id"]

        descendant_ids = (
            get_descendant_category_ids(
                root_id,
                categories,
            )
        )

        excluded_ids.update(
            descendant_ids
        )

        print(
            f"[EXCLUDE] "
            f"{html.unescape(category.get('name', ''))} "
            f"(root id={root_id}, "
            f"total ids={len(descendant_ids)})"
        )

    return excluded_ids


# =========================================================
# 5. VALIDATE ROOT CATEGORIES
# =========================================================

def validate_target_categories(
    categories: List[dict],
) -> None:

    category_by_id = {
        category["id"]: category
        for category in categories
    }

    print()
    print(
        "=================================================="
    )

    print(
        "ROOT CATEGORY VALIDATION"
    )

    print(
        "=================================================="
    )

    for name, category_id in TARGET_CATEGORIES.items():

        category = category_by_id.get(
            category_id
        )

        if not category:

            print(
                f"[ERROR] "
                f"{name}: "
                f"id={category_id} "
                f"NOT FOUND"
            )

            continue

        category_name = html.unescape(
            category.get(
                "name",
                "",
            )
        )

        print(
            f"{name:<15} "
            f"id={category_id:<6} "
            f"name={category_name!r} "
            f"slug={category.get('slug')!r} "
            f"count={category.get('count', 0)}"
        )


# =========================================================
# 6. PRINT CATEGORY TREE
# =========================================================

def print_category_tree(
    root_id: int,
    categories: List[dict],
    excluded_ids: Set[int] | None = None,
) -> None:

    excluded_ids = (
        excluded_ids
        or set()
    )

    category_map = {
        category["id"]: category
        for category in categories
    }

    children_map = {}

    for category in categories:

        parent = category.get(
            "parent",
            0,
        )

        children_map.setdefault(
            parent,
            [],
        ).append(
            category
        )

    def print_node(
        category_id: int,
        level: int = 0,
    ):

        category = category_map.get(
            category_id
        )

        if not category:
            return

        name = html.unescape(
            category.get(
                "name",
                "",
            )
        )

        excluded_text = ""

        if category_id in excluded_ids:
            excluded_text = " [EXCLUDED]"

        print(
            "  " * level
            + f"- {name} "
            + f"[id={category['id']}, "
            + f"slug={category.get('slug')}, "
            + f"count={category.get('count', 0)}]"
            + excluded_text
        )

        children = children_map.get(
            category_id,
            [],
        )

        children = sorted(
            children,
            key=lambda x: x.get(
                "name",
                "",
            ),
        )

        for child in children:

            print_node(
                child["id"],
                level + 1,
            )

    print_node(
        root_id
    )


# =========================================================
# 7. FETCH POSTS FOR ONE CATEGORY
# =========================================================

def fetch_posts_by_category(
    category_id: int,
) -> List[dict]:

    posts = []

    page = 1
    per_page = 100

    while True:

        response = session.get(
            POST_API,
            params={
                "categories": category_id,
                "page": page,
                "per_page": per_page,

                "_fields": (
                    "id,"
                    "date,"
                    "modified,"
                    "slug,"
                    "link,"
                    "title,"
                    "categories"
                ),
            },
            timeout=TIMEOUT,
        )

        if response.status_code == 400:
            break

        response.raise_for_status()

        items = response.json()

        if not items:
            break

        posts.extend(
            items
        )

        total_pages = int(
            response.headers.get(
                "X-WP-TotalPages",
                "1",
            )
        )

        if page >= total_pages:
            break

        page += 1

        time.sleep(
            REQUEST_DELAY
        )

    return posts


# =========================================================
# 8. ENGLISH URL FILTER
# =========================================================

def is_english_url(
    url: str,
) -> bool:

    if not url:
        return False

    return (
        url.startswith(
            f"{BASE_URL}/en/"
        )
        or url == f"{BASE_URL}/en"
    )


# =========================================================
# 9. GET CLEAN POST TITLE
# =========================================================

def get_post_title(
    post: dict,
) -> str:

    title = (
        post
        .get(
            "title",
            {},
        )
        .get(
            "rendered",
            "",
        )
    )

    return html.unescape(
        title
    ).strip()


# =========================================================
# 10. CHECK IF POST SHOULD BE EXCLUDED
# =========================================================

def is_post_excluded(
    post: dict,
    excluded_category_ids: Set[int],
) -> bool:

    post_category_ids = set(
        post.get(
            "categories",
            [],
        )
    )

    return bool(
        post_category_ids
        & excluded_category_ids
    )


# =========================================================
# 11. CRAWL TARGET CATEGORIES
# =========================================================

def crawl_target_posts(
    categories: List[dict],
    excluded_category_ids: Set[int],
) -> List[dict]:

    all_posts = {}

    print()
    print(
        "=================================================="
    )

    print(
        "CRAWLING TARGET CATEGORIES"
    )

    print(
        "=================================================="
    )

    for source_category, root_id in TARGET_CATEGORIES.items():

        category_ids = (
            get_descendant_category_ids(
                root_id,
                categories,
            )
        )

        original_count = len(
            category_ids
        )

        # Remove OCOP and any other excluded category branches
        category_ids = (
            category_ids
            - excluded_category_ids
        )

        print()
        print(
            f"[{source_category}]"
        )

        print(
            f"  Original categories: "
            f"{original_count}"
        )

        print(
            f"  After exclusions: "
            f"{len(category_ids)}"
        )

        raw_post_matches = 0
        excluded_post_count = 0

        for category_id in sorted(
            category_ids
        ):

            print(
                f"  Fetching category "
                f"{category_id}"
            )

            try:

                posts = (
                    fetch_posts_by_category(
                        category_id
                    )
                )

            except Exception as e:

                print(
                    f"    [ERROR] "
                    f"{category_id}: "
                    f"{e}"
                )

                continue

            print(
                f"    -> "
                f"{len(posts)} posts"
            )

            raw_post_matches += len(
                posts
            )

            for post in posts:

                url = post.get(
                    "link"
                )

                if not url:
                    continue

                # English only
                if not is_english_url(
                    url
                ):
                    continue

                # Important:
                # A post can belong to a normal category AND OCOP.
                #
                # Therefore exclude based on the post's categories
                # as well, not only based on category traversal.
                if is_post_excluded(
                    post,
                    excluded_category_ids,
                ):

                    excluded_post_count += 1

                    print(
                        f"    [SKIP EXCLUDED] "
                        f"{get_post_title(post)}"
                    )

                    continue

                post_id = post.get(
                    "id"
                )

                if post_id is None:
                    continue

                # First time seeing the post
                if post_id not in all_posts:

                    post[
                        "_source_categories"
                    ] = {
                        source_category
                    }

                    all_posts[
                        post_id
                    ] = post

                else:

                    # Same post may belong to multiple
                    # target categories
                    all_posts[
                        post_id
                    ][
                        "_source_categories"
                    ].add(
                        source_category
                    )

        print(
            f"[{source_category}] "
            f"Raw post matches: "
            f"{raw_post_matches}"
        )

        print(
            f"[{source_category}] "
            f"Excluded post matches: "
            f"{excluded_post_count}"
        )

    posts = list(
        all_posts.values()
    )

    print()
    print(
        "=================================================="
    )

    print(
        f"[DONE] Unique English posts "
        f"after exclusions: "
        f"{len(posts)}"
    )

    print(
        "=================================================="
    )

    return posts


# =========================================================
# 12. PRINT DISCOVERED POSTS
# =========================================================

def print_discovered_posts(
    posts: List[dict],
) -> None:

    print()
    print(
        "=================================================="
    )

    print(
        "DISCOVERED POSTS"
    )

    print(
        "=================================================="
    )

    counters = {
        category: 0
        for category in TARGET_CATEGORIES
    }

    for post in posts:

        source_categories = sorted(
            post.get(
                "_source_categories",
                set(),
            )
        )

        title = get_post_title(
            post
        )

        url = post.get(
            "link",
            "",
        )

        for category in source_categories:

            if category in counters:

                counters[
                    category
                ] += 1

        category_text = ", ".join(
            source_categories
        )

        print(
            f"[{category_text}] "
            f"{title}"
        )

        print(
            f"    {url}"
        )

    print()
    print(
        "POST COUNTS:"
    )

    for category, count in counters.items():

        print(
            f"  {category:<15}: "
            f"{count}"
        )

    print(
        f"  {'TOTAL UNIQUE':<15}: "
        f"{len(posts)}"
    )


# =========================================================
# 13. SAVE POSTS INTO URLSource
# =========================================================

def save_posts_to_db(
    posts: List[dict],
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
            "SAVING URLS TO DATABASE"
        )

        print(
            "=================================================="
        )

        for post in posts:

            url = post.get(
                "link"
            )

            if not url:
                continue

            title = get_post_title(
                post
            )

            source_categories = ", ".join(
                sorted(
                    post.get(
                        "_source_categories",
                        set(),
                    )
                )
            )

            # Already in DB
            if url in existing_urls:

                skipped += 1

                print(
                    f"[SKIP DB] "
                    f"[{source_categories}] "
                    f"{title}"
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
                f"[{source_categories}] "
                f"{title}"
            )

        db.commit()

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

    except Exception:

        db.rollback()

        raise

    finally:

        db.close()


# =========================================================
# 14. MAIN
# =========================================================

def main():

    print(
        "=================================================="
    )

    print(
        "Danang Fantasticity crawler"
    )

    print(
        "=================================================="
    )

    print(
        "Included categories:"
    )

    print(
        "  - SEE & DO"
    )

    print(
        "  - EAT & DRINK"
    )

    print(
        "  - SHOPPING"
    )

    print(
        "  - STAY"
    )

    print()

    print(
        "Excluded categories:"
    )

    for excluded_name in (
        EXCLUDED_CATEGORY_NAMES
    ):

        print(
            f"  - {excluded_name}"
        )

    print(
        "=================================================="
    )

    # -----------------------------------------------------
    # STEP 1
    # Fetch full WordPress category taxonomy
    # -----------------------------------------------------

    categories = (
        fetch_all_categories()
    )

    # -----------------------------------------------------
    # STEP 2
    # Validate our manually selected roots
    # -----------------------------------------------------

    validate_target_categories(
        categories
    )

    # -----------------------------------------------------
    # STEP 3
    # Detect categories that should be excluded
    # -----------------------------------------------------

    print()
    print(
        "=================================================="
    )

    print(
        "DETECTING EXCLUDED CATEGORIES"
    )

    print(
        "=================================================="
    )

    excluded_category_ids = (
        get_excluded_category_ids(
            categories
        )
    )

    print(
        f"[EXCLUDE] Total excluded "
        f"category IDs: "
        f"{len(excluded_category_ids)}"
    )

    # -----------------------------------------------------
    # STEP 4
    # Print category trees
    # -----------------------------------------------------

    print()
    print(
        "=================================================="
    )

    print(
        "CATEGORY TREES"
    )

    print(
        "=================================================="
    )

    for name, root_id in (
        TARGET_CATEGORIES.items()
    ):

        print()
        print(
            "------------------------------------------"
        )

        print(
            name.upper()
        )

        print(
            "------------------------------------------"
        )

        print_category_tree(
            root_id,
            categories,
            excluded_category_ids,
        )

    # -----------------------------------------------------
    # STEP 5
    # Crawl posts
    # -----------------------------------------------------

    posts = crawl_target_posts(
        categories,
        excluded_category_ids,
    )

    # -----------------------------------------------------
    # STEP 6
    # Display what will be inserted
    # -----------------------------------------------------

    print_discovered_posts(
        posts
    )

    # -----------------------------------------------------
    # STEP 7
    # Insert URLs into URLSource
    # -----------------------------------------------------

    save_posts_to_db(
        posts
    )

    # -----------------------------------------------------
    # DONE
    # -----------------------------------------------------

    print()
    print(
        "=================================================="
    )

    print(
        "Danang Fantasticity crawler completed."
    )

    print()

    print(
        "Next run:"
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