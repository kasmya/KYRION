import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from typing import Dict, List, Tuple

def scrape_url(url: str) -> Dict[str, List[str]]:
    """
    Scrapes a given URL for hyperlinks, images, page title, meta description, and headings.

    Args:
        url (str): The URL to scrape.

    Returns:
        Dict[str, List[str]]: A dictionary containing the scraped data.
    """
    try:
        # Check if the URL is valid
        result = urlparse(url)
        if not all([result.scheme, result.netloc]):
            raise ValueError("Invalid URL")

        # Send a GET request to the URL
        response = requests.get(url, timeout=5)
        response.raise_for_status()  # Raise an exception for 4xx or 5xx status codes

        # Parse the HTML content using BeautifulSoup
        soup = BeautifulSoup(response.text, 'html.parser')

        # Extract the page title
        title = soup.find('title').text.strip() if soup.find('title') else ""

        # Extract the meta description
        meta_description = soup.find('meta', attrs={'name': 'description'})
        meta_description = meta_description.get('content').strip() if meta_description else ""

        # Extract all hyperlinks
        hyperlinks = []
        for link in soup.find_all('a'):
            href = link.get('href')
            if href:
                # Convert relative URLs to absolute URLs
                hyperlinks.append(urljoin(url, href))

        # Extract all images
        images = []
        for image in soup.find_all('img'):
            src = image.get('src')
            if src:
                # Convert relative URLs to absolute URLs
                images.append(urljoin(url, src))

        # Extract all headings (h1, h2, h3)
        headings = []
        for heading in soup.find_all(['h1', 'h2', 'h3']):
            headings.append(heading.text.strip())

        # Return the scraped data
        return {
            "title": [title],
            "meta_description": [meta_description],
            "hyperlinks": hyperlinks,
            "images": images,
            "headings": headings
        }

    except requests.exceptions.RequestException as e:
        # Handle network issues
        print(f"Error: {e}")
        return {}

    except Exception as e:
        # Handle other exceptions
        print(f"Error: {e}")
        return {}

# Example usage:
if __name__ == "__main__":
    url = "http://example.com"
    scraped_data = scrape_url(url)
    for key, value in scraped_data.items():
        print(f"{key.capitalize()}: {value}")