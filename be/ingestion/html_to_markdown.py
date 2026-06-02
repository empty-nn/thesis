# ingestion/html_to_markdown.py

import re
import time
import html as html_lib
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin, urlparse, unquote

import requests
from bs4 import BeautifulSoup, Comment
from markdownify import markdownify as md


# =========================================================
# HEADERS
# =========================================================

DEFAULT_HEADERS = {
    "User-Agent": (
        "VictorTourismRAG/0.1 "
        "(thesis research; contact: your_email@example.com) "
        "Python requests"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "*/*;q=0.8"
    ),
    "Accept-Language": "en,en-US;q=0.9",
    "Accept-Encoding": "gzip, deflate",
}


WIKIMEDIA_HEADERS = {
    "User-Agent": (
        "VictorTourismRAG/0.1 "
        "(thesis research; contact: your_email@example.com) "
        "Python requests"
    ),
    "Accept": "application/json,text/html,*/*;q=0.8",
    "Accept-Language": "en,en-US;q=0.9",
    "Accept-Encoding": "gzip, deflate",
}


# =========================================================
# CLEANING RULES
# =========================================================

UNWANTED_TAGS = [
    "script",
    "style",
    "noscript",
    "iframe",
    "svg",
    "canvas",
    "form",
    "button",
    "input",
    "select",
    "textarea",
    "nav",
    "footer",
    "aside",
]


UNWANTED_CLASS_ID_KEYWORDS = [
    "cookie",
    "banner",
    "advert",
    "ads",
    "subscribe",
    "newsletter",
    "popup",
    "modal",
    "breadcrumb",
    "social",
    "share",
    "sidebar",
    "related",
    "recommend",
    "comment",
    "comments",
    "menu",
    "navigation",
    "footer",

    # MediaWiki / Wikivoyage noise
    "mw-editsection",
    "mw-jump-link",
    "printfooter",
    "catlinks",
    "noprint",
    "metadata",
    "sisterproject",
    "navbox",
    "ambox",
    "hatnote",
]


UNWANTED_EXACT_CLASS_ID = {
    "toc",
    "siteSub",
    "contentSub",
    "jump-to-nav",
}


# =========================================================
# FETCH HTML
# =========================================================

def fetch_html(
    url: str,
    timeout: int = 30,
    debug: bool = False,
) -> str:
    response = requests.get(
        url,
        headers=DEFAULT_HEADERS,
        timeout=timeout,
    )

    response.raise_for_status()

    if debug:
        print(response.text[:3000])

    return response.text


# =========================================================
# WIKIVOYAGE / MEDIAWIKI API
# =========================================================

def is_wikivoyage_url(url: str) -> bool:
    parsed = urlparse(url)
    return "wikivoyage.org" in parsed.netloc.lower()


def extract_wiki_title_from_url(url: str) -> str:
    """
    Example:
    https://en.wikivoyage.org/wiki/Da_Nang -> Da_Nang
    """

    parsed = urlparse(url)
    path = parsed.path

    if "/wiki/" not in path:
        raise ValueError(f"Cannot extract wiki title from URL: {url}")

    title = path.split("/wiki/", 1)[1]
    title = unquote(title)

    return title


def fetch_wikivoyage_page_html(
    title: str,
    sleep_seconds: float = 1.0,
    timeout: int = 30,
) -> str:
    """
    Fetch parsed Wikivoyage HTML using MediaWiki API.
    Better than scraping the normal page URL directly.
    """

    api_url = "https://en.wikivoyage.org/w/api.php"

    time.sleep(sleep_seconds)

    params = {
        "action": "parse",
        "page": title,
        "prop": "text",
        "format": "json",
        "formatversion": "2",
        "redirects": "1",
    }

    response = requests.get(
        api_url,
        headers=WIKIMEDIA_HEADERS,
        params=params,
        timeout=timeout,
    )

    response.raise_for_status()

    data = response.json()

    if "error" in data:
        raise RuntimeError(data["error"])

    return data["parse"]["text"]


