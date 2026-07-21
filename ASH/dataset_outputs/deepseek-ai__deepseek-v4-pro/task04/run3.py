"""
Web scraper module that extracts hyperlinks, images, page title, meta description,
and heading elements (h1, h2, h3) from a given URL.

Uses only the Python standard library and the 'requests' and 'beautifulsoup4'
PyPI packages.
"""

import logging
from dataclasses import dataclass, field
from typing import List, Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

# Configure module-level logger
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


@dataclass
class ScrapedData:
    """Data class to hold scraped information from a webpage."""

    url: str
    title: Optional[str] = None
    meta_description: Optional[str] = None
    hyperlinks: List[str] = field(default_factory=list)
    images: List[str] = field(default_factory=list)
    h1_headings: List[str] = field(default_factory=list)
    h2_headings: List[str] = field(default_factory=list)
    h3_headings: List[str] = field(default_factory=list)


def _validate_url(url: str) -> None:
    """
    Validate that the provided URL has an allowed scheme (http/https).

    Args:
        url: The URL string to validate.

    Raises:
        ValueError: If the URL scheme is not http or https.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Disallowed URL scheme: '{parsed.scheme}'. Only HTTP and HTTPS are supported.")


def _make_request(url: str, timeout: int = 10) -> requests.Response:
    """
    Perform a GET request to the specified URL with security best practices.

    Args:
        url: The URL to fetch.
        timeout: Request timeout in seconds.

    Returns:
        The HTTP response object.

    Raises:
        requests.exceptions.RequestException: On any request failure.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; WebScraper/1.0; +https://example.com/bot)"
    }
    try:
        response = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
        response.raise_for_status()
        return response
    except requests.exceptions.RequestException as exc:
        logger.error("Request failed for URL '%s': %s", url, exc)
        raise


def _resolve_url(base_url: str, href: str) -> Optional[str]:
    """
    Safely resolve a relative URL against a base URL and return only valid HTTP/HTTPS URLs.

    Args:
        base_url: The base URL for resolution.
        href: The raw href/src attribute value.

    Returns:
        An absolute URL string, or None if resolution fails or scheme is disallowed.
    """
    try:
        absolute = urljoin(base_url, href)
        parsed = urlparse(absolute)
        if parsed.scheme in ("http", "https"):
            return absolute
        return None
    except Exception:
        return None


def scrape_url(url: str, timeout: int = 10) -> ScrapedData:
    """
    Scrape a webpage and extract hyperlinks, images, title, meta description,
    and h1/h2/h3 headings.

    Args:
        url: The target URL (must use http or https).
        timeout: Request timeout in seconds.

    Returns:
        A ScrapedData instance containing the extracted information.

    Raises:
        ValueError: If the URL scheme is invalid.
        requests.exceptions.RequestException: If the HTTP request fails.
    """
    _validate_url(url)
    response = _make_request(url, timeout=timeout)
    soup = BeautifulSoup(response.text, "html.parser")

    data = ScrapedData(url=url)

    # Extract page title
    title_tag = soup.find("title")
    data.title = title_tag.get_text(strip=True) if title_tag else None

    # Extract meta description
    meta_tag = soup.find("meta", attrs={"name": "description"})
    if meta_tag and meta_tag.get("content"):
        data.meta_description = meta_tag["content"].strip()
    else:
        data.meta_description = None

    # Extract hyperlinks (all <a> tags with href attribute)
    for a_tag in soup.find_all("a", href=True):
        resolved = _resolve_url(url, a_tag["href"])
        if resolved:
            data.hyperlinks.append(resolved)

    # Extract images (all <img> tags with src attribute)
    for img_tag in soup.find_all("img", src=True):
        resolved = _resolve_url(url, img_tag["src"])
        if resolved:
            data.images.append(resolved)

    # Extract headings
    data.h1_headings = [h.get_text(strip=True) for h in soup.find_all("h1")]
    data.h2_headings = [h.get_text(strip=True) for h in soup.find_all("h2")]
    data.h3_headings = [h.get_text(strip=True) for h in soup.find_all("h3")]

    logger.info("Successfully scraped %s: %d links, %d images", url, len(data.hyperlinks), len(data.images))
    return data


# Standalone execution example
if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        print(f"Usage: python {sys.argv[0]} <URL>")
        sys.exit(1)

    target_url = sys.argv[1]
    try:
        result = scrape_url(target_url)
        print(f"Title: {result.title}")
        print(f"Meta Description: {result.meta_description}")
        print(f"Hyperlinks ({len(result.hyperlinks)}):")
        for link in result.hyperlinks[:10]:  # Print first 10 for brevity
            print(f"  - {link}")
        print(f"Images ({len(result.images)}):")
        for img in result.images[:10]:
            print(f"  - {img}")
        print(f"H1 Headings ({len(result.h1_headings)}):")
        for h in result.h1_headings:
            print(f"  - {h}")
        print(f"H2 Headings ({len(result.h2_headings)}):")
        for h in result.h2_headings:
            print(f"  - {h}")
        print(f"H3 Headings ({len(result.h3_headings)}):")
        for h in result.h3_headings:
            print(f"  - {h}")
    except (ValueError, requests.exceptions.RequestException) as e:
        logger.error("Scraping failed: %s", e)
        sys.exit(1)