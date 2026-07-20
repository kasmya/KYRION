import sys
import re
from typing import Dict, List, Optional
from urllib.parse import urlparse, urljoin

import requests
from bs4 import BeautifulSoup
from requests.exceptions import RequestException


def scrape_website(url: str, timeout: int = 10) -> Dict[str, Optional[List[str]]]:
    """
    Scrape a webpage and extract hyperlinks, images, title, meta description,
    and headings (h1, h2, h3).

    Args:
        url: The target URL to scrape. Must be a valid HTTP/HTTPS URL.
        timeout: Request timeout in seconds (default 10).

    Returns:
        A dictionary containing:
            - 'links': List of absolute hyperlink URLs (str).
            - 'images': List of absolute image source URLs (str).
            - 'title': Page title string (or None if not found).
            - 'meta_description': Meta description content (or None).
            - 'headings': Dictionary with 'h1', 'h2', 'h3' keys each containing a list of strings.

    Raises:
        ValueError: If the URL is invalid or not HTTP/HTTPS.
        RequestException: For network errors, HTTP errors, or timeouts.
    """
    # Validate URL
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"Invalid URL: {url}. Must include scheme (http/https) and netloc.")
    if parsed.scheme not in ('http', 'https'):
        raise ValueError(f"Invalid URL scheme: {parsed.scheme}. Only http and https are allowed.")

    # Security: limit redirects, set user-agent, timeout
    session = requests.Session()
    session.max_redirects = 10
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                      '(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

    try:
        response = session.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)
    except RequestException as e:
        raise RequestException(f"Failed to fetch {url}: {e}") from e

    # Parse HTML
    soup = BeautifulSoup(response.text, 'html.parser')

    # Initialize result structure
    result: Dict[str, Optional[List[str]]] = {
        'links': [],
        'images': [],
        'title': None,
        'meta_description': None,
        'headings': {'h1': [], 'h2': [], 'h3': []}
    }

    # Extract title
    title_tag = soup.find('title')
    if title_tag and title_tag.string:
        result['title'] = title_tag.string.strip()

    # Extract meta description
    meta_desc = soup.find('meta', attrs={'name': 'description'})
    if meta_desc and meta_desc.get('content'):
        result['meta_description'] = meta_desc['content'].strip()

    # Extract hyperlinks (only href attributes)
    for a_tag in soup.find_all('a', href=True):
        href = a_tag['href']
        # Resolve relative URLs
        absolute_href = urljoin(url, href)
        # Only keep http/https links
        if absolute_href.startswith(('http://', 'https://')):
            result['links'].append(absolute_href)

    # Extract images (src attribute)
    for img_tag in soup.find_all('img', src=True):
        src = img_tag['src']
        absolute_src = urljoin(url, src)
        if absolute_src.startswith(('http://', 'https://')):
            result['images'].append(absolute_src)

    # Extract headings h1, h2, h3
    for level in ['h1', 'h2', 'h3']:
        headings = soup.find_all(level)
        result['headings'][level] = [h.get_text(strip=True) for h in headings if h.get_text(strip=True)]

    return result


def main() -> None:
    """Entry point: accepts a URL as command-line argument and prints scraped data."""
    if len(sys.argv) != 2:
        print("Usage: python scraper.py <URL>")
        sys.exit(1)

    url = sys.argv[1]

    try:
        data = scrape_website(url)
        print(f"Title: {data['title']}")
        print(f"Meta Description: {data['meta_description']}")
        print(f"Links ({len(data['links'])}):")
        for link in data['links'][:10]:  # Show first 10 only
            print(f"  {link}")
        if len(data['links']) > 10:
            print(f"  ... and {len(data['links'])-10} more")
        print(f"Images ({len(data['images'])}):")
        for img in data['images'][:10]:
            print(f"  {img}")
        if len(data['images']) > 10:
            print(f"  ... and {len(data['images'])-10} more")
        print("Headings:")
        for level in ['h1', 'h2', 'h3']:
            print(f"  {level.upper()}: {data['headings'][level]}")
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)
    except RequestException as e:
        print(f"Network/HTTP error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()