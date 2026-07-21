"""
Web Scraper Module

This module provides functionality to scrape a web page and extract:
- All hyperlinks
- All images
- Page title
- Meta description
- All h1, h2, h3 headings

It follows security best practices such as URL validation, request timeouts,
and limiting redirects. It uses the widely-used `requests` and `beautifulsoup4`
packages for HTTP and HTML parsing respectively.
"""

import re
import sys
from typing import List, Dict, Optional, Set
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from requests.exceptions import RequestException, Timeout, TooManyRedirects, SSLError

# Constants
DEFAULT_TIMEOUT = 10  # seconds
MAX_REDIRECTS = 5
ALLOWED_SCHEMES = {"http", "https"}
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/91.0.4472.124 Safari/537.36"
)


def validate_url(url: str) -> bool:
    """
    Validate that the URL uses an allowed scheme (http/https) and has a netloc.

    Args:
        url: The URL string to validate.

    Returns:
        True if the URL is valid, False otherwise.
    """
    try:
        parsed = urlparse(url)
        return parsed.scheme in ALLOWED_SCHEMES and bool(parsed.netloc)
    except Exception:
        return False


def fetch_page(url: str) -> Optional[str]:
    """
    Fetch the HTML content of a page with security considerations.

    Args:
        url: The URL to fetch.

    Returns:
        The HTML content as a string if successful, None otherwise.

    Raises:
        ValueError: If the URL is invalid.
    """
    if not validate_url(url):
        raise ValueError(f"Invalid or disallowed URL: {url}")

    headers = {"User-Agent": USER_AGENT}
    try:
        response = requests.get(
            url,
            headers=headers,
            timeout=DEFAULT_TIMEOUT,
            allow_redirects=True,
            max_redirects=MAX_REDIRECTS,
        )
        response.raise_for_status()
        # Ensure we are dealing with HTML content
        content_type = response.headers.get("Content-Type", "")
        if "text/html" not in content_type:
            print(f"Warning: Content-Type is not HTML: {content_type}", file=sys.stderr)
        return response.text
    except Timeout:
        print(f"Error: Request timed out after {DEFAULT_TIMEOUT} seconds", file=sys.stderr)
    except TooManyRedirects:
        print(f"Error: Too many redirects (max {MAX_REDIRECTS})", file=sys.stderr)
    except SSLError as e:
        print(f"SSL Error: {e}", file=sys.stderr)
    except RequestException as e:
        print(f"Request failed: {e}", file=sys.stderr)
    except Exception as e:
        print(f"Unexpected error during fetch: {e}", file=sys.stderr)
    return None


def parse_html(html: str) -> BeautifulSoup:
    """
    Parse HTML string into a BeautifulSoup object.

    Args:
        html: The HTML content as a string.

    Returns:
        A BeautifulSoup object representing the parsed HTML.
    """
    return BeautifulSoup(html, "html.parser")


def extract_links(soup: BeautifulSoup, base_url: str) -> List[str]:
    """
    Extract all hyperlinks (href attributes) from <a> tags, resolved to absolute URLs.

    Args:
        soup: BeautifulSoup object of the page.
        base_url: The base URL of the page for resolving relative links.

    Returns:
        A list of absolute URLs (strings). Duplicates are removed.
    """
    links: Set[str] = set()
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"].strip()
        if href:
            absolute = urljoin(base_url, href)
            # Only keep http/https links
            if urlparse(absolute).scheme in ALLOWED_SCHEMES:
                links.add(absolute)
    return sorted(links)


def extract_images(soup: BeautifulSoup, base_url: str) -> List[str]:
    """
    Extract all image sources (src attributes) from <img> tags, resolved to absolute URLs.

    Args:
        soup: BeautifulSoup object of the page.
        base_url: The base URL of the page for resolving relative image URLs.

    Returns:
        A list of absolute image URLs (strings). Duplicates are removed.
    """
    images: Set[str] = set()
    for img_tag in soup.find_all("img", src=True):
        src = img_tag["src"].strip()
        if src:
            absolute = urljoin(base_url, src)
            if urlparse(absolute).scheme in ALLOWED_SCHEMES:
                images.add(absolute)
    return sorted(images)


def extract_title(soup: BeautifulSoup) -> Optional[str]:
    """
    Extract the page title from the <title> tag.

    Args:
        soup: BeautifulSoup object of the page.

    Returns:
        The title string if found, otherwise None.
    """
    title_tag = soup.find("title")
    if title_tag and title_tag.string:
        return title_tag.string.strip()
    return None


def extract_meta_description(soup: BeautifulSoup) -> Optional[str]:
    """
    Extract the meta description content from <meta name="description"> or
    <meta property="og:description">.

    Args:
        soup: BeautifulSoup object of the page.

    Returns:
        The description string if found, otherwise None.
    """
    # Try standard meta description
    meta = soup.find("meta", attrs={"name": re.compile(r"^description$", re.I)})
    if meta and meta.get("content"):
        return meta["content"].strip()
    # Try Open Graph description
    meta = soup.find("meta", property=re.compile(r"^og:description$", re.I))
    if meta and meta.get("content"):
        return meta["content"].strip()
    # Try Twitter description
    meta = soup.find("meta", attrs={"name": re.compile(r"^twitter:description$", re.I)})
    if meta and meta.get("content"):
        return meta["content"].strip()
    return None


def extract_headings(soup: BeautifulSoup) -> Dict[str, List[str]]:
    """
    Extract all h1, h2, h3 headings.

    Args:
        soup: BeautifulSoup object of the page.

    Returns:
        A dictionary with keys 'h1', 'h2', 'h3' each mapping to a list of heading texts.
    """
    headings = {"h1": [], "h2": [], "h3": []}
    for level in ["h1", "h2", "h3"]:
        for tag in soup.find_all(level):
            text = tag.get_text(strip=True)
            if text:
                headings[level].append(text)
    return headings


def scrape(url: str) -> Optional[Dict]:
    """
    Scrape a web page and extract structured data.

    Args:
        url: The URL to scrape.

    Returns:
        A dictionary with keys: 'url', 'title', 'meta_description', 'headings',
        'links', 'images'. Returns None if scraping fails.
    """
    html = fetch_page(url)
    if html is None:
        return None

    soup = parse_html(html)

    result = {
        "url": url,
        "title": extract_title(soup),
        "meta_description": extract_meta_description(soup),
        "headings": extract_headings(soup),
        "links": extract_links(soup, url),
        "images": extract_images(soup, url),
    }
    return result


if __name__ == "__main__":
    # Simple command-line usage: python scraper.py <URL>
    if len(sys.argv) != 2:
        print("Usage: python scraper.py <URL>", file=sys.stderr)
        sys.exit(1)

    target_url = sys.argv[1]
    data = scrape(target_url)
    if data:
        import json
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print("Scraping failed.", file=sys.stderr)
        sys.exit(1)