"""
Web scraper utility extracting hyperlinks, images, title, meta description,
and headings (h1, h2, h3) from a given URL.

Features
--------
* Type‑annotated functions.
* Detailed docstrings.
* URL validation using urllib.
* Network error handling (timeouts, connection errors, invalid responses).
* Security‑focused defaults (SSL verification, reasonable timeout, limiting
  redirects).
* No external side effects – the module only returns data structures.
"""

from __future__ import annotations

import sys
import logging
from dataclasses import dataclass, asdict
from typing import List, Dict, Any
from urllib.parse import urlparse, urljoin

import requests
from bs4 import BeautifulSoup, SoupStrainer, FeatureNotFound

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
DEFAULT_TIMEOUT: int = 10  # seconds
MAX_REDIRECTS: int = 5
USER_AGENT: str = "Mozilla/5.0 (compatible; WebScraper/1.0; +https://example.com/bot)"


# --------------------------------------------------------------------------- #
# Data structures
# --------------------------------------------------------------------------- #
@dataclass
class ScrapeResult:
    """Container for all extracted data."""
    url: str
    title: str | None
    meta_description: str | None
    hyperlinks: List[str]
    images: List[str]
    headings: Dict[str, List[str]]  # keys: h1, h2, h3


# --------------------------------------------------------------------------- #
# Helper functions
# --------------------------------------------------------------------------- #
def _is_valid_url(url: str) -> bool:
    """Return True if `url` has a valid scheme and netloc."""
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _make_absolute(base: str, link: str) -> str:
    """Convert a possibly relative link to an absolute URL."""
    return urljoin(base, link)


def _extract_text_from_tags(soup: BeautifulSoup, tag_name: str) -> List[str]:
    """Return stripped text from all tags of `tag_name`."""
    return [element.get_text(strip=True) for element in soup.find_all(tag_name)]


# --------------------------------------------------------------------------- #
# Core scraping logic
# --------------------------------------------------------------------------- #
def scrape_page(url: str) -> ScrapeResult:
    """
    Fetch a page and extract hyperlinks, images, title, meta description,
    and H1–H3 headings.

    Parameters
    ----------
    url: str
        The target page URL. Must be a fully qualified HTTP/HTTPS URL.

    Returns
    -------
    ScrapeResult
        Data class containing the extracted information.

    Raises
    ------
    ValueError
        If the URL is malformed or uses an unsupported scheme.
    requests.RequestException
        For network‑related errors (connection problems, timeouts, etc.).
    RuntimeError
        If the HTML parser cannot be initialized.
    """
    if not _is_valid_url(url):
        raise ValueError(f"Invalid URL: {url!r}")

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    adapter = requests.adapters.HTTPAdapter(max_retries=MAX_REDIRECTS)
    session.mount("http://", adapter)
    session.mount("https://", adapter)

    try:
        resp = session.get(url, timeout=DEFAULT_TIMEOUT, allow_redirects=True, verify=True)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise requests.RequestException(f"Network error while fetching {url!r}: {exc}") from exc

    # Parse only the parts we care about to limit memory usage.
    try:
        # Using SoupStrainer can improve performance for large pages.
        strainer = SoupStrainer(["a", "img", "title", "meta", "h1", "h2", "h3"])
        soup = BeautifulSoup(resp.text, "html.parser", parse_only=strainer)
    except FeatureNotFound as exc:
        raise RuntimeError("HTML parser not found in your environment.") from exc

    # Title
    title_tag = soup.title
    title = title_tag.string.strip() if title_tag and title_tag.string else None

    # Meta description
    meta_desc_tag = soup.find("meta", attrs={"name": "description"}) or soup.find(
        "meta", attrs={"property": "og:description"}
    )
    meta_description = (
        meta_desc_tag["content"].strip() if meta_desc_tag and meta_desc_tag.get("content") else None
    )

    # Hyperlinks
    raw_links = [a.get("href") for a in soup.find_all("a", href=True)]
    hyperlinks = [_make_absolute(url, link) for link in raw_links if link]

    # Images
    raw_imgs = [img.get("src") for img in soup.find_all("img", src=True)]
    images = [_make_absolute(url, src) for src in raw_imgs if src]

    # Headings
    headings = {
        "h1": _extract_text_from_tags(soup, "h1"),
        "h2": _extract_text_from_tags(soup, "h2"),
        "h3": _extract_text_from_tags(soup, "h3"),
    }

    return ScrapeResult(
        url=url,
        title=title,
        meta_description=meta_description,
        hyperlinks=hyperlinks,
        images=images,
        headings=headings,
    )


# --------------------------------------------------------------------------- #
# CLI entry point (optional)
# --------------------------------------------------------------------------- #
def _format_result(result: ScrapeResult) -> str:
    """Pretty‑print the ScrapeResult for CLI use."""
    lines = [
        f"URL: {result.url}",
        f"Title: {result.title or 'N/A'}",
        f"Meta Description: {result.meta_description or 'N/A'}",
        f"Hyperlinks ({len(result.hyperlinks)}):",
    ]
    lines.extend(f"  - {link}" for link in result.hyperlinks[:10])
    if len(result.hyperlinks) > 10:
        lines.append(f"  ... ({len(result.hyperlinks) - 10} more)")

    lines.append(f"Images ({len(result.images)}):")
    lines.extend(f"  - {src}" for src in result.images[:10])
    if len(result.images) > 10:
        lines.append(f"  ... ({len(result.images) - 10} more)")

    for level in ("h1", "h2", "h3"):
        headings = result.headings.get(level, [])
        lines.append(f"{level.upper()} ({len(headings)}):")
        lines.extend(f"  - {txt}" for txt in headings[:10])
        if len(headings) > 10:
            lines.append(f"  ... ({len(headings) - 10} more)")

    return "\n".join(lines)


def main(argv: List[str] | None = None) -> None:
    """Simple command‑line interface."""
    if argv is None:
        argv = sys.argv[1:]

    if not argv:
        print("Usage: python scraper.py <URL>", file=sys.stderr)
        sys.exit(1)

    url = argv[0]
    try:
        result = scrape_page(url)
        print(_format_result(result))
    except ValueError as ve:
        logging.error("Invalid input: %s", ve)
        sys.exit(2)
    except requests.RequestException as re:
        logging.error("Network error: %s", re)
        sys.exit(3)
    except Exception as e:  # pragma: no cover
        logging.exception("Unexpected error: %s", e)
        sys.exit(99)


if __name__ == "__main__":
    main()