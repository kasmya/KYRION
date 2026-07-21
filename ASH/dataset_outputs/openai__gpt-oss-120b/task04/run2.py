"""
web_scraper.py

A lightweight web scraper that extracts key information from a given URL:
- All hyperlinks (`<a href=...>`)
- All image sources (`<img src=...>`)
- Page title
- Meta description
- Headings (`<h1>`, `<h2>`, `<h3>`)

The module uses only the Python standard library together with the widely‑used
`requests` and `beautifulsoup4` packages. It follows security best practices
by validating URLs, using HTTPS verification, setting reasonable timeouts,
and handling errors explicitly.

Example
-------
>>> from web_scraper import scrape
>>> data = scrape("https://example.com")
>>> print(data["title"])
>>> print(data["links"])
"""

from __future__ import annotations

import logging
import sys
import urllib.parse
from typing import Any, Dict, List, Optional

import requests
from bs4 import BeautifulSoup, SoupStrainer

# Configure a module‑level logger
logger = logging.getLogger(__name__)
handler = logging.StreamHandler(sys.stderr)
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.INFO)


class ScraperError(Exception):
    """Base exception for scraper‑related errors."""

    pass


def _validate_url(url: str) -> str:
    """
    Validate and sanitize a URL.

    Parameters
    ----------
    url: str
        The URL to validate.

    Returns
    -------
    str
        The normalized URL.

    Raises
    ------
    ScraperError
        If the URL is malformed or uses an unsupported scheme.
    """
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ScraperError(f"Unsupported URL scheme: {parsed.scheme!r}")
    if not parsed.netloc:
        raise ScraperError("URL must have a network location (domain).")
    # Re‑assemble to ensure a clean URL
    cleaned = parsed.geturl()
    logger.debug("Validated URL: %s", cleaned)
    return cleaned


def _fetch_content(url: str, timeout: int = 10) -> str:
    """
    Retrieve the raw HTML content of a URL.

    Parameters
    ----------
    url: str
        The target URL (must be validated beforehand).
    timeout: int, optional
        Seconds to wait for a response before aborting. Defaults to 10.

    Returns
    -------
    str
        The HTML content as text.

    Raises
    ------
    ScraperError
        For network‑related issues, non‑HTML responses, or HTTP errors.
    """
    try:
        response = requests.get(url, timeout=timeout, verify=True, allow_redirects=True)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise ScraperError(f"Failed to fetch {url!r}: {exc}") from exc

    content_type = response.headers.get("Content-Type", "")
    if "text/html" not in content_type:
        raise ScraperError(f"URL does not contain HTML content (Content-Type: {content_type})")
    logger.debug("Fetched %d bytes from %s", len(response.text), url)
    return response.text


def _parse_html(html: str) -> BeautifulSoup:
    """
    Parse HTML text into a BeautifulSoup object.

    Parameters
    ----------
    html: str
        Raw HTML content.

    Returns
    -------
    BeautifulSoup
        Parsed soup using the built‑in HTML parser.
    """
    # Using SoupStrainer to limit parsing to relevant tags improves performance.
    strainer = SoupStrainer(["a", "img", "title", "meta", "h1", "h2", "h3"])
    soup = BeautifulSoup(html, "html.parser", parse_only=strainer)
    logger.debug("HTML parsed into BeautifulSoup")
    return soup


def _extract_title(soup: BeautifulSoup) -> str:
    """
    Extract the page title.

    Parameters
    ----------
    soup: BeautifulSoup
        Parsed HTML soup.

    Returns
    -------
    str
        The title text, or an empty string if not found.
    """
    title_tag = soup.title
    title = title_tag.get_text(strip=True) if title_tag else ""
    logger.debug("Extracted title: %s", title)
    return title


