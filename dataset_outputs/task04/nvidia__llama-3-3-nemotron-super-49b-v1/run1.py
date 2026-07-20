import logging
from dataclasses import dataclass
from typing import List, Optional
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import sys

# Configure Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

@dataclass
class ScrapedData:
    """Holds scraped web page data."""
    title: Optional[str]
    meta_description: Optional[str]
    hyperlinks: List[str]
    images: List[str]
    headings: List[str]

def validate_url(url: str) -> bool:
    """Checks if the URL is valid."""
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except ValueError:
        return False

def scrape_url(url: str) -> ScrapedData:
    """
    Scrapes a web page for title, meta description, hyperlinks, images, and headings.

    Args:
    - url (str): The URL of the page to scrape.

    Returns:
    - ScrapedData: A dataclass containing the scraped data.

    Raises:
    - ValueError: If the URL is invalid.
    - requests.RequestException: For network issues.
    """
    if not validate_url(url):
        raise ValueError("Invalid URL")

    try:
        # Send a GET request with a user-agent to mimic a browser
        response = requests.get(url, headers={"User-Agent": "WebScraper/1.0"})
        response.raise_for_status()  # Raise an exception for HTTP errors
    except requests.RequestException as e:
        logger.error(f"Network error: {e}")
        raise

    soup = BeautifulSoup(response.text, 'html.parser')

    # Extract page title
    title = soup.title.string if soup.title else None

    # Extract meta description
    meta_description = soup.find('meta', attrs={'name': 'description'})
    meta_description = meta_description.get('content') if meta_description else None

    # Extract all hyperlinks
    hyperlinks = []
    for link in soup.find_all('a'):
        href = link.get('href')
        if href:
            # Ensure absolute URLs
            hyperlinks.append(urljoin(url, href))

    # Extract all images
    images = [img.get('src') for img in soup.find_all('img') if img.get('src')]

    # Extract all headings
    headings = []
    for header in soup.find_all(['h1', 'h2', 'h3']):
        headings.append(header.text.strip())

    return ScrapedData(title, meta_description, hyperlinks, images, headings)

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python scraper.py <URL>")
        sys.exit(1)

    url = sys.argv[1]
    try:
        data = scrape_url(url)
        print("Scraped Data:")
        print(f"Title: {data.title}")
        print(f"Meta Description: {data.meta_description}")
        print("Hyperlinks:")
        for link in data.hyperlinks:
            print(link)
        print("Images:")
        for img in data.images:
            print(img)
        print("Headings:")
        for heading in data.headings:
            print(heading)
    except Exception as e:
        logger.error(f"Scraping failed: {e}")
        sys.exit(1)