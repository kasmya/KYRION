"""
Web Scraper Module

This module provides functionality to scrape a web page and extract:
- All hyperlinks (resolved to absolute URLs)
- All images (resolved to absolute URLs)
- Page title
- Meta description
- All h1, h2, h3 headings

It uses only the Python standard library (urllib, html.parser) to avoid external dependencies.
Security best practices are followed: timeout, user-agent, URL validation, and SSL verification.
"""

import html.parser
import logging
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# Constants
DEFAULT_TIMEOUT = 10  # seconds
USER_AGENT = "WebScraper/1.0 (+https://example.com/bot)"
ALLOWED_SCHEMES = {"http", "https"}


class ScraperError(Exception):
    """Base exception for scraper errors."""
    pass


class FetchError(ScraperError):
    """Raised when fetching the URL fails."""
    pass


class ParseError(ScraperError):
    """Raised when parsing the HTML fails."""
    pass


class ValidationError(ScraperError):
    """Raised when input validation fails."""
    pass


def validate_url(url: str) -> None:
    """
    Validate that the URL uses an allowed scheme and has a netloc.

    Args:
        url: The URL to validate.

    Raises:
        ValidationError: If the URL is invalid or uses a disallowed scheme.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ALLOWED_SCHEMES:
        raise ValidationError(f"URL scheme '{parsed.scheme}' not allowed. Only {ALLOWED_SCHEMES} are permitted.")
    if not parsed.netloc:
        raise ValidationError("URL must have a network location (domain).")


def fetch_page(url: str, timeout: int = DEFAULT_TIMEOUT) -> str:
    """
    Fetch the HTML content of a page.

    Args:
        url: The URL to fetch.
        timeout: Request timeout in seconds.

    Returns:
        The HTML content as a string.

    Raises:
        FetchError: If the request fails for any reason.
    """
    validate_url(url)

    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    # Create an SSL context that verifies certificates (default behavior)
    context = ssl.create_default_context()

    try:
        with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
            # Check content type is HTML
            content_type = response.headers.get("Content-Type", "")
            if "text/html" not in content_type.lower():
                logger.warning("Content-Type is not text/html: %s", content_type)
            # Decode using charset from headers or fallback to utf-8
            encoding = response.headers.get_content_charset() or "utf-8"
            html_bytes = response.read()
            return html_bytes.decode(encoding, errors="replace")
    except urllib.error.HTTPError as e:
        raise FetchError(f"HTTP error {e.code}: {e.reason}") from e
    except urllib.error.URLError as e:
        raise FetchError(f"URL error: {e.reason}") from e
    except TimeoutError as e:
        raise FetchError(f"Request timed out after {timeout} seconds") from e
    except Exception as e:
        raise FetchError(f"Unexpected error fetching URL: {e}") from e


class ScraperHTMLParser(html.parser.HTMLParser):
    """
    HTML parser that extracts links, images, title, meta description, and headings.
    """

    def __init__(self, base_url: str) -> None:
        super().__init__()
        self.base_url = base_url
        self.links: List[str] = []
        self.images: List[str] = []
        self.title: str = ""
        self.meta_description: str = ""
        self.headings: List[Dict[str, str]] = []  # each dict: {"tag": "h1", "text": "..."}
        self._in_title = False
        self._title_data = []
        self._current_heading_tag: Optional[str] = None
        self._heading_data: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        attrs_dict = dict(attrs)
        tag_lower = tag.lower()

        if tag_lower == "a":
            href = attrs_dict.get("href")
            if href:
                absolute = urljoin(self.base_url, href)
                self.links.append(absolute)

        elif tag_lower == "img":
            src = attrs_dict.get("src")
            if src:
                absolute = urljoin(self.base_url, src)
                self.images.append(absolute)

        elif tag_lower == "title":
            self._in_title = True
            self._title_data = []

        elif tag_lower in ("h1", "h2", "h3"):
            self._current_heading_tag = tag_lower
            self._heading_data = []

        elif tag_lower == "meta":
            # Check for name="description" or property="og:description"
            name = attrs_dict.get("name", "").lower()
            prop = attrs_dict.get("property", "").lower()
            content = attrs_dict.get("content", "")
            if (name == "description" or prop == "og:description") and content and not self.meta_description:
                self.meta_description = content.strip()

    def handle_endtag(self, tag: str) -> None:
        tag_lower = tag.lower()

        if tag_lower == "title":
            self._in_title = False
            self.title = "".join(self._title_data).strip()

        elif tag_lower in ("h1", "h2", "h3") and self._current_heading_tag == tag_lower:
            text = "".join(self._heading_data).strip()
            if text:
                self.headings.append({"tag": tag_lower, "text": text})
            self._current_heading_tag = None
            self._heading_data = []

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._title_data.append(data)
        if self._current_heading_tag:
            self._heading_data.append(data)

    def handle_entityref(self, name: str) -> None:
        # Convert entity references to characters (e.g., &amp; -> &)
        try:
            char = chr(html.entities.name2codepoint[name])
        except KeyError:
            char = f"&{name};"
        self.handle_data(char)

    def handle_charref(self, name: str) -> None:
        # Convert numeric character references (e.g., &#65; -> A)
        try:
            if name.startswith('x'):
                char = chr(int(name[1:], 16))
            else:
                char = chr(int(name))
        except ValueError:
            char = f"&#{name};"
        self.handle_data(char)


def parse_page(html: str, base_url: str) -> Dict[str, object]:
    """
    Parse HTML content and extract required information.

    Args:
        html: The HTML content as a string.
        base_url: The base URL for resolving relative links.

    Returns:
        A dictionary with keys: title, meta_description, headings, links, images.

    Raises:
        ParseError: If parsing fails unexpectedly.
    """
    try:
        parser = ScraperHTMLParser(base_url)
        parser.feed(html)
        parser.close()
    except Exception as e:
        raise ParseError(f"HTML parsing failed: {e}") from e

    return {
        "title": parser.title,
        "meta_description": parser.meta_description,
        "headings": parser.headings,
        "links": parser.links,
        "images": parser.images,
    }


def scrape(url: str, timeout: int = DEFAULT_TIMEOUT) -> Dict[str, object]:
    """
    Scrape a URL and return extracted data.

    Args:
        url: The URL to scrape.
        timeout: Request timeout in seconds.

    Returns:
        Dictionary containing title, meta_description, headings, links, images.

    Raises:
        ScraperError: If any step fails.
    """
    logger.info("Fetching %s", url)
    html = fetch_page(url, timeout=timeout)
    logger.info("Parsing HTML")
    result = parse_page(html, url)
    logger.info("Scraping completed successfully")
    return result


def main() -> None:
    """
    Command-line entry point. Takes a single URL argument and prints JSON output.
    """
    import json

    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <URL>", file=sys.stderr)
        sys.exit(1)

    url = sys.argv[1]
    try:
        data = scrape(url)
        print(json.dumps(data, indent=2, ensure_ascii=False))
    except ScraperError as e:
        logger.error("Scraping failed: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()