"""Web scraper utility.

Extracts hyperlinks, image sources, page title, meta description,
and headings (h1, h2, h3) from a given URL.

Requirements:
    - requests
    - beautifulsoup4
"""

from __future__ import annotations

import sys
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Tuple
from urllib.parse import urlparse, urljoin

import requests
from bs4 import BeautifulSoup, SoupStrainer

# Configure simple logging (can be replaced or extended by the caller)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Exceptions
# --------------------------------------------------------------------------- #
class ScraperError(Exception):
    """Base exception for scraper-related errors."""


class InvalidURLError(ScraperError):
    """Raised when the supplied URL is syntactically invalid."""


class NetworkError(ScraperError):
    """Raised when a network request fails (timeouts, DNS errors, etc.)."""


# --------------------------------------------------------------------------- #
# Data structures
# --------------------------------------------------------------------------- #
@dataclass
class ScrapeResult:
    """Container for scraped information."""

    url: str
    title: str = ""
    meta_description: str = ""
    hyperlinks: List[str] = field(default_factory=list)
    images: List[str] = field(default_factory=list)
    headings: Dict[str, List[str]] = field(default_factory=lambda: {"h1": [], "h2": [], "h3": []})


# --------------------------------------------------------------------------- #
# Core functionality
# --------------------------------------------------------------------------- #
def _is_valid_url(url: str) -> bool:
    """Very small URL validator – checks scheme and netloc."""
    parsed = urlparse(url)
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def _fetch_html(url: str, timeout: int = 10) -> str:
    """Download HTML content with sane defaults.

    Args:
        url: Target URL.
        timeout: Seconds before the request aborts.

    Returns:
        Raw HTML text.

    Raises:
        NetworkError: For request‑related failures.
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (compatible; ScraperBot/1.0; +https://example.com/bot)"
        )
    }
    try:
        resp = requests.get(
            url,
            headers=headers,
            timeout=timeout,
            allow_redirects=True,
            stream=False,
            verify=True,  # SSL verification on (security best practice)
        )
        resp.raise_for_status()
        # Guard against non‑HTML content
        content_type = resp.headers.get("Content-Type", "")
        if "text/html" not in content_type:
            raise NetworkError(f"URL does not appear to be an HTML page: {content_type}")
        return resp.text
    except requests.RequestException as exc:
        raise NetworkError(str(exc)) from exc


def _make_absolute(base: str, link: str) -> str:
    """Convert possibly relative URL to absolute using the page's base URL."""
    return urljoin(base, link)


def scrape(url: str) -> ScrapeResult:
    """Scrape a web page and return its important components.

    Args:
        url: Fully qualified URL to scrape.

    Returns:
        ScrapeResult instance populated with extracted data.

    Raises:
        InvalidURLError: If `url` lacks a valid scheme/netloc.
        NetworkError: For network‑related problems.
    """
    if not _is_valid_url(url):
        raise InvalidURLError(f"Invalid URL supplied: {url!r}")

    html = _fetch_html(url)

    # Parse only necessary parts to reduce memory overhead
    soup = BeautifulSoup(
        html,
        "html.parser",
        parse_only=SoupStrainer(["a", "img", "title", "meta", "h1", "h2", "h3"]),
    )

    result = ScrapeResult(url=url)

    # Title
    if soup.title and soup.title.string:
        result.title = soup.title.string.strip()

    # Meta description
    meta_desc_tag = soup.find("meta", attrs={"name": "description"})
    if meta_desc_tag and meta_desc_tag.get("content"):
        result.meta_description = meta_desc_tag["content"].strip()

    # Hyperlinks
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"].strip()
        if href:
            result.hyperlinks.append(_make_absolute(url, href))

    # Images
    for img_tag in soup.find_all("img", src=True):
        src = img_tag["src"].strip()
        if src:
            result.images.append(_make_absolute(url, src))

    # Headings
    for level in ("h1", "h2", "h3"):
        for heading in soup.find_all(level):
            text = heading.get_text(separator=" ", strip=True)
            if text:
                result.headings[level].append(text)

    # Deduplicate while preserving order
    result.hyperlinks = list(dict.fromkeys(result.hyperlinks))
    result.images = list(dict.fromkeys(result.images))

    return result


# --------------------------------------------------------------------------- #
# CLI entry point (optional)
# --------------------------------------------------------------------------- #
def _format_result(res: ScrapeResult) -> str:
    """Pretty‑print a ScrapeResult for terminal display."""
    lines: List[str] = [
        f"URL: {res.url}",
        f"Title: {res.title}",
        f"Meta Description: {res.meta_description}",
        "",
        "Headings:",
    ]
    for level in ("h1", "h2", "h3"):
        lines.append(f"  {level.upper()}:")
        for txt in res.headings[level]:
            lines.append(f"    - {txt}")

    lines.append("")
    lines.append("Hyperlinks:")
    for link in res.hyperlinks:
        lines.append(f"  - {link}")

    lines.append("")
    lines.append("Images:")
    for img in res.images:
        lines.append(f"  - {img}")

    return "\n".join(lines)


def main(argv: List[str] | None = None) -> int:
    """Simple command‑line interface.

    Usage:
        python scraper.py <URL>
    """
    if argv is None:
        argv = sys.argv[1:]

    if not argv or len(argv) != 1:
        print("Usage: python scraper.py <URL>", file=sys.stderr)
        return 2

    url = argv[0]
    try:
        result = scrape(url)
        print(_format_result(result))
        return 0
    except ScraperError as exc:
        logger.error("Scraping failed: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())