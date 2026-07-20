import requests
from bs4 import BeautifulSoup
from urllib.parse import urlsplit, urlparse
from typing import List, Dict, Optional
import logging

def scrape_website(url: str) -> Dict:
    """
    Scrapes a website and extracts hyperlinks, images, page title, meta description, and headings.

    Args:
    url (str): The URL of the website to scrape.

    Returns:
    Dict: A dictionary containing the extracted data.
    """

    # Validate the URL
    try:
        result = urlparse(url)
        if not all([result.scheme, result.netloc]):
            raise ValueError("Invalid URL")
    except ValueError as e:
        logging.error(f"Invalid URL: {e}")
        raise

    try:
        # Send a GET request to the URL
        response = requests.get(url, timeout=5, headers={'User-Agent': 'Mozilla/5.0'})

        # Check if the request was successful
        response.raise_for_status()

        # Parse the HTML content using BeautifulSoup
        soup = BeautifulSoup(response.text, 'html.parser')

        # Extract hyperlinks
        hyperlinks = [a.get('href') for a in soup.find_all('a', href=True)]

        # Extract images
        images = [img.get('src') for img in soup.find_all('img', src=True)]

        # Extract page title
        page_title = soup.find('title').text if soup.find('title') else None

        # Extract meta description
        meta_description = soup.find('meta', attrs={'name': 'description'})
        meta_description = meta_description.get('content') if meta_description else None

        # Extract headings
        headings = {}
        for i in range(1, 4):
            headings[f'h{i}'] = [h.text for h in soup.find_all(f'h{i}')]
    except requests.exceptions.RequestException as e:
        logging.error(f"Error scraping website: {e}")
        raise

    return {
        'hyperlinks': hyperlinks,
        'images': images,
        'page_title': page_title,
        'meta_description': meta_description,
        'headings': headings
    }

def main():
    url = input("Enter the URL to scrape: ")
    try:
        scraped_data = scrape_website(url)
        print(scraped_data)
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.ERROR)
    main()