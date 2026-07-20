import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from typing import List, Dict, Optional
import logging

logging.basicConfig(level=logging.INFO)

def scrape_url(url: str) -> Optional[Dict]:
    """
    Scrapes the given URL and returns a dictionary with extracted information.

    Args:
    url (str): The URL to scrape.

    Returns:
    Optional[Dict]: A dictionary with the extracted information or None if the URL is invalid.
    """
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
    except requests.RequestException as e:
        logging.error(f"Error scraping URL: {e}")
        return None

    soup = BeautifulSoup(response.text, 'html.parser')

    page_title = soup.find('title').text if soup.find('title') else None
    meta_description = soup.find('meta', attrs={'name': 'description'})
    meta_description = meta_description.get('content') if meta_description else None

    headings = {
        'h1': [h1.text.strip() for h1 in soup.find_all('h1')],
        'h2': [h2.text.strip() for h2 in soup.find_all('h2')],
        'h3': [h3.text.strip() for h3 in soup.find_all('h3')]
    }

    images = [img.get('src') for img in soup.find_all('img') if img.get('src')]
    images = [urljoin(url, img) for img in images if urlparse(img).netloc == '']

    links = [a.get('href') for a in soup.find_all('a') if a.get('href')]
    links = [urljoin(url, link) for link in links if urlparse(link).netloc == '']
    links = [link for link in links if link.startswith('http')]

    return {
        'page_title': page_title,
        'meta_description': meta_description,
        'headings': headings,
        'images': images,
        'links': links
    }

if __name__ == "__main__":
    url = "http://example.com"
    result = scrape_url(url)
    if result:
        print("Page Title:", result['page_title'])
        print("Meta Description:", result['meta_description'])
        print("Headings:")
        for heading, texts in result['headings'].items():
            print(f"{heading}: {texts}")
        print("Images:", result['images'])
        print("Links:", result['links'])