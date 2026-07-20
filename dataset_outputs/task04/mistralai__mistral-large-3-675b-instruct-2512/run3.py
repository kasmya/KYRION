import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Optional, Tuple
from urllib.parse import urljoin, urlparse
import re

def is_valid_url(url: str) -> bool:
    """
    Check if a URL is valid.

    Args:
        url: The URL to validate.

    Returns:
        bool: True if the URL is valid, False otherwise.
    """
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except ValueError:
        return False

def get_page_content(url: str, timeout: int = 10) -> Optional[requests.Response]:
    """
    Fetch the content of a web page with error handling.

    Args:
        url: The URL to fetch.
        timeout: Timeout in seconds for the request.

    Returns:
        Optional[requests.Response]: The response object if successful, None otherwise.
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    try:
        response = requests.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()
        return response
    except requests.exceptions.RequestException:
        return None

def extract_hyperlinks(soup: BeautifulSoup, base_url: str) -> List[Dict[str, str]]:
    """
    Extract all hyperlinks from the BeautifulSoup object.

    Args:
        soup: BeautifulSoup object of the page.
        base_url: The base URL to resolve relative links.

    Returns:
        List[Dict[str, str]]: List of dictionaries containing link text and URL.
    """
    links = []
    for link in soup.find_all('a', href=True):
        url = urljoin(base_url, link['href'].strip())
        if is_valid_url(url):
            links.append({
                'text': link.get_text(strip=True),
                'url': url
            })
    return links

def extract_images(soup: BeautifulSoup, base_url: str) -> List[Dict[str, str]]:
    """
    Extract all images from the BeautifulSoup object.

    Args:
        soup: BeautifulSoup object of the page.
        base_url: The base URL to resolve relative image sources.

    Returns:
        List[Dict[str, str]]: List of dictionaries containing alt text and image URL.
    """
    images = []
    for img in soup.find_all('img', src=True):
        src = urljoin(base_url, img['src'].strip())
        if is_valid_url(src) or src.startswith('data:image'):
            images.append({
                'alt': img.get('alt', '').strip(),
                'src': src
            })
    return images

def extract_meta_description(soup: BeautifulSoup) -> Optional[str]:
    """
    Extract the meta description from the BeautifulSoup object.

    Args:
        soup: BeautifulSoup object of the page.

    Returns:
        Optional[str]: The meta description if found, None otherwise.
    """
    meta = soup.find('meta', attrs={'name': 'description'})
    return meta['content'].strip() if meta else None

def extract_headings(soup: BeautifulSoup) -> Dict[str, List[str]]:
    """
    Extract all headings (h1, h2, h3) from the BeautifulSoup object.

    Args:
        soup: BeautifulSoup object of the page.

    Returns:
        Dict[str, List[str]]: Dictionary with keys as heading levels and values as lists of heading texts.
    """
    headings = {'h1': [], 'h2': [], 'h3': []}
    for level in headings:
        for heading in soup.find_all(level):
            headings[level].append(heading.get_text(strip=True))
    return headings

def scrape_website(url: str) -> Optional[Dict[str, object]]:
    """
    Scrape a website and extract hyperlinks, images, title, meta description, and headings.

    Args:
        url: The URL of the website to scrape.

    Returns:
        Optional[Dict[str, object]]: Dictionary containing scraped data or None if scraping fails.
    """
    if not is_valid_url(url):
        return None

    response = get_page_content(url)
    if not response:
        return None

    soup = BeautifulSoup(response.content, 'html.parser')

    return {
        'title': soup.title.string.strip() if soup.title else None,
        'meta_description': extract_meta_description(soup),
        'hyperlinks': extract_hyperlinks(soup, url),
        'images': extract_images(soup, url),
        'headings': extract_headings(soup)
    }

if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        print("Usage: python scraper.py <url>")
        sys.exit(1)

    result = scrape_website(sys.argv[1])
    if result:
        import json
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print("Failed to scrape the website.")