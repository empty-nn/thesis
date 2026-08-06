import requests
import time
from urllib.parse import urljoin

# Import your queue helper (adjust import path as needed)
from data_building.loaders.url_queue import add_url

WIKIVOYAGE_API = "https://en.wikivoyage.org/w/api.php"
BASE_URL = "https://en.wikivoyage.org/wiki/"
HEADERS = {"User-Agent": "TourismRAGBot/1.0 (empty119.nn@gamil.com)"}
REQUEST_DELAY = 5.0

def api_get(params):
    resp = requests.get(WIKIVOYAGE_API, params=params, headers=HEADERS)
    resp.raise_for_status()
    time.sleep(REQUEST_DELAY)
    print(resp.json())
    return resp.json()

def get_subcategories(category_title):
    subcats = set()
    cmcontinue = None
    while True:
        params = {
            'action': 'query',
            'list': 'categorymembers',
            'cmtitle': f'Category:{category_title}',
            'cmtype': 'subcat',
            'cmlimit': 'max',
            'format': 'json',
        }
        if cmcontinue:
            params['cmcontinue'] = cmcontinue
        data = api_get(params)
        for member in data['query']['categorymembers']:
            subcats.add(member['title'].split(':', 1)[1])
        if 'continue' in data and 'cmcontinue' in data['continue']:
            cmcontinue = data['continue']['cmcontinue']
        else:
            break
    return subcats

def get_pages_in_category(category_title):
    pages = set()
    cmcontinue = None
    while True:
        params = {
            'action': 'query',
            'list': 'categorymembers',
            'cmtitle': f'Category:{category_title}',
            'cmtype': 'page',
            'cmnamespace': '0',
            'cmlimit': 'max',
            'format': 'json',
        }
        if cmcontinue:
            params['cmcontinue'] = cmcontinue
        data = api_get(params)
        for member in data['query']['categorymembers']:
            pages.add(member['title'])
        if 'continue' in data and 'cmcontinue' in data['continue']:
            cmcontinue = data['continue']['cmcontinue']
        else:
            break
    return pages

def collect_and_queue_vietnam_pages():
    """Get all Vietnam article URLs and add them directly to the DB queue."""
    all_titles = set()

    # Pages directly in Category:Vietnam
    all_titles.update(get_pages_in_category("Vietnam"))

    # Pages in subcategories
    subcats = get_subcategories("Vietnam")
    for subcat in subcats:
        print(f"Fetching pages in subcategory: {subcat}")
        all_titles.update(get_pages_in_category(subcat))

    queued_count = 0
    for title in all_titles:
        encoded_title = title.replace(' ', '_')
        url = urljoin(BASE_URL, encoded_title)
        try:
            add_url(url)  # will only insert if not already present
            queued_count += 1
        except Exception as e:
            print(f"Error queuing {url}: {e}")

    print(f"Total articles found: {len(all_titles)}, queued: {queued_count}")

if __name__ == "__main__":
    collect_and_queue_vietnam_pages()