def fetch_wikivoyage_page_html_cached(
    title: str,
    cache_dir: str = "cache/wikivoyage",
) -> str:
    """
    Cache Wikivoyage HTML locally to avoid repeated requests.
    """

    cache_path = Path(cache_dir) / f"{title}.html"
    cache_path.parent.mkdir(parents=True, exist_ok=True)

    if cache_path.exists():
        return cache_path.read_text(encoding="utf-8")

    html_text = fetch_wikivoyage_page_html(title)

    cache_path.write_text(
        html_text,
        encoding="utf-8",
    )

    return html_text


# =========================================================
# BEAUTIFULSOUP HELPERS
# =========================================================

def attr_to_text(value) -> str:
    """
    Convert BeautifulSoup attribute value safely.
    id is usually string.
    class is usually list.
    """

    if value is None:
        return ""

    if isinstance(value, list):
        return " ".join(str(v) for v in value)

    return str(value)


def remove_comments(soup: BeautifulSoup) -> None:
    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        comment.extract()


def remove_unwanted_tags(soup: BeautifulSoup) -> None:
    """
    Remove unwanted HTML tags safely.
    """

    for tag_name in UNWANTED_TAGS:
        for tag in list(soup.find_all(tag_name)):
            if tag is not None and tag.parent is not None:
                tag.decompose()


def remove_unwanted_by_class_or_id(soup: BeautifulSoup) -> None:
    """
    Remove noisy blocks by class/id keywords.

    Important:
    First collect tags, then remove them.
    Do not decompose while directly iterating.
    """

    tags_to_remove = []

    for tag in list(soup.find_all(True)):
        if tag is None:
            continue

        if getattr(tag, "attrs", None) is None:
            continue

        tag_id = attr_to_text(tag.get("id")).strip().lower()
        tag_classes_text = attr_to_text(tag.get("class")).strip().lower()
        tag_role = attr_to_text(tag.get("role")).strip().lower()
        tag_aria = attr_to_text(tag.get("aria-label")).strip().lower()

        combined = f"{tag_id} {tag_classes_text} {tag_role} {tag_aria}"

        exact_values = set()

        if tag_id:
            exact_values.add(tag_id)

        tag_classes = tag.get("class")

        if tag_classes:
            for cls in tag_classes:
                exact_values.add(str(cls).strip().lower())

        if any(value in UNWANTED_EXACT_CLASS_ID for value in exact_values):
            tags_to_remove.append(tag)
            continue

        if any(keyword in combined for keyword in UNWANTED_CLASS_ID_KEYWORDS):
            tags_to_remove.append(tag)

    for tag in tags_to_remove:
        if tag is not None and tag.parent is not None:
            tag.decompose()


def remove_visual_nodes(soup: BeautifulSoup) -> None:
    """
    Remove image/media/template-heavy nodes.
    Useful for Wikivoyage/Wikipedia-like pages.
    """

    selectors = [
        "figure",
        ".thumb",
        ".image",
        ".gallery",
        ".mw-default-size",
        ".mw-kartographer-map",
        ".mapframe",
        ".locmap",
        ".infobox",
        ".metadata",
        ".noprint",
    ]

    for selector in selectors:
        for tag in list(soup.select(selector)):
            if tag is not None and tag.parent is not None:
                tag.decompose()


def remove_bad_tables(soup: BeautifulSoup) -> None:
    """
    Remove layout/template tables and climate charts.
    For tourism RAG, these tables often become noisy Markdown.
    """

    for table in list(soup.find_all("table")):
        if table is None or table.parent is None:
            continue

        class_text = attr_to_text(table.get("class")).lower()
        table_text = table.get_text(" ", strip=True).lower()

        should_remove = False

        if any(
            keyword in class_text
            for keyword in [
                "infobox",
                "metadata",
                "ambox",
                "navbox",
                "climate",
                "wikitable",
            ]
        ):
            should_remove = True

        if "climate chart" in table_text:
            should_remove = True

        if "imperial conversion" in table_text:
            should_remove = True

        if "average max. and min. temperatures" in table_text:
            should_remove = True

        if should_remove:
            table.decompose()


