import requests

DEFAULT_HEADERS = {
    "User-Agent": (
        "VictorTourismRAG/0.1 "
        "(thesis research) Python requests"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,"
        "application/xml;q=0.9,*/*;q=0.8"
    ),
    "Accept-Language": "en,en-US;q=0.9",
    "Accept-Encoding": "gzip, deflate",
}

def fetch_html(
    url: str,
    timeout: int = 30,
) -> str:
    response = requests.get(
        url,
        headers=DEFAULT_HEADERS,
        timeout=timeout,
    )

    response.raise_for_status()

    if not response.encoding:
        response.encoding = response.apparent_encoding

    return response.text