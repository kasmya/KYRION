import logging
from dataclasses import dataclass
from typing import List, Optional
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import argparse

# Configure Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

@dataclass
class ScrapedData:
    """
    Dataclass to hold scraped web page data.
    """
    title: Optional[str] = None
    meta_description: Optional[str] = None
    hyperlinks: List[str] = None
    images: List[str] = None
    headings: dict = None

def is_valid_url(url: str) -> bool:
    """
    Checks if a URL is valid.

    Args:
    - url (str): The URL to check.

    Returns:
    - bool: True if the URL is valid, False otherwise.
    """
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except ValueError:
        return False

def scrape_web_page(url: str) -> ScrapedData:
    """
    Scrapes a web page for title, meta description, hyperlinks, images, and headings.

    Args:
    - url (str): The URL of the web page to scrape.

    Returns:
    - ScrapedData: A dataclass containing the scraped data.

    Raises:
    - ValueError: If the URL is invalid.
    - requests.RequestException: For network issues.
    """
    if not is_valid_url(url):
        raise ValueError("Invalid URL")

    try:
        # Send a GET request with a user-agent to mimic a browser
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3'}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()  # Raise an exception for HTTP errors
    except requests.RequestException as e:
        logging.error(f"Network error: {e}")
        raise

    soup = BeautifulSoup(response.text, 'html.parser')
    scraped_data = ScrapedData()

    # Extract Page Title
    scraped_data.title = soup.title.string if soup.title else None

    # Extract Meta Description
    meta_description_tag = soup.find('meta', attrs={'name': 'description'})
    scraped_data.meta_description = meta_description_tag.get('content') if meta_description_tag else None

    # Extract Hyperlinks
    scraped_data.hyperlinks = []
    for link in soup.find_all('a'):
        href = link.get('href')
        if href:
            # Join relative URLs with the base URL
            absolute_url = urljoin(url, href)
            scraped_data.hyperlinks.append(absolute_url)

    # Extract Images
    scraped_data.images = []
    for img in soup.find_all('img'):
        src = img.get('src')
        if src:
            absolute_src = urljoin(url, src)
            scraped_data.images.append(absolute_src)

    # Extract Headings
    scraped_data.headings = {f"h{i}": [] for i in range(1, 4)}  # Initialize for h1, h2, h3
    for i in range(1, 4):
        for heading in soup.find_all(f"h{i}"):
            scraped_data.headings[f"h{i}"].append(heading.text.strip())

    return scraped_data

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Web Page Scraper")
    parser.add_argument("url", help="URL of the web page to scrape")
    args = parser.parse_args()

    try:
        data = scrape_web_page(args.url)
        print("Scraped Data:")
        print(f"Title: {data.title}")
        print(f"Meta Description: {data.meta_description}")
        print("Hyperlinks:", data.hyperlinks)
        print("Images:", data.images)
        print("Headings:")
        for level, texts in data.headings.items():
            print(f"{level}: {texts}")
    except Exception as e:
        logging.error(f"Error: {e}")