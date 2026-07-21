"""Web scraper module for extracting structured data from web pages.

This module provides functionality to fetch a web page and extract:
- All hyperlinks (with anchor text and URLs)
- All images (with src, alt, and title attributes)
- Page title
- Meta description
- All h1, h2, h3 headings

Security best practices are followed:
- URL validation to prevent SSRF
- Request timeout and redirect limits
- Custom User-Agent header
- Content-Type validation
- Size limits on response content

Example usage:
    from web_scraper import scrape_page
    result = scrape_page("https://example.com")
    print(result["title"])
"""

import re
import sys
import urllib.parse
from dataclasses import dataclass, asdict
from typing import List, Optional, Dict, Any
from html.parser import HTMLParser

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError as e:
    print(f"Required packages missing: {e}. Install with: pip install requests beautifulsoup4", file=sys.stderr)
    sys.exit(1)


# Constants for security and resource limits
DEFAULT_TIMEOUT = 10  # seconds
MAX_REDIRECTS = 5
MAX_CONTENT_SIZE = 10 * 1024 * 1024  # 10 MB
ALLOWED_SCHEMES = {"http", "https"}
USER_AGENT = "WebScraper/1.0 (+https://github.com/example/web-scraper)"


@dataclass
class Link:
    """Represents a hyperlink found on the page."""
    url: str
    text: str
    title: Optional[str] = None


@dataclass
class Image:
    """Represents an image found on the page."""
    src: str
    alt: Optional[str] = None
    title: Optional[str] = None


@dataclass
class Heading:
    """Represents a heading (h1, h2, h3) found on the page."""
    level: int
    text: str


@dataclass
class ScrapedData:
    """Container for all scraped data from a page."""
    url: str
    title: Optional[str]
    meta_description: Optional[str]
    links: List[Link]
    images: List[Image]
    headings: List[Heading]


def validate_url(url: str) -> bool:
    """Validate URL for security and correctness.
    
    Args:
        url: The URL string to validate.
        
    Returns:
        True if URL is valid and uses allowed scheme, False otherwise.
    """
    try:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme.lower() not in ALLOWED_SCHEMES:
            return False
        if not parsed.netloc:
            return False
        # Prevent localhost and private IP access (basic SSRF protection)
        if parsed.hostname in {"localhost", "127.0.0.1", "::1"}:
            return False
        # Additional check for private IP ranges could be added here
        return True
    except Exception:
        return False


def fetch_page(url: str) -> requests.Response:
    """Fetch a web page with security constraints.
    
    Args:
        url: The URL to fetch.
        
    Returns:
        Response object from requests.
        
    Raises:
        ValueError: If URL validation fails.
        requests.RequestException: For network errors, timeouts, etc.
    """
    if not validate_url(url):
        raise ValueError(f"Invalid or disallowed URL: {url}")

    session = requests.Session()
    session.max_redirects = MAX_REDIRECTS
    headers = {"User-Agent": USER_AGENT}

    try:
        response = session.get(
            url,
            headers=headers,
            timeout=DEFAULT_TIMEOUT,
            stream=True,
            allow_redirects=True
        )
        response.raise_for_status()

        # Check content type - only process HTML
        content_type = response.headers.get("Content-Type", "").lower()
        if "text/html" not in content_type:
            raise ValueError(f"Unsupported content type: {content_type}")

        # Limit content size
        content_length = response.headers.get("Content-Length")
        if content_length and int(content_length) > MAX_CONTENT_SIZE:
            raise ValueError(f"Content too large: {content_length} bytes")

        # Read content with size limit
        content = b""
        for chunk in response.iter_content(chunk_size=8192):
            content += chunk
            if len(content) > MAX_CONTENT_SIZE:
                raise ValueError("Content exceeds maximum size limit")
        
        response._content = content  # type: ignore
        return response
    except requests.RequestException as e:
        raise requests.RequestException(f"Failed to fetch {url}: {e}") from e


def parse_html(html: str, base_url: str) -> BeautifulSoup:
    """Parse HTML content with BeautifulSoup.
    
    Args:
        html: Raw HTML string.
        base_url: Base URL for resolving relative links.
        
    Returns:
        BeautifulSoup object.
    """
    return BeautifulSoup(html, "html.parser")


