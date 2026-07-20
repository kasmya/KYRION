import requests
from bs4 import BeautifulSoup
from typing import Dict, List, Optional, Union
from urllib.parse import urlparse, urljoin
import logging

# Configure logging to avoid output pollution in production
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def scrape_url(url: str) -> Dict[str, Union[str, List[str]]]:
    """
    Scrape a given URL and extract hyperlinks, images, page title,
    meta description, and all headings (h1, h2, h3).

    Args:
        url: The target URL to scrape.

    Returns:
        A dictionary containing:
            - 'title': str, page title (empty string if missing)
            - 'meta_description': str, meta description content (empty if missing)
            - 'hyperlinks': list of str, absolute URLs of all hyperlinks
            - 'images': list of str, absolute URLs of all images
            - 'h1': list of str, text of all <h1> elements
            - 'h2': list of str, text of all <h2> elements
            - 'h3': list of str, text of all <h3> elements

    Raises:
        ValueError: If the URL is invalid (missing scheme or network location).
        requests.exceptions.RequestException: On network issues or non-2xx responses.
    """
    # 1. Validate URL format
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(
            f"Invalid URL: '{url}'. Must include scheme (http/https) and network location."
        )

    # 2. Security: reject non-HTTP/HTTPS schemes to prevent URL::file etc.
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Only http/https URLs are allowed, got: {parsed.scheme}")

    # 3. Prepare request with a common user-agent to avoid basic blocks
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/91.0.4472.124 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }

    # 4. Fetch the page with timeout and redirect following
    try:
        response = requests.get(
            url,
            headers=headers,
            timeout=10,  # seconds
            allow_redirects=True,
            stream=True,  # For checking content type without full download
        )
        # Raise an exception for HTTP error statuses (4xx, 5xx)
        response.raise_for_status()
    except requests.exceptions.Timeout:
        logger.error(f"Request timed out for URL: {url}")
        raise
    except requests.exceptions.ConnectionError as e:
        logger.error(f"Connection error for URL {url}: {e}")
        raise
    except requests.exceptions.HTTPError as e:
        logger.error(f"HTTP error {e.response.status_code} for URL {url}")
        raise
    except requests.exceptions.RequestException as e:
        logger.error(f"Request failed for URL {url}: {e}")
        raise

    # 5. Security: only process HTML content (ignore binary downloads, PDFs, etc.)
    content_type = response.headers.get("Content-Type", "")
    if "text/html" not in content_type and "application/xhtml+xml" not in content_type:
        raise ValueError(
            f"URL does not point to an HTML page. Content-Type: {content_type}"
        )

    # 6. Limit the downloaded content to prevent memory issues (10MB)
    #    We read with iter_content and limit to a max length.
    max_bytes = 10 * 1024 * 1024  # 10 MB
    content = b""
    for chunk in response.iter_content(chunk_size=8192, decode_unicode=False):
        content += chunk
        if len(content) > max_bytes:
            logger.warning(f"Content exceeds {max_bytes} bytes, truncating.")
            break

    # 7. Parse HTML
    soup = BeautifulSoup(content, "html.parser")

    # Base URL for resolving relative links
    base_url = url

    # 8. Extract page title
    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else ""

    # 9. Extract meta description
    meta_desc_tag = soup.find("meta", attrs={"name": "description"})
    meta_description = ""
    if meta_desc_tag and meta_desc_tag.get("content"):
        meta_description = meta_desc_tag["content"].strip()

    # 10. Extract all hyperlinks (<a> with href)
    hyperlinks: List[str] = []
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"].strip()
        # Skip empty, javascript:, mailto:, tel: links, and fragment-only urls
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue
        # Convert to absolute URL
        absolute_url = urljoin(base_url, href)
        # Reject non-HTTP/HTTPS schemes after joining (e.g., ftp, file)
        parsed_href = urlparse(absolute_url)
        if parsed_href.scheme not in ("http", "https", ""):
            continue
        hyperlinks.append(absolute_url)

    # 11. Extract all images (<img> with src)
    images: List[str] = []
    for img_tag in soup.find_all("img", src=True):
        src = img_tag["src"].strip()
        if not src:
            continue
        absolute_src = urljoin(base_url, src)
        parsed_src = urlparse(absolute_src)
        if parsed_src.scheme not in ("http", "https", ""):
            continue
        images.append(absolute_src)

    # 12. Extract headings
    h1_texts: List[str] = [h.get_text(strip=True) for h in soup.find_all("h1") if h.get_text(strip=True)]
    h2_texts: List[str] = [h.get_text(strip=True) for h in soup.find_all("h2") if h.get_text(strip=True)]
    h3_texts: List[str] = [h.get_text(strip=True) for h in soup.find_all("h3") if h.get_text(strip=True)]

    # 13. Assemble result
    result = {
        "title": title,
        "meta_description": meta_description,
        "hyperlinks": hyperlinks,
        "images": images,
        "h1": h1_texts,
        "h2": h2_texts,
        "h3": h3_texts,
    }
    return result


# Example usage (if run as script, demonstrate the function)
if __name__ == "__main__":
    test_url = "https://example.com"
    try:
        data = scrape_url(test_url)
        print(f"Title: {data['title']}")
        print(f"Meta Description: {data['meta_description']}")
        print(f"Number of hyperlinks: {len(data['hyperlinks'])}")
        print(f"Number of images: {len(data['images'])}")
        print(f"H1 headings: {data['h1']}")
        print(f"H2 headings: {data['h2']}")
        print(f"H3 headings: {data['h3']}")
    except Exception as e:
        print(f"Error scraping {test_url}: {e}")