#!/usr/bin/env python3
"""
Web scraper utility.

Extracts:
- Page title
- Meta description
- All hyperlinks (absolute URLs)
- All image sources (absolute URLs)
- Headings (h1, h2, h3) with their text

Usage:
    >>> from scraper import scrape
    >>> result = scrape("https://example.com")
    >>> print(result)
"""

from __future__ import annotations

import sys
import logging
import re
from typing import List, Dict, TypedDict, Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup, SoupStrainer, Tag

# Configure basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ScrapeResult(TypedDict):
    """Typed dict describing the scraper output."""
    url: str
    title: Optional[str]
    meta_description: Optional[str]
    links: List[str]
    images: List[str]
    headings: Dict[str, List[str]]  # keys: h1, h2, h3


def _is_valid_url(url: str) -> bool:
    """Return True if *url* looks like a proper HTTP/HTTPS URL."""
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _fetch(url: str, timeout: int = 10) -> requests.Response:
    """
    Retrieve *url* using a safe request configuration.

    Raises:
        requests.RequestException: for network‑related errors.
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (compatible; ScraperBot/1.0; +https://github.com/yourname/scraper)"
        )
    }
    session = requests.Session()
    # Limit redirects to avoid open redirect loops.
    resp = session.get(
        url,
        headers=headers,
        timeout=timeout,
        verify=True,          # enforce SSL verification
        allow_redirects=True,
        max_redirects=5,
    )
    resp.raise_for_status()
    return resp


def _absolute_url(base: str, link: str) -> str:
    """Resolve *link* relative to *base* and return an absolute URL."""
    return urljoin(base, link)


def scrape(url: str) -> ScrapeResult:
    """
    Scrape *url* and return a dictionary with title, meta description,
    hyperlinks, image URLs and headings (h1‑h3).

    Args:
        url: Target web page URL.

    Returns:
        ScrapeResult containing collected data.

    Raises:
        ValueError: If *url* is not a valid HTTP/HTTPS URL.
        requests.RequestException: For network or HTTP errors.
    """
    if not _is_valid_url(url):
        raise ValueError(f"Invalid URL: {url}")

    try:
        response = _fetch(url)
    except requests.RequestException as exc:
        logger.error("Network error while fetching %s: %s", url, exc)
        raise

    # Parse only the needed parts to reduce memory usage
    parse_only = SoupStrainer(["title", "meta", "a", "img", "h1", "h2", "h3"])
    soup = BeautifulSoup(response.text, "html.parser", parse_only=parse_only)

    # Title
    title_tag = soup.title
    title = title_tag.get_text(strip=True) if isinstance(title_tag, Tag) else None

    # Meta description
    meta_desc_tag = soup.find("meta", attrs={"name": re.compile("^description$", re.I)})
    if not meta_desc_tag:
        meta_desc_tag = soup.find("meta", attrs={"property": re.compile("^og:description$", re.I)})
    meta_description = (
        meta_desc_tag["content"].strip()
        if isinstance(meta_desc_tag, Tag) and meta_desc_tag.has_attr("content")
        else None
    )

    # Hyperlinks
    links: List[str] = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.startswith("#"):
            continue  # skip same‑page anchors
        absolute = _absolute_url(url, href)
        links.append(absolute)

    # Images
    images: List[str] = []
    for img in soup.find_all("img", src=True):
        src = img["src"]
        absolute = _absolute_url(url, src)
        images.append(absolute)

    # Headings
    headings: Dict[str, List[str]] = {"h1": [], "h2": [], "h3": []}
    for level in headings.keys():
        for tag in soup.find_all(level):
            text = tag.get_text(strip=True)
            if text:
                headings[level].append(text)

    return {
        "url": url,
        "title": title,
        "meta_description": meta_description,
        "links": links,
        "images": images,
        "headings": headings,
    }


def _demo() -> None:
    """Simple command‑line demo."""
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <URL>", file=sys.stderr)
        sys.exit(1)

    target_url = sys.argv[1]
    try:
        result = scrape(target_url)
    except Exception as exc:  # pragma: no cover
        logger.error("Failed to scrape: %s", exc)
        sys.exit(1)

    import json
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    _demo()