def extract_title(soup: BeautifulSoup) -> Optional[str]:
    """Extract page title from HTML.
    
    Args:
        soup: Parsed BeautifulSoup object.
        
    Returns:
        Title text or None if not found.
    """
    title_tag = soup.find("title")
    return title_tag.get_text(strip=True) if title_tag else None


def extract_meta_description(soup: BeautifulSoup) -> Optional[str]:
    """Extract meta description from HTML.
    
    Checks multiple common meta tag patterns.
    
    Args:
        soup: Parsed BeautifulSoup object.
        
    Returns:
        Description text or None if not found.
    """
    # Standard meta description
    meta = soup.find("meta", attrs={"name": "description"})
    if meta and meta.get("content"):
        return meta["content"].strip()
    
    # Open Graph description
    meta = soup.find("meta", attrs={"property": "og:description"})
    if meta and meta.get("content"):
        return meta["content"].strip()
    
    # Twitter description
    meta = soup.find("meta", attrs={"name": "twitter:description"})
    if meta and meta.get("content"):
        return meta["content"].strip()
    
    return None


def extract_links(soup: BeautifulSoup, base_url: str) -> List[Link]:
    """Extract all hyperlinks from HTML.
    
    Args:
        soup: Parsed BeautifulSoup object.
        base_url: Base URL for resolving relative links.
        
    Returns:
        List of Link objects.
    """
    links = []
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"].strip()
        if not href or href.startswith(("javascript:", "mailto:", "tel:")):
            continue
        
        # Resolve relative URLs
        absolute_url = urllib.parse.urljoin(base_url, href)
        
        # Validate the resolved URL
        if not validate_url(absolute_url):
            continue
            
        text = a_tag.get_text(strip=True)
        title = a_tag.get("title", "").strip() or None
        
        links.append(Link(url=absolute_url, text=text, title=title))
    return links


def extract_images(soup: BeautifulSoup, base_url: str) -> List[Image]:
    """Extract all images from HTML.
    
    Args:
        soup: Parsed BeautifulSoup object.
        base_url: Base URL for resolving relative image sources.
        
    Returns:
        List of Image objects.
    """
    images = []
    for img_tag in soup.find_all("img", src=True):
        src = img_tag["src"].strip()
        if not src:
            continue
            
        # Resolve relative URLs
        absolute_src = urllib.parse.urljoin(base_url, src)
        
        # Validate the resolved URL
        if not validate_url(absolute_src):
            continue
            
        alt = img_tag.get("alt", "").strip() or None
        title = img_tag.get("title", "").strip() or None
        
        images.append(Image(src=absolute_src, alt=alt, title=title))
    return images


def extract_headings(soup: BeautifulSoup) -> List[Heading]:
    """Extract all h1, h2, h3 headings from HTML.
    
    Args:
        soup: Parsed BeautifulSoup object.
        
    Returns:
        List of Heading objects.
    """
    headings = []
    for level in (1, 2, 3):
        for tag in soup.find_all(f"h{level}"):
            text = tag.get_text(strip=True)
            if text:
                headings.append(Heading(level=level, text=text))
    return headings


def scrape_page(url: str) -> ScrapedData:
    """Scrape a web page and extract structured data.
    
    Args:
        url: The URL to scrape.
        
    Returns:
        ScrapedData object containing all extracted information.
        
    Raises:
        ValueError: For invalid URLs or content issues.
        requests.RequestException: For network errors.
    """
    response = fetch_page(url)
    soup = parse_html(response.text, url)
    
    return ScrapedData(
        url=url,
        title=extract_title(soup),
        meta_description=extract_meta_description(soup),
        links=extract_links(soup, url),
        images=extract_images(soup, url),
        headings=extract_headings(soup)
    )


def main() -> None:
    """Command-line interface for the web scraper.
    
    Usage: python web_scraper.py <URL>
    Outputs JSON representation of scraped data.
    """
    import json
    
    if len(sys.argv) != 2:
        print("Usage: python web_scraper.py <URL>", file=sys.stderr)
        sys.exit(1)
    
    url = sys.argv[1]
    
    try:
        data = scrape_page(url)
        # Convert dataclasses to dict for JSON serialization
        result = asdict(data)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    except (ValueError, requests.RequestException) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()