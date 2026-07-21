"""
web_scraper.py

A lightweight web scraper that extracts key information from a given URL:
- All hyperlinks (absolute URLs)
- All image sources (absolute URLs)
- Page title
- Meta description
- Headings (h1, h2, h3)

The module provides a high‑level :func:`scrape` function returning a
:class:`ScrapeResult` dataclass.  Errors are reported via :class:`ScraperError`.

Only the Python standard library and the widely‑used third‑party packages
``requests`` and ``beautifulsoup4`` are required.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import requests
from bs4 import BeautifulSoup, SoupStrainer
from urllib.parse import urljoin, urlparse

__all__ = [
    "ScrapeResult",
    "ScraperError",
    "scrape",
]

# Configure a basic logger for debugging; in production this can be overridden.
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ScraperError(Exception):
    """Base exception for all scraper‑related errors."""


@dataclass(frozen=True)
class ScrapeResult:
    """Container for the data extracted from a web page."""
    url: str
    title: Optional[str] = None
    meta_description: Optional[str] = None
    links: List[str] = field(default_factory=list)
    images: List[str] = field(default_factory=list)
    headings: Dict[str, List[str]] = field(default_factory=lambda: {"h1": [], "h2": [], "h3": []})


def _is_valid_http_url(url: str) -> bool:
    """
    Validate that *url* uses HTTP or HTTPS scheme.

    Args:
        url: URL to validate.

    Returns:
        ``True`` if the URL has a supported scheme, else ``False``.
    """
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"}


def fetch_content(url: str, *, timeout: int = 10) -> str:
    """
    Retrieve the raw HTML content of *url*.

    Args:
        url: Target URL.
        timeout: Seconds to wait for a response.

    Returns:
        HTML content as a Unicode string.

    Raises:
        ScraperError: If the request fails or the response is not text/html.
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (compatible; WebScraper/1.0; +https://example.com/bot)"
        )
    }
    try:
        logger.debug("Fetching URL: %s", url)
        response = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
        response.raise_for_status()
    except requests.exceptions.RequestException as exc:
        raise ScraperError(f"Network error while fetching {url!r}: {exc}") from exc

    content_type = response.headers.get("Content-Type", "")
    if "text/html" not in content_type:
        raise ScraperError(f"URL {url!r} did not return HTML (Content-Type: {content_type})")

    try:
        html = response.text
    except UnicodeDecodeError as exc:
        raise ScraperError(f"Failed to decode response from {url!r}: {exc}") from exc

    return html


def parse_html(html: str) -> BeautifulSoup:
    """
    Parse *html* into a :class:`BeautifulSoup` object.

    Args:
        html: Raw HTML string.

    Returns:
        A BeautifulSoup instance using the built‑in ``html.parser``.
    """
    # Using SoupStrainer to limit parsing to relevant tags can improve performance,
    # but for simplicity we parse the whole document.
    return BeautifulSoup(html, "html.parser")


def extract_links(soup: BeautifulSoup, base_url: str) -> List[str]:
    """
    Extract all absolute hyperlinks from *soup*.

    Relative URLs are resolved against *base_url*.
    Only HTTP/HTTPS links are returned.

    Args:
        soup: Parsed HTML.
        base_url: URL of the page (used for resolving relative links).

    Returns:
        List of absolute URLs.
    """
    links: List[str] = []
    for a_tag in soup.find_all("a", href=True):
        href = a_tag.get("href").strip()
        absolute = urljoin(base_url, href)
        if _is_valid_http_url(absolute):
            links.append(absolute)
    return links


def extract_images(soup: BeautifulSoup, base_url: str) -> List[str]:
    """
    Extract all absolute image source URLs from *soup*.

    Relative URLs are resolved against *base_url*.
    Only HTTP/HTTPS links are returned.

    Args:
        soup: Parsed HTML.
        base_url: URL of the page (used for resolving relative links).

    Returns:
        List of absolute image URLs.
    """
    images: List[str] = []
    for img_tag in soup.find_all("img", src=True):
        src = img_tag.get("src").strip()
        absolute = urljoin(base_url, src)
        if _is_valid_http_url(absolute):
            images.append(absolute)
    return images


