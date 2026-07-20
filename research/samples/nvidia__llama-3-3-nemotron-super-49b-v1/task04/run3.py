from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from requests import RequestException
from typing import List, Dict, Optional
from logging import Logger, getLogger
from logging.config import dictConfig

# Configure logging
dictConfig({
    'version': 1,
    'formatters': {
        'standard': {'format': '[%(levelname)s] %(message)s'}
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'level': 'INFO',
            'formatter': 'standard'
        }
    },
    'root': {
        'level': 'DEBUG',
        'handlers': ['console']
    }
})

logger: Logger = getLogger(__name__)

class WebScraper:
    """
    A web scraper class to extract common webpage elements.
    
    Attributes:
    - url (str): The URL of the webpage to scrape.
    - user_agent (str): User agent string for HTTP requests.
    """

    def __init__(self, url: str, user_agent: str = "WebScraper/1.0"):
        """
        Initialize the WebScraper with a URL and optional user agent.
        
        Args:
        - url (str): The URL of the webpage to scrape.
        - user_agent (str, optional): User agent string. Defaults to "WebScraper/1.0".
        
        Raises:
        - ValueError: If the URL is invalid.
        """
        self.url = url
        self.user_agent = user_agent
        
        # Validate URL
        try:
            result = urlparse(url)
            if not all([result.scheme, result.netloc]):
                raise ValueError("Invalid URL")
        except ValueError as e:
            logger.error(f"Invalid URL: {e}")
            raise

    def _fetch_page(self) -> Optional[BeautifulSoup]:
        """
        Fetch the webpage content using requests.
        
        Returns:
        - Optional[BeautifulSoup]: Parsed BeautifulSoup object or None on failure.
        """
        try:
            headers = {'User-Agent': self.user_agent}
            response = RequestException.get(self.url, headers=headers)
            response.raise_for_status()  # Raise an exception for HTTP errors
            return BeautifulSoup(response.text, 'html.parser')
        except RequestException as e:
            logger.error(f"Network error fetching {self.url}: {e}")
            return None

    def scrape(self) -> Dict[str, List[str]]:
        """
        Scrape the webpage for hyperlinks, images, page title, meta description, and headings.
        
        Returns:
        - Dict[str, List[str]]: Dictionary containing the scraped elements.
        """
        soup = self._fetch_page()
        if not soup:
            return {}  # Return empty dict on failure

        result: Dict[str, List[str]] = {
            "hyperlinks": [],
            "images": [],
            "headings": [],
            "page_title": [soup.title.string] if soup.title else [],
            "meta_description": []
        }

        # Extract meta description
        meta_desc = soup.find('meta', attrs={'name': 'description'})
        if meta_desc and meta_desc.get('content'):
            result["meta_description"].append(meta_desc['content'])

        # Extract hyperlinks
        for link in soup.find_all('a'):
            href = link.get('href')
            if href:
                # Ensure absolute URLs
                result["hyperlinks"].append(urljoin(self.url, href))

        # Extract images
        for img in soup.find_all('img'):
            src = img.get('src')
            if src:
                result["images"].append(urljoin(self.url, src))

        # Extract headings
        for header in soup.find_all(['h1', 'h2', 'h3']):
            result["headings"].append(header.text.strip())

        return result


def main():
    if __name__ == "__main__":
        url = "https://example.com"  # Replace with your target URL
        scraper = WebScraper(url)
        scraped_data = scraper.scrape()
        
        # Example: Print scraped data
        for key, value in scraped_data.items():
            print(f"{key.capitalize().replace('_', ' ')}:")
            for item in value:
                print(f"- {item}")
            print()


if __name__ == "__main__":
    main()