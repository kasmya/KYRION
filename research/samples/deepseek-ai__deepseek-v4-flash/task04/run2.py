import sys
from typing import Optional, Dict, List, Any
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup


class WebScraper:
    """
    A web scraper for extracting common elements from a given URL.

    Attributes:
        timeout (int): Request timeout in seconds.
        user_agent (str): User-Agent header value.
    """

    def __init__(self, timeout: int = 10, user_agent: Optional[str] = None) -> None:
        """
        Initialize the scraper with timeout and optional user-agent.

        Args:
            timeout: Request timeout in seconds.
            user_agent: Custom User-Agent string. If None, a default is used.
        """
        self.timeout = timeout
        self.user_agent = user_agent or (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/91.0.4472.124 Safari/537.36"
        )

    def _validate_url(self, url: str) -> None:
        """
        Validate that the given URL is absolute and has a supported scheme.

        Args:
            url: The URL to validate.

        Raises:
            ValueError: If the URL is invalid, not absolute, or uses unsupported scheme.
        """
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            raise ValueError(f"Invalid URL: '{url}' must be absolute with scheme and netloc.")
        if parsed.scheme not in ("http", "https"):
            raise ValueError(f"Unsupported URL scheme: '{parsed.scheme}'. Only http and https allowed.")

    def extract(self, url: str) -> Dict[str, Any]:
        """
        Extract page title, meta description, all hyperlinks, images, and headings (h1-h3).

        Args:
            url: The target URL to scrape.

        Returns:
            A dictionary with keys:
                - 'success' (bool): Operation success status.
                - 'error' (str, optional): Error message if success is False.
                - 'title' (str): Page title (empty if missing).
                - 'meta_description' (str): Meta description content (empty if missing).
                - 'headings' (dict): Keys 'h1', 'h2', 'h3' each with a list of strings.
                - 'links' (list): List of absolute URLs from <a href>.
                - 'images' (list): List of absolute URLs from <img src>.
        """
        result: Dict[str, Any] = {
            "success": False,
            "title": "",
            "meta_description": "",
            "headings": {"h1": [], "h2": [], "h3": []},
            "links": [],
            "images": [],
        }

        # Validate URL
        try:
            self._validate_url(url)
        except ValueError as e:
            result["error"] = str(e)
            return result

        # Fetch page
        try:
            response = requests.get(
                url,
                headers={"User-Agent": self.user_agent},
                timeout=self.timeout,
            )
            response.raise_for_status()  # Raise HTTPError on bad status (4xx, 5xx)
        except requests.exceptions.Timeout:
            result["error"] = f"Request timed out after {self.timeout} seconds."
            return result
        except requests.exceptions.ConnectionError:
            result["error"] = f"Failed to connect to '{url}'. Check URL or network."
            return result
        except requests.exceptions.HTTPError as e:
            result["error"] = f"HTTP error {e.response.status_code}: {e.response.reason}"
            return result
        except requests.exceptions.RequestException as e:
            result["error"] = f"Request failed: {e}"
            return result

        # Parse HTML
        soup = BeautifulSoup(response.text, "html.parser")

        # Title
        title_tag = soup.find("title")
        result["title"] = title_tag.get_text(strip=True) if title_tag else ""

        # Meta description
        meta_desc = soup.find("meta", attrs={"name": "description"})
        if meta_desc and meta_desc.get("content"):
            result["meta_description"] = meta_desc["content"].strip()

        # Headings
        for tag in ("h1", "h2", "h3"):
            headings = soup.find_all(tag)
            for heading in headings:
                text = heading.get_text(strip=True)
                if text:  # Only include non-empty headings
                    result["headings"][tag].append(text)

        # Hyperlinks - resolve to absolute URLs
        base_uri = url
        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"].strip()
            # Resolve relative URLs
            absolute = requests.compat.urljoin(base_uri, href)
            # Keep only http/https (avoid mailto, javascript, etc.)
            parsed = urlparse(absolute)
            if parsed.scheme in ("http", "https"):
                result["links"].append(absolute)

        # Images
        for img in soup.find_all("img", src=True):
            src = img["src"].strip()
            absolute = requests.compat.urljoin(base_uri, src)
            parsed = urlparse(absolute)
            if parsed.scheme in ("http", "https"):
                result["images"].append(absolute)

        result["success"] = True
        return result


# Example usage (if run as script)
if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python scraper.py <URL>")
        sys.exit(1)

    url = sys.argv[1]
    scraper = WebScraper()
    data = scraper.extract(url)

    if data["success"]:
        print(f"Title: {data['title']}")
        print(f"Meta Description: {data['meta_description']}")
        for level in ("h1", "h2", "h3"):
            print(f"{level.upper()} ({len(data['headings'][level])}): {data['headings'][level]}")
        print(f"Links ({len(data['links'])}): {data['links']}")
        print(f"Images ({len(data['images'])}): {data['images']}")
    else:
        print(f"Error: {data['error']}", file=sys.stderr)
        sys.exit(1)