def extract_title(soup: BeautifulSoup) -> Optional[str]:
    """
    Retrieve the page title.

    Args:
        soup: Parsed HTML.

    Returns:
        Title text or ``None`` if not present.
    """
    title_tag = soup.find("title")
    if title_tag and title_tag.string:
        return title_tag.string.strip()
    return None


def extract_meta_description(soup: BeautifulSoup) -> Optional[str]:
    """
    Retrieve the meta description content.

    Args:
        soup: Parsed HTML.

    Returns:
        Description text or ``None`` if not present.
    """
    meta_tag = soup.find("meta", attrs={"name": "description"})
    if meta_tag and meta_tag.get("content"):
        return meta_tag["content"].strip()
    return None


def extract_headings(soup: BeautifulSoup) -> Dict[str, List[str]]:
    """
    Extract text content of h1, h2, and h3 headings.

    Args:
        soup: Parsed HTML.

    Returns:
        Mapping from heading tag name to a list of stripped texts.
    """
    headings: Dict[str, List[str]] = {"h1": [], "h2": [], "h3": []}
    for level in headings.keys():
        for tag in soup.find_all(level):
            if tag.string:
                headings[level].append(tag.string.strip())
            else:
                # If the heading contains nested tags, get the full text.
                text = tag.get_text(separator=" ", strip=True)
                if text:
                    headings[level].append(text)
    return headings


def scrape(url: str, *, timeout: int = 10) -> ScrapeResult:
    """
    Perform a complete scrape of *url*.

    The function fetches the page, parses the HTML, and extracts the required
    pieces of information.  All URLs are returned as absolute HTTP/HTTPS links.

    Args:
        url: Target page URL.
        timeout: Seconds to wait for the HTTP request.

    Returns:
        :class:`ScrapeResult` containing the extracted data.

    Raises:
        ScraperError: If any step of the scraping process fails.
    """
    if not _is_valid_http_url(url):
        raise ScraperError(f"Provided URL is not a valid HTTP/HTTPS URL: {url!r}")

    html = fetch_content(url, timeout=timeout)
    soup = parse_html(html)

    result = ScrapeResult(
        url=url,
        title=extract_title(soup),
        meta_description=extract_meta_description(soup),
        links=extract_links(soup, base_url=url),
        images=extract_images(soup, base_url=url),
        headings=extract_headings(soup),
    )
    return result


def _format_result(result: ScrapeResult) -> str:
    """
    Helper to format a :class:`ScrapeResult` for pretty printing.

    Args:
        result: The scrape result.

    Returns:
        Human‑readable string.
    """
    lines = [
        f"URL: {result.url}",
        f"Title: {result.title or 'N/A'}",
        f"Meta Description: {result.meta_description or 'N/A'}",
        f"Links ({len(result.links)}):",
    ]
    lines.extend(f"  - {link}" for link in result.links)
    lines.append(f"Images ({len(result.images)}):")
    lines.extend(f"  - {img}" for img in result.images)
    for level, texts in result.headings.items():
        lines.append(f"{level.upper()} headings ({len(texts)}):")
        lines.extend(f"  - {txt}" for txt in texts)
    return "\n".join(lines)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Extract hyperlinks, images, title, meta description, and headings from a web page."
    )
    parser.add_argument("url", help="The URL of the page to scrape.")
    parser.add_argument(
        "--timeout",
        type=int,
        default=10,
        help="Timeout in seconds for the HTTP request (default: 10).",
    )
    args = parser.parse_args()

    try:
        result = scrape(args.url, timeout=args.timeout)
        print(_format_result(result))
    except ScraperError as exc:
        logger.error("Scraping failed: %s", exc)
        sys.exit(1)