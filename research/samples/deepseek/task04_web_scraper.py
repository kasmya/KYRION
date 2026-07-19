"""
Advanced Web Scraper with rate limiting, proxy support, and exponential backoff.

Features:
- Scrapes product data (name, price, rating)
- Handles pagination
- Saves to CSV and JSON
- Retry logic with exponential backoff
- User-agent rotation
- Proxy support
"""

import os
import logging
import time
import random
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime
import csv
import json
from urllib.parse import urljoin, urlparse
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
import pandas as pd

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('scraper.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class ScraperConfig:
    """Configuration for web scraper."""
    
    def __init__(
        self,
        base_url: str,
        delay_range: Tuple[float, float] = (1.0, 3.0),
        max_retries: int = 3,
        backoff_factor: float = 2.0,
        timeout: int = 30,
        proxies: Optional[List[str]] = None,
        max_pages: int = 100
    ):
        """
        Initialize scraper configuration.
        
        Args:
            base_url: Base URL to scrape
            delay_range: Range for random delay between requests (min, max)
            max_retries: Maximum retry attempts
            backoff_factor: Exponential backoff factor
            timeout: Request timeout in seconds
            proxies: List of proxy URLs
            max_pages: Maximum pages to scrape
        """
        self.base_url = base_url
        self.delay_range = delay_range
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self.timeout = timeout
        self.proxies = proxies or []
        self.max_pages = max_pages

class WebScraper:
    """Advanced web scraper with multiple features."""
    
    def __init__(self, config: ScraperConfig):
        """
        Initialize web scraper.
        
        Args:
            config: ScraperConfig object with settings
        """
        self.config = config
        self.ua = UserAgent()
        self.session = self._create_session()
        self.scraped_data: List[Dict[str, Any]] = []
        self.current_proxy_index = 0
        
        logger.info(f"Scraper initialized for {config.base_url}")
    
    def _create_session(self) -> requests.Session:
        """Create a requests session with retry logic."""
        session = requests.Session()
        
        retry_strategy = Retry(
            total=self.config.max_retries,
            backoff_factor=self.config.backoff_factor,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS"]
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        return session
    
    def _get_random_headers(self) -> Dict[str, str]:
        """Generate random headers with user-agent rotation."""
        return {
            'User-Agent': self.ua.random,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
    
    def _get_proxy(self) -> Optional[Dict[str, str]]:
        """Get next proxy from rotation."""
        if not self.config.proxies:
            return None
        
        proxy = self.config.proxies[self.current_proxy_index]
        self.current_proxy_index = (self.current_proxy_index + 1) % len(self.config.proxies)
        
        return {'http': proxy, 'https': proxy}
    
    def _fetch_page(self, url: str) -> Optional[BeautifulSoup]:
        """
        Fetch a webpage with retry logic and exponential backoff.
        
        Args:
            url: URL to fetch
            
        Returns:
            BeautifulSoup object or None if failed
        """
        for attempt in range(self.config.max_retries):
            try:
                # Add delay
                if attempt > 0:
                    delay = self.config.backoff_factor ** attempt
                    logger.info(f"Retry {attempt}/{self.config.max_retries} after {delay}s")
                    time.sleep(delay)
                else:
                    delay = random.uniform(*self.config.delay_range)
                    time.sleep(delay)
                
                headers = self._get_random_headers()
                proxy = self._get_proxy()
                
                logger.debug(f"Fetching {url} (attempt {attempt + 1})")
                
                response = self.session.get(
                    url,
                    headers=headers,
                    proxies=proxy,
                    timeout=self.config.timeout
                )
                
                response.raise_for_status()
                
                # Check for blocking
                if len(response.text) < 1000 and response.status_code == 200:
                    logger.warning(f"Possible blocking detected on {url}")
                    raise requests.RequestException("Possible blocking detected")
                
                return BeautifulSoup(response.text, 'html.parser')
                
            except requests.RequestException as e:
                logger.error(f"Request failed for {url}: {str(e)}")
                
                if attempt == self.config.max_retries - 1:
                    logger.error(f"Max retries reached for {url}")
                    return None
                
                continue
            
            except Exception as e:
                logger.error(f"Unexpected error fetching {url}: {str(e)}", exc_info=True)
                return None
        
        return None
    
    def parse_product_page(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """
        Parse product information from BeautifulSoup object.
        
        Args:
            soup: BeautifulSoup object of product page
            
        Returns:
            Dictionary containing product information
        """
        product = {
            'name': self._extract_name(soup),
            'price': self._extract_price(soup),
            'rating': self._extract_rating(soup),
            'description': self._extract_description(soup),
            'url': self._extract_url(soup),
            'availability': self._extract_availability(soup),
            'scraped_at': datetime.now().isoformat()
        }
        
        return product
    
    def _extract_name(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract product name with multiple selectors."""
        selectors = [
            'h1.product-title',
            'h1.product-name',
            '[data-testid="product-title"]',
            '.product-name',
            'h1[itemprop="name"]',
            '#productTitle'
        ]
        
        for selector in selectors:
            element = soup.select_one(selector)
            if element:
                return element.get_text(strip=True)
        
        # Fallback to h1 tag
        h1 = soup.find('h1')
        if h1:
            return h1.get_text(strip=True)
        
        return None
    
    def _extract_price(self, soup: BeautifulSoup) -> Optional[float]:
        """Extract product price."""
        selectors = [
            '.price',
            '[data-testid="price"]',
            '.product-price',
            '[itemprop="price"]',
            '#priceblock_ourprice',
            '.a-price .a-offscreen'
        ]
        
        for selector in selectors:
            element = soup.select_one(selector)
            if element:
                text = element.get_text(strip=True)
                # Extract numeric price
                import re
                match = re.search(r'[\d,.]+', text)
                if match:
                    try:
                        return float(match.group().replace(',', ''))
                    except ValueError:
                        continue
        
        return None
    
    def _extract_rating(self, soup: BeautifulSoup) -> Optional[float]:
        """Extract product rating."""
        selectors = [
            '[data-testid="rating"]',
            '.star-rating',
            '[itemprop="ratingValue"]',
            '.a-icon-star'
        ]
        
        for selector in selectors:
            element = soup.select_one(selector)
            if element:
                # Try to get from text
                text = element.get_text(strip=True)
                import re
                match = re.search(r'(\d+(\.\d+)?)', text)
                if match:
                    rating = float(match.group(1))
                    if 0 <= rating <= 5:
                        return rating
                
                # Try to get from attribute
                rating_text = element.get('content') or element.get('data-rating')
                if rating_text:
                    try:
                        return float(rating_text)
                    except ValueError:
                        continue
        
        return None
    
    def _extract_description(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract product description."""
        selectors = [
            '[data-testid="description"]',
            '.product-description',
            '#productDescription',
            '[itemprop="description"]'
        ]
        
        for selector in selectors:
            element = soup.select_one(selector)
            if element:
                return element.get_text(strip=True)[:1000]  # Limit length
        
        return None
    
    def _extract_url(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract canonical URL."""
        canonical = soup.find('link', rel='canonical')
        if canonical:
            return canonical.get('href')
        return None
    
    def _extract_availability(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract product availability."""
        selectors = [
            '[data-testid="availability"]',
            '.availability',
            '#availability'
        ]
        
        for selector in selectors:
            element = soup.select_one(selector)
            if element:
                return element.get_text(strip=True)
        
        return 'Unknown'
    
    def find_product_links(self, soup: BeautifulSoup, base_url: str) -> List[str]:
        """
        Extract product links from listing page.
        
        Args:
            soup: BeautifulSoup object
            base_url: Base URL for resolving relative links
            
        Returns:
            List of product URLs
        """
        links = set()
        
        # Common product link patterns
        selectors = [
            'a.product-link',
            'a[href*="/product/"]',
            'a[href*="/item/"]',
            'a[href*="/p/"]',
            '.product-card a',
            '[data-testid="product-link"]'
        ]
        
        for selector in selectors:
            elements = soup.select(selector)
            for element in elements:
                href = element.get('href')
                if href:
                    full_url = urljoin(base_url, href)
                    links.add(full_url)
        
        return list(links)
    
    def find_next_page(self, soup: BeautifulSoup, current_url: str) -> Optional[str]:
        """
        Find next page URL for pagination.
        
        Args:
            soup: BeautifulSoup object
            current_url: Current page URL
            
        Returns:
            Next page URL or None if no more pages
        """
        # Common next page patterns
        selectors = [
            'a.next',
            'a[rel="next"]',
            'a.pagination-next',
            'a[aria-label="Next page"]',
            '.pagination a:last-child'
        ]
        
        for selector in selectors:
            element = soup.select_one(selector)
            if element:
                href = element.get('href')
                if href and href != current_url:
                    return urljoin(current_url, href)
        
        return None
    
    def scrape_products(self, start_url: str) -> List[Dict[str, Any]]:
        """
        Scrape products with pagination support.
        
        Args:
            start_url: Starting URL for scraping
            
        Returns:
            List of scraped product dictionaries
        """
        products = []
        current_url = start_url
        page_count = 0
        
        while current_url and page_count < self.config.max_pages:
            logger.info(f"Scraping page {page_count + 1}: {current_url}")
            
            # Fetch listing page
            soup = self._fetch_page(current_url)
            if not soup:
                logger.error(f"Failed to fetch page {current_url}")
                break
            
            # Find product links
            product_links = self.find_product_links(soup, current_url)
            logger.info(f"Found {len(product_links)} product links")
            
            # Scrape each product
            for product_url in product_links:
                logger.debug(f"Scraping product: {product_url}")
                product_soup = self._fetch_page(product_url)
                
                if product_soup:
                    product_data = self.parse_product_page(product_soup)
                    products.append(product_data)
                    logger.info(f"Scraped: {product_data.get('name', 'Unknown')}")
            
            # Get next page
            next_page = self.find_next_page(soup, current_url)
            if next_page and next_page != current_url:
                current_url = next_page
                page_count += 1
            else:
                logger.info("No more pages found")
                break
        
        self.scraped_data = products
        logger.info(f"Scraped {len(products)} products from {page_count} pages")
        
        return products
    
    def save_to_csv(self, filename: str) -> None:
        """Save scraped data to CSV file."""
        if not self.scraped_data:
            logger.warning("No data to save")
            return
        
        try:
            with open(filename, 'w', newline='', encoding='utf-8') as f:
                if self.scraped_data:
                    writer = csv.DictWriter(f, fieldnames=self.scraped_data[0].keys())
                    writer.writeheader()
                    writer.writerows(self.scraped_data)
            
            logger.info(f"Data saved to {filename}")
            
        except Exception as e:
            logger.error(f"Error saving to CSV: {str(e)}", exc_info=True)
    
    def save_to_json(self, filename: str) -> None:
        """Save scraped data to JSON file."""
        if not self.scraped_data:
            logger.warning("No data to save")
            return
        
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(self.scraped_data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Data saved to {filename}")
            
        except Exception as e:
            logger.error(f"Error saving to JSON: {str(e)}", exc_info=True)

def main():
    """Main function demonstrating scraper usage."""
    
    # Configuration
    config = ScraperConfig(
        base_url="https://books.toscrape.com",
        delay_range=(1.0, 3.0),
        max_retries=3,
        backoff_factor=2.0,
        timeout=30,
        max_pages=5
    )
    
    # Initialize scraper
    scraper = WebScraper(config)
    
    # Scrape products
    start_url = "https://books.toscrape.com/catalogue/page-1.html"
    products = scraper.scrape_products(start_url)
    
    # Save data
    if products:
        output_dir = Path("scraped_data")
        output_dir.mkdir(exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        csv_filename = output_dir / f"products_{timestamp}.csv"
        json_filename = output_dir / f"products_{timestamp}.json"
        
        scraper.save_to_csv(str(csv_filename))
        scraper.save_to_json(str(json_filename))
        
        # Display summary
        df = pd.DataFrame(products)
        print("\n" + "="*50)
        print("SCRAPING SUMMARY")
        print("="*50)
        print(f"Total products scraped: {len(products)}")
        print(f"Columns: {', '.join(df.columns)}")
        
        if not df.empty:
            print(f"\nSample data:")
            print(df[['name', 'price', 'rating']].head())
            
            print(f"\nPrice statistics:")
            if 'price' in df and df['price'].notna().any():
                print(f"  Average price: ${df['price'].mean():.2f}")
                print(f"  Price range: ${df['price'].min():.2f} - ${df['price'].max():.2f}")
            
            print(f"\nRating statistics:")
            if 'rating' in df and df['rating'].notna().any():
                print(f"  Average rating: {df['rating'].mean():.2f}/5.0")
            
            print(f"\nFiles saved to:")
            print(f"  CSV: {csv_filename}")
            print(f"  JSON: {json_filename}")
    else:
        print("No products were scraped")

if __name__ == "__main__":
    main()
