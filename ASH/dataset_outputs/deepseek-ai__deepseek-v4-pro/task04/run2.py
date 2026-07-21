"""
Web scraper module for extracting structured data from a given URL.

Extracts hyperlinks, images, page title, meta description, and heading
elements (h1, h2, h3) from a target web page. Uses only the standard library
and the widely-used `requests` and `beautifulsoup4` packages.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Union
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup, Tag

# Configure module-level logger
logger = logging.getLogger(__name__)


def _is_valid_url(url: str) -> bool:
    """Validate that a URL has an HTTP or HTTPS scheme."""
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"}


def _sanitize_url(base_url: str, href: Optional[str]) -> Optional[str]:
    """
    Safely resolve a potentially relative URL against a base URL.

    Args:
        base_url: The absolute base URL of the page.
        href: A raw hyperlink reference (can be relative or absolute).

    Returns:
        An absolute URL string, or None if the input is empty or invalid.
    """
    if not href:
        return None
    # Strip leading/trailing whitespace
    href = href.strip()
    if not href:
        return None
    try:
        absolute = urljoin(base_url, href)
        parsed = urlparse(absolute)
        # Only allow http and https schemes to avoid dangerous protocols
        if parsed.scheme not in ("http", "https"):
            logger.debug("Ignoring non-http(s) url: %s", absolute)
            return None
        return absolute
    except ValueError as exc:
        logger.debug("Invalid URL %s: %s", href, exc)
        return None


def _get_text_safe(tag: Optional[Tag]) -> Optional[str]:
    """Extract and strip text from a BeautifulSoup Tag, returning None if missing."""
    if tag is None:
        return None
    text = tag.get_text(strip=True)
    return text or None


def scrape_page(url: str, timeout: int = 10) -> Dict[str, Union[str, List[str]]]:
    """
    Scrape a web page and extract structured information.

    Args:
        url: The fully qualified URL of the web page to scrape.
        timeout: Request timeout in seconds. Defaults to 10.

    Returns:
        A dictionary containing the following keys:
            - "title": The page <title> text (or empty string).
            - "meta_description": The content of the meta description tag
              (or empty string).
            - "h1": List of h1 heading texts.
            - "h2": List of h2 heading texts.
            - "h3": List of h3 heading texts.
            - "links": List of absolute hyperlinks found on the page.
            - "images": List of absolute image source URLs found on the page.

    Raises:
        ValueError: If the provided URL is not a valid HTTP/HTTPS URL.
        requests.RequestException: For network or HTTP related errors.
    """
    if not _is_valid_url(url):
        raise ValueError(f"URL must have an http or https scheme: {url}")

    logger.info("Scraping URL: %s", url)

    # Use a session for connection pooling and consistent headers
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (compatible; WebScraper/1.0; "
                "+https://example.com/bot)"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
    )

    try:
        response = session.get(url, timeout=timeout, allow_redirects=True)
        response.raise_for_status()
    except requests.RequestException:
        logger.exception("HTTP request failed for %s", url)
        raise
    finally:
        session.close()

    soup = BeautifulSoup(response.text, "html.parser")

    # --- Title ---
    title_tag = soup.find("title")
    title = _get_text_safe(title_tag) or ""

    # --- Meta description ---
    meta_desc_tag = soup.find("meta", attrs={"name": "description"})
    meta_description = ""
    if meta_desc_tag and meta_desc_tag.get("content"):
        meta_description = meta_desc_tag["content"].strip()

    # --- Headings ---
    h1_texts: List[str] = [
        h.get_text(strip=True) for h in soup.find_all("h1") if h.get_text(strip=True)
    ]
    h2_texts: List[str] = [
        h.get_text(strip=True) for h in soup.find_all("h2") if h.get_text(strip=True)
    ]
    h3_texts: List[str] = [
        h.get_text(strip=True) for h in soup.find_all("h3") if h.get_text(strip=True)
    ]

    # --- Links ---
    links: List[str] = []
    for a_tag in soup.find_all("a", href=True):
        if isinstance(a_tag, Tag):
            absolute = _sanitize_url(url, a_tag.get("href"))
            if absolute:
                links.append(absolute)

    # --- Images ---
    images: List[str] = []
    for img_tag in soup.find_all("img", src=True):
        if isinstance(img_tag, Tag):
            absolute = _sanitize_url(url, img_tag.get("src"))
            if absolute:
                images.append(absolute)

    result: Dict[str, Union[str, List[str]]] = {
        "title": title,
        "meta_description": meta_description,
        "h1": h1_texts,
        "h2": h2_texts,
        "h3": h3_texts,
        "links": links,
        "images": images,
    }

    logger.info("Successfully scraped %s", url)
    return result