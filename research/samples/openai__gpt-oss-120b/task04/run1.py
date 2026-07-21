"""
web_scraper.py

A minimal web scraper that retrieves the following information from a given URL:

* All hyperlinks (the ``href`` attribute of ``<a>`` tags)
* All images (the ``src`` attribute of ``<img>`` tags)
* The page title
* The meta description (content of ``<meta name="description">``)
* All headings ``<h1>``, ``<h2>`` and ``<h3>``

The module uses only the standard library together with the widely‑used
``requests`` and ``beautifulsoup4`` packages.  It follows security best
practices by:

* Verifying SSL certificates
* Setting a sensible timeout
* Limiting the maximum amount of data downloaded (5 MiB)

Typical usage::

    from web_scraper import scrape_url

    result = scrape_url("https://example.com")
    print(result.title)
    print(result.links)
"""

from __future__ import annotations

import sys
import argparse
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Iterable

import requests
from bs4 import BeautifulSoup, SoupStrainer, Tag

# Configure a module‑level logger
logger = logging.getLogger(__name__)
handler = logging.StreamHandler(sys.stderr)
formatter = logging.Formatter("[%(levelname)s] %(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.INFO)

# ---------------------------------------------------------------------------

_MAX_CONTENT_SIZE = 5 * 1024 * 1024  # 5 MiB
_DEFAULT_TIMEOUT = 10  # seconds
_USER_AGENT = (
    "web-scraper/1.0 (+https://github.com/yourname/web-scraper) "
    "requests/{}".format(requests.__version__)
)


class ScraperError(Exception):
    """Base exception for scraper related errors."""


class ContentTooLargeError(ScraperError):
    """Raised when the downloaded content exceeds the allowed size."""


@dataclass
class ScrapedData:
    """Container for the extracted information of a web page."""

    url: str
    title: Optional[str] = None
    meta_description: Optional[str] = None
    links: List[str] = field(default_factory=list)
    images: List[str] = field(default_factory=list)
    headings: Dict[str, List[str]] = field(default_factory=lambda: {"h1": [], "h2": [], "h3": []})


def _download(url: str) -> str:
    """
    Download the HTML content of *url*.

    The request is performed with SSL verification, a custom User‑Agent,
    a timeout and a size limit.

    Parameters
    ----------
    url: str
        The absolute URL to download.

    Returns
    -------
    str
        The decoded HTML content.

    Raises
    ------
    ScraperError
        If the request fails or the content is too large.
    """
    headers = {"User-Agent": _USER_AGENT}
    try:
        with requests.get(
            url,
            headers=headers,
            timeout=_DEFAULT_TIMEOUT,
            stream=True,
            allow_redirects=True,
            verify=True,
        ) as resp:
            resp.raise_for_status()
            content_chunks: List[bytes] = []
            size = 0
            for chunk in resp.iter_content(chunk_size=8192):
                if not chunk:
                    continue
                size += len(chunk)
                if size > _MAX_CONTENT_SIZE:
                    raise ContentTooLargeError(f"Content size exceeds {_MAX_CONTENT_SIZE} bytes")
                content_chunks.append(chunk)
            raw_content = b"".join(content_chunks)
            encoding = resp.encoding if resp.encoding else "utf-8"
            return raw_content.decode(encoding, errors="replace")
    except requests.RequestException as exc:
        raise ScraperError(f"Failed to download {url!r}: {exc}") from exc
    except ContentTooLargeError:
        raise
    except Exception as exc:  # pragma: no cover
        raise ScraperError(f"Unexpected error while downloading {url!r}: {exc}") from exc


def _extract_title(soup: BeautifulSoup) -> Optional[str]:
    """
    Return the page title if present.

    Parameters
    ----------
    soup: BeautifulSoup
        Parsed HTML document.

    Returns
    -------
    Optional[str]
        The title text or ``None`` if not found.
    """
    title_tag = soup.title
    return title_tag.string.strip() if title_tag and title_tag.string else None


def _extract_meta_description(soup: BeautifulSoup) -> Optional[str]:
    """
    Return the content of the ``<meta name="description">`` tag.

    Parameters
    ----------
    soup: BeautifulSoup
        Parsed HTML document.

    Returns
    -------
    Optional[str]
        The description text or ``None`` if not found.
    """
    tag = soup.find("meta", attrs={"name": "description"})
    if tag and isinstance(tag, Tag):
        return tag.get("content", "").strip() or None
    return None


def _extract_links(soup: BeautifulSoup) -> List[str]:
    """
    Extract all ``href`` attributes from ``<a>`` tags.

    Parameters
    ----------
    soup: BeautifulSoup
        Parsed HTML document.

    Returns
    -------
    List[str]
        List of hyperlink URLs (may be relative).
    """
    links: List[str] = []
    for a in soup.find_all("a", href=True):
        href = a.get("href")
        if href:
            links.append(href.strip())
    return links


def _extract_images(soup: BeautifulSoup) -> List[str]:
    """
    Extract all ``src`` attributes from ``<img>`` tags.

    Parameters
    ----------
    soup: BeautifulSoup
        Parsed HTML document.

    Returns
    -------
    List[str]
        List of image source URLs (may be relative).
    """
    images: List[str] = []
    for img in soup.find_all("img", src=True):
        src = img.get("src")
        if src:
            images.append(src.strip())
    return images


def _extract_headings(soup: BeautifulSoup) -> Dict[str, List[str]]:
    """
    Extract text from ``<h1>``, ``<h2>`` and ``<h3>`` elements.

    Parameters
    ----------
    soup: BeautifulSoup
        Parsed HTML document.

    Returns
    -------
    Dict[str, List[str]]
        Mapping from tag name to a list of heading texts.
    """
    headings: Dict[str, List[str]] = {"h1": [], "h2": [], "h3": []}
    for tag_name in headings.keys():
        for tag in soup.find_all(tag_name):
            text = tag.get_text(separator=" ", strip=True)
            if text:
                headings[tag_name].append(text)
    return headings


def _parse_html(html: str, url: str) -> ScrapedData:
    """
    Parse *html* and extract the required information.

    Parameters
    ----------
    html: str
        The raw HTML content.
    url: str
        The URL the HTML originated from (stored for reference).

    Returns
    -------
    ScrapedData
        Populated data container.
    """
    # Only parse the parts we need to keep memory usage low.
    strainer = SoupStrainer(["title", "meta", "a", "img", "h1", "h2", "h3"])
    soup = BeautifulSoup(html, "html.parser", parse_only=strainer)

    data = ScrapedData(url=url)
    data.title = _extract_title(soup)
    data.meta_description = _extract_meta_description(soup)
    data.links = _extract_links(soup)
    data.images = _extract_images(soup)
    data.headings = _extract_headings(soup)
    return data


def scrape_url(url: str) -> ScrapedData:
    """
    Download *url* and extract hyperlinks, images, title, meta description,
    and ``h1``/``h2``/``h3`` headings.

    Parameters
    ----------
    url: str
        The target URL (must be absolute).

    Returns
    -------
    ScrapedData
        An object containing the extracted information.

    Raises
    ------
    ScraperError
        If any network or parsing error occurs.
    """
    logger.info("Scraping %s", url)
    html = _download(url)
    return _parse_html(html, url)


def _parse_cli_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    """
    Parse command‑line arguments.

    Parameters
    ----------
    argv: Optional[Iterable[str]]
        Argument list to parse; defaults to ``sys.argv[1:]``.

    Returns
    -------
    argparse.Namespace
        Parsed arguments.
    """
    parser = argparse.ArgumentParser(description="Simple web scraper")
    parser.add_argument("url", help="The URL to scrape")
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose (debug) logging",
    )
    return parser.parse_args(argv)


def _configure_logging(verbose: bool) -> None:
    """
    Adjust the log level based on *verbose* flag.

    Parameters
    ----------
    verbose: bool
        If ``True``, set log level to DEBUG.
    """
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)


def main(argv: Optional[Iterable[str]] = None) -> None:
    """
    Entry point for command‑line usage.

    Parameters
    ----------
    argv: Optional[Iterable[str]]
        Custom argument list; defaults to ``sys.argv[1:]``.
    """
    args = _parse_cli_args(argv)
    _configure_logging(args.verbose)

    try:
        result = scrape_url(args.url)
    except ScraperError as exc:
        logger.error("Scraping failed: %s", exc)
        sys.exit(1)

    # Pretty‑print the result
    print("URL:", result.url)
    print("Title:", result.title or "(none)")
    print("Meta description:", result.meta_description or "(none)")
    print("\nLinks:")
    for link in result.links:
        print("  -", link)
    print("\nImages:")
    for img in result.images:
        print("  -", img)
    print("\nHeadings:")
    for level, texts in result.headings.items():
        if texts:
            print(f"  {level.upper()}:")
            for txt in texts:
                print("    -", txt)


if __name__ == "__main__":
    main()