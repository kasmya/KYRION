"""
Web scraper module for extracting hyperlinks, images, title, meta description,
and headings (h1, h2, h3) from a given URL.

Uses only the Python standard library and the widely-used 'requests' and
'beautifulsoup4' packages.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Set, Tuple
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


def _is_valid_url(url: str) -> bool:
    """
    Validate that a URL has a scheme and netloc.

    Args:
        url: The URL string to validate.

    Returns:
        True if the URL is valid, False otherwise.
    """
    parsed = urlparse(url)
    return bool(parsed.scheme and parsed.netloc)


def extract_page_data(url: str, timeout: int = 10) -> Dict:
    """
    Extract all required data from a web page.

    Args:
        url: The target URL to scrape.
        timeout: Request timeout in seconds (default 10).

    Returns:
        A dictionary containing:
            - url: The original URL.
            - title: The page title (str or None).
            - meta_description: The meta description content (str or None).
            - headings: dict with keys 'h1', 'h2', 'h3' and list values.
            - links: list of absolute hyperlink URLs.
            - images: list of absolute image source URLs.

    Raises:
        ValueError: If the URL is invalid.
        requests.RequestException: For network/HTTP errors.
    """
    if not _is_valid_url(url):
        raise ValueError(f"Invalid URL provided: {url}")

    try:
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.error("Failed to fetch URL %s: %s", url, exc)
        raise

    soup = BeautifulSoup(response.text, "html.parser")

    title: List[str] = []
    title_tag = soup.find("title")
    if title_tag and title_tag.string:
        title.append(title_tag.string.strip())

    meta_description: List[str] = []
    meta_tag = soup.find("meta", attrs={"name": "description"})
    if meta_tag and meta_tag.get("content"):
        meta_description.append(meta_tag["content"].strip())

    headings: Dict[str, List[str]] = {"h1": [], "h2": [], "h3": []}
    for level in ("h1", "h2", "h3"):
        for tag in soup.find_all(level):
            text = tag.get_text(strip=True)
            if text:
                headings[level].append(text)

    hyperlinks: List[str] = []
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        absolute = urljoin(url, href)
        if _is_valid_url(absolute):
            hyperlinks.append(absolute)

    images: List[str] = []
    for img_tag in soup.find_all("img", src=True):
        src = img_tag["src"]
        absolute = urljoin(url, src)
        if _is_valid_url(absolute):
            images.append(absolute)

    return {
        "url": url,
        "title": title[0] if title else None,
        "meta_description": meta_description[0] if meta_description else None,
        "headings": headings,
        "hyperlinks": hyperlinks,
        "images": images,
    }