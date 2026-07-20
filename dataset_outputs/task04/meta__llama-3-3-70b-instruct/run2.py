import requests
from bs4 import BeautifulSoup
from urllib.parse import urlsplit, urlparse
from typing import Dict, List, Tuple

def scrape_url(url: str) -> Dict[str, List[str]]:
    """
    Scrapes the given URL and extracts all hyperlinks, images, page title, 
    meta description, and all headings (h1, h2, h3).

    Args:
        url (str): The URL to scrape.

    Returns:
        Dict[str, List[str]]: A dictionary containing the scraped data.
    """
    try:
        # Validate the URL
        result = urlparse(url)
        if not all([result.scheme, result.netloc]):
            raise ValueError("Invalid URL")

        # Send a GET request
        response = requests.get(url, timeout=5)

        # Check if the request was successful
        response.raise_for_status()

        # Parse the HTML content
        soup = BeautifulSoup(response.text, 'html.parser')

        # Extract the page title
        title = soup.find('title')
        page_title = title.text.strip() if title else ""

        # Extract the meta description
        meta_description = soup.find('meta', attrs={'name': 'description'})
        meta_description = meta_description.get('content') if meta_description else ""

        # Extract all hyperlinks
        hyperlinks = [a.get('href') for a in soup.find_all('a', href=True)]

        # Extract all images
        images = [img.get('src') for img in soup.find_all('img', src=True)]

        # Extract all headings (h1, h2, h3)
        headings = [h.text.strip() for h in soup.find_all(['h1', 'h2', 'h3'])]

        return {
            "title": [page_title],
            "meta_description": [meta_description],
            "hyperlinks": hyperlinks,
            "images": images,
            "headings": headings
        }

    except requests.exceptions.HTTPError as http_err:
        print(f"HTTP error occurred: {http_err}")
    except Exception as err:
        print(f"Other error occurred: {err}")
    return {}

def main():
    url = "http://example.com"
    scraped_data = scrape_url(url)
    for key, value in scraped_data.items():
        print(f"{key}: {value}")

if __name__ == "__main__":
    main()