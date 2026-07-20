import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from typing import Dict, List, Optional

def is_valid_url(url: str) -> bool:
    """Check if a URL is valid."""
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except ValueError:
        return False

def extract_hyperlinks(html: str, base_url: str) -> List[str]:
    """Extract all hyperlinks from HTML."""
    soup = BeautifulSoup(html, 'html.parser')
    hyperlinks = []
    for link in soup.find_all('a'):
        href = link.get('href')
        if href:
            absolute_url = urljoin(base_url, href)
            hyperlinks.append(absolute_url)
    return hyperlinks

def extract_images(html: str, base_url: str) -> List[str]:
    """Extract all image URLs from HTML."""
    soup = BeautifulSoup(html, 'html.parser')
    images = []
    for img in soup.find_all('img'):
        src = img.get('src')
        if src:
            absolute_url = urljoin(base_url, src)
            images.append(absolute_url)
    return images

def extract_headings(html: str) -> Dict[str, List[str]]:
    """Extract all headings (h1, h2, h3) from HTML."""
    soup = BeautifulSoup(html, 'html.parser')
    headings = {'h1': [], 'h2': [], 'h3': []}
    for heading in soup.find_all(['h1', 'h2', 'h3']):
        headings[heading.name].append(heading.text.strip())
    return headings

def extract_meta_description(html: str) -> Optional[str]:
    """Extract meta description from HTML."""
    soup = BeautifulSoup(html, 'html.parser')
    meta = soup.find('meta', attrs={'name': 'description'})
    return meta.get('content') if meta else None

def extract_page_title(html: str) -> Optional[str]:
    """Extract page title from HTML."""
    soup = BeautifulSoup(html, 'html.parser')
    return soup.find('title').text.strip() if soup.find('title') else None

def scrape_url(url: str) -> Dict[str, List[str] or str]:
    """Scrape a URL and extract relevant information."""
    if not is_valid_url(url):
        raise ValueError("Invalid URL")

    try:
        response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
        response.raise_for_status()
    except requests.RequestException as e:
        raise Exception(f"Failed to retrieve URL: {e}")

    html = response.text
    hyperlinks = extract_hyperlinks(html, url)
    images = extract_images(html, url)
    headings = extract_headings(html)
    meta_description = extract_meta_description(html)
    page_title = extract_page_title(html)

    return {
        'hyperlinks': hyperlinks,
        'images': images,
        'headings': headings,
        'meta_description': meta_description,
        'page_title': page_title
    }

# Example usage:
url = "https://www.example.com"
result = scrape_url(url)
print(result)