def make_links_absolute(
    soup: BeautifulSoup,
    base_url: str,
) -> None:
    for tag in soup.find_all(["a", "img"]):
        attr = "href" if tag.name == "a" else "src"
        value = tag.get(attr)

        if value:
            tag[attr] = urljoin(base_url, value)


def extract_main_content(soup: BeautifulSoup):
    """
    Try to extract the main useful content.
    Includes MediaWiki / Wikivoyage selectors.
    """

    selectors = [
        "#mw-content-text .mw-parser-output",
        "#mw-content-text",
        "main",
        "article",
        "[role='main']",
        "#content",
        "#main",
        ".content",
        ".main-content",
        ".article-content",
        ".post-content",
        ".entry-content",
    ]

    for selector in selectors:
        candidate = soup.select_one(selector)

        if candidate:
            return candidate

    candidates = [
        soup.find("main"),
        soup.find("article"),
        soup.find(attrs={"role": "main"}),
        soup.find(id=re.compile(r"(content|main|article|body)", re.I)),
        soup.find(class_=re.compile(r"(content|main|article|body|post|entry)", re.I)),
    ]

    for candidate in candidates:
        if candidate:
            return candidate

    return soup.body or soup


# =========================================================
# MARKDOWN NORMALIZATION
# =========================================================

def normalize_block_for_dedup(text: str) -> str:
    text = text.lower()
    text = re.sub(r"\[[^\]]+\]\([^)]+\)", "", text)
    text = re.sub(r"[^a-z0-9à-ỹ\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def deduplicate_markdown_blocks(md_text: str) -> str:
    """
    Remove repeated Markdown paragraphs/blocks.
    Also removes near-duplicate blocks with the same beginning.
    """

    if not md_text:
        return ""

    blocks = re.split(r"\n\s*\n", md_text)
    cleaned_blocks = []

    seen_exact = set()
    seen_prefixes = set()

    for block in blocks:
        stripped = block.strip()

        if not stripped:
            continue

        normalized = normalize_block_for_dedup(stripped)

        if not normalized:
            continue

        is_heading = stripped.startswith("#")

        exact_key = normalized
        prefix_key = normalized[:180]

        if not is_heading:
            if exact_key in seen_exact:
                continue

            if len(normalized) > 180 and prefix_key in seen_prefixes:
                continue

        seen_exact.add(exact_key)

        if len(normalized) > 180:
            seen_prefixes.add(prefix_key)

        cleaned_blocks.append(stripped)

    return "\n\n".join(cleaned_blocks).strip()


def normalize_markdown(md_text: str) -> str:
    if not md_text:
        return ""

    md_text = html_lib.unescape(md_text)

    md_text = re.sub(
        r"\[([^\]]+)\]\([^)]+\)",
        r"\1",
        md_text,
    )
    # Remove Markdown image links like [!](url) or ![](url)
    md_text = re.sub(
        r"(?m)^\s*\[!\]\([^)]+\)\s*$",
        "",
        md_text,
    )

    md_text = re.sub(
        r"!\[[^\]]*\]\([^)]+\)",
        "",
        md_text,
    )

    # Remove MediaWiki edit links
    md_text = re.sub(
        r"\[\s*edit\s*\]\([^)]+\)",
        "",
        md_text,
        flags=re.IGNORECASE,
    )

    md_text = re.sub(
        r"\[\s*edit\s*\]",
        "",
        md_text,
        flags=re.IGNORECASE,
    )

    # Remove empty links like [](url)
    md_text = re.sub(
        r"\[\s*\]\([^)]+\)",
        "",
        md_text,
    )

    # Remove common MediaWiki navigation lines and image captions
    noisy_line_patterns = [
        r"^Jump to navigation$",
        r"^Jump to search$",
        r"^From Wikivoyage$",
        r"^The Free Travel Guide$",
        r"^Retrieved from .+$",
        r"^Categories?: .+$",
        r"^Overview from top of .+$",
        r"^Red-shanked douc monkeys$",
        r"^Climate chart .*$",
        r"^Imperial conversion$",
    ]

    cleaned_lines = []

    for line in md_text.splitlines():
        stripped = line.strip()

        if any(
            re.match(pattern, stripped, flags=re.IGNORECASE)
            for pattern in noisy_line_patterns
        ):
            continue

        cleaned_lines.append(line)

    md_text = "\n".join(cleaned_lines)

    # Remove messy Markdown table blocks
    blocks = re.split(r"\n\s*\n", md_text)
    kept_blocks = []

    for block in blocks:
        lines = block.splitlines()
        pipe_lines = [
            line
            for line in lines
            if line.strip().startswith("|")
        ]

        # Usually climate/template tables become large pipe blocks.
        if len(pipe_lines) >= 3:
            continue

        kept_blocks.append(block)

    md_text = "\n\n".join(kept_blocks)

    # Fix heading spacing
    md_text = re.sub(
        r"(?m)^(#{1,6})([^\s#])",
        r"\1 \2",
        md_text,
    )

    # Remove too many spaces
    md_text = re.sub(r"[ \t]{2,}", " ", md_text)

    # Remove spaces before punctuation
    md_text = re.sub(r"\s+([.,;:!?])", r"\1", md_text)

    # Normalize blank lines
    md_text = re.sub(r"\n{3,}", "\n\n", md_text)

    return md_text.strip()


# =========================================================
# HTML -> MARKDOWN
# =========================================================

def html_to_markdown(
    html_text: str,
    source_url: Optional[str] = None,
    extract_main: bool = True,
) -> str:
    try:
        soup = BeautifulSoup(html_text, "lxml")
    except Exception:
        soup = BeautifulSoup(html_text, "html.parser")

    remove_comments(soup)

    if source_url:
        make_links_absolute(soup, source_url)

    content_node = extract_main_content(soup) if extract_main else soup

    remove_visual_nodes(content_node)
    remove_bad_tables(content_node)
    remove_unwanted_tags(content_node)
    remove_unwanted_by_class_or_id(content_node)

    markdown_text = md(
        str(content_node),
        heading_style="ATX",
        bullets="-",
        strip=["span"],
    )

    markdown_text = normalize_markdown(markdown_text)
    markdown_text = deduplicate_markdown_blocks(markdown_text)

    return markdown_text


def url_to_markdown(
    url: str,
    debug: bool = False,
    use_cache: bool = True,
) -> str:
    """
    Convert URL to Markdown.

    For Wikivoyage:
    - use official MediaWiki API
    - use cache
    - avoid normal page scraping
    """

    if is_wikivoyage_url(url):
        title = extract_wiki_title_from_url(url)

        if use_cache:
            html_text = fetch_wikivoyage_page_html_cached(title)
        else:
            html_text = fetch_wikivoyage_page_html(title)

        markdown_text = html_to_markdown(
            html_text,
            source_url=url,
            extract_main=False,
        )

        return markdown_text

    html_text = fetch_html(
        url,
        debug=debug,
    )

    markdown_text = html_to_markdown(
        html_text,
        source_url=url,
        extract_main=True,
    )

    return markdown_text


# =========================================================
# TEST
# =========================================================

if __name__ == "__main__":
    url = "https://en.wikivoyage.org/wiki/Da_Nang"

    markdown_text = url_to_markdown(
        url,
        debug=False,
        use_cache=True,
    )

    print(markdown_text[:8000])