"""Web Scraper with retry logic, user-agent rotation, and proxy support."""
import csv, json, time, logging, random
from typing import List, Dict, Optional
import requests
from bs4 import BeautifulSoup
from fake_useragent import UserAgent

logging.basicConfig(level=logging.INFO)
ua = UserAgent()
PROXIES = {"http": "http://10.10.1.10:3128", "https": "http://10.10.1.10:1080"} # Example proxy

def fetch_with_retry(url: str, retries: int = 3, backoff: float = 2.0) -> Optional[requests.Response]:
    """Fetch URL with exponential backoff."""
    for i in range(retries):
        try:
            headers = {'User-Agent': ua.random}
            # Using proxies=PROXIES if needed, omitted for general execution safety
            resp = requests.get(url, headers=headers, timeout=10)
            resp.raise_for_status()
            return resp
        except requests.RequestException as e:
            logging.warning(f"Attempt {i+1} failed for {url}: {e}")
            time.sleep(backoff * (2 ** i))
    return None

def scrape_page(url: str) -> List[Dict[str, str]]:
    """Scrape product data from a single page."""
    resp = fetch_with_retry(url)
    if not resp: return []
    soup = BeautifulSoup(resp.text, 'html.parser')
    products = []
    # Generic selectors for demonstration
    for item in soup.select('.product-card'):
        name = item.select_one('.title').text.strip() if item.select_one('.title') else 'N/A'
        price = item.select_one('.price').text.strip() if item.select_one('.price') else 'N/A'
        rating = item.select_one('.rating').text.strip() if item.select_one('.rating') else 'N/A'
        products.append({"name": name, "price": price, "rating": rating})
    return products

def scrape_all(base_url: str, max_pages: int = 3) -> List[Dict[str, str]]:
    """Handle pagination and aggregate data."""
    all_data = []
    for page in range(1, max_pages + 1):
        url = f"{base_url}?page={page}"
        logging.info(f"Scraping {url}")
        data = scrape_page(url)
        if not data: break
        all_data.extend(data)
        time.sleep(random.uniform(1, 3)) # Polite delay
    return all_data

def save_data(data: List[Dict], filename: str):
    """Save to CSV and JSON."""
    if not data: return
    with open(f"{filename}.csv", 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=data[0].keys())
        writer.writeheader()
        writer.writerows(data)
    with open(f"{filename}.json", 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)
    logging.info(f"Saved {len(data)} items to {filename}.csv/json")

if __name__ == "__main__":
    # Example usage with a mock URL structure
    # data = scrape_all("http://example.com/products", max_pages=2)
    # save_data(data, "products")
    logging.info("Scraper ready. Configure base_url to run.")