def _extract_meta_description(soup: BeautifulSoup) -> str:
    """
    Extract the meta description content.

    Parameters
    ----------
    soup: BeautifulSoup
        Parsed HTML soup.

    Returns
    -------
    str
        The description text, or an empty string if not found.
    """
    meta_tag = soup.find("meta", attrs={"name": "description"})
    description = meta_tag["content"].strip() if meta_tag and meta_tag.get("content") else ""
    logger.debug("Extracted meta description: %s", description)
    return description


def _extract_links(soup: BeautifulSoup, base_url: str) -> List[str]:
    """
    Extract all hyperlink URLs from the page.

    Parameters
    ----------
    soup: BeautifulSoup
        Parsed HTML soup.
    base_url: str
        Base URL to resolve relative links.

    Returns
    -------
    List[str]
        A list of absolute URLs.
    """
    links: List[str] = []
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        absolute = urllib.parse.urljoin(base_url, href)
        links.append(absolute)
    logger.debug("Extracted %d hyperlinks", len(links))
    return links


def _extract_images(soup: BeautifulSoup, base_url: str) -> List[str]:
    """
    Extract all image source URLs from the page.

    Parameters
    ----------
    soup: BeautifulSoup
        Parsed HTML soup.
    base_url: str
        Base URL to resolve relative image URLs.

    Returns
    -------
    List[str]
        A list of absolute image URLs.
    """
    images: List[str] = []
    for img_tag in soup.find_all("img", src=True):
        src = img_tag["src"]
        absolute = urllib.parse.urljoin(base_url, src)
        images.append(absolute)
    logger.debug("Extracted %d image sources", len(images))
    return images


def _extract_headings(soup: BeautifulSoup) -> Dict[str, List[str]]:
    """
    Extract text from `<h1>`, `<h2>`, and `<h3>` headings.

    Parameters
    ----------
    soup: BeautifulSoup
        Parsed HTML soup.

    Returns
    -------
    Dict[str, List[str]]
        Mapping of heading level to list of texts, e.g. {"h1": [...], "h2": [...], "h3": [...]}.
    """
    headings: Dict[str, List[str]] = {"h1": [], "h2": [], "h3": []}
    for level in headings.keys():
        for tag in soup.find_all(level):
            text = tag.get_text(strip=True)
            if text:
                headings[level].append(text)
    logger.debug(
        "Extracted headings: h1=%d, h2=%d, h3=%d",
        len(headings["h1"]),
        len(headings["h2"]),
        len(headings["h3"]),
    )
    return headings


def scrape(url: str, timeout: int = 10) -> Dict[str, Any]:
    """
    Scrape a web page for common elements.

    Parameters
    ----------
    url: str
        Target URL to scrape.
    timeout: int, optional
        Network timeout in seconds (default: 10).

    Returns
    -------
    Dict[str, Any]
        Dictionary containing:
        - "title": str
        - "meta_description": str
        - "links": List[str]
        - "images": List[str]
        - "headings": Dict[str, List[str]]

    Raises
    ------
    ScraperError
        If any step of the scraping process fails.
    """
    logger.info("Starting scrape for URL: %s", url)
    cleaned_url = _validate_url(url)
    html = _fetch_content(cleaned_url, timeout=timeout)
    soup = _parse_html(html)

    result: Dict[str, Any] = {
        "title": _extract_title(soup),
        "meta_description": _extract_meta_description(soup),
        "links": _extract_links(soup, cleaned_url),
        "images": _extract_images(soup, cleaned_url),
        "headings": _extract_headings(soup),
    }
    logger.info("Scraping completed for %s", url)
    return result


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Simple web scraper")
    parser.add_argument("url", help="URL of the page to scrape")
    parser.add_argument(
        "--timeout",
        type=int,
        default=10,
        help="Network timeout in seconds (default: 10)",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty‑print JSON output",
    )
    args = parser.parse_args()

    try:
        data = scrape(args.url, timeout=args.timeout)
        if args.pretty:
            print(json.dumps(data, indent=2, ensure_ascii=False))
        else:
            print(json.dumps(data, ensure_ascii=False))
    except ScraperError as exc:
        logger.error("Scraping failed: %s", exc)
        sys.exit(1)