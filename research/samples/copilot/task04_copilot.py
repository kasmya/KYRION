"""
Web Scraper using Requests, BeautifulSoup, and fake_useragent.
Features:
- Scrape product data (name, price, rating)
- Handle pagination
- Save to CSV and JSON
- Retry logic with exponential backoff
- User-agent rotation
- Proxy support
"""

import requests
from bs4 import BeautifulSoup
import csv
import json
import time
import random
import logging
from fake_useragent import UserAgent
from typing import List, Dict, Optional

# Configure logging
logging.basicConfig(level=logging.INFO)

# User-agent rotation
ua = UserAgent()

# Example proxy list (stubbed)
PROXIES = [
    "http://proxy1.example.com:8080",
    "http://proxy2.example.com:8080",
]


def fetch_page(url: str, retries: int = 3) -> Optional[str]:
    """Fetch a page with retry logic and user-agent rotation.

    Args:
        url (str): Target URL.
        retries (int): Number of retries.

    Returns:
        Optional[str]: HTML content or None if failed.
    """
    for attempt in range(retries):
        try:
            headers = {"User-Agent": ua.random}
            proxy = {"http": random.choice(PROXIES)} if PROXIES else None
            response = requests.get(url, headers=headers, proxies=proxy, timeout=10)
            response.raise_for_status()
            return response.text
        except requests.RequestException as e:
            wait = 2 ** attempt
            logging.warning(f"Request failed ({e}), retrying in {wait}s...")
            time.sleep(wait)
    logging.error("Failed to fetch page after retries.")
    return None


def parse_products(html: str) -> List[Dict[str, str]]:
    """Parse product data from HTML.

    Args:
        html (str): HTML content.

    Returns:
        List[Dict[str, str]]: List of product dictionaries.
    """
    soup = BeautifulSoup(html, "html.parser")
    products = []
    for item in soup.select(".product"):  # Example CSS selector
        name = item.select_one(".name").get_text(strip=True) if item.select_one(".name") else "N/A"
        price = item.select_one(".price").get_text(strip=True) if item.select_one(".price") else "N/A"
        rating = item.select_one(".rating").get_text(strip=True) if item.select_one(".rating") else "N/A"
        products.append({"name": name, "price": price, "rating": rating})
    return products


def scrape_site(base_url: str, pages: int = 5) -> List[Dict[str, str]]:
    """Scrape multiple pages of products.

    Args:
        base_url (str): Base URL with pagination placeholder.
        pages (int): Number of pages to scrape.

    Returns:
        List[Dict[str, str]]: All scraped products.
    """
    all_products: List[Dict[str, str]] = []
    for page in range(1, pages + 1):
        url = base_url.format(page=page)
        logging.info(f"Scraping {url}")
        html = fetch_page(url)
        if html:
            products = parse_products(html)
            all_products.extend(products)
        else:
            logging.warning(f"Skipping page {page} due to fetch error.")
    return all_products


def save_to_csv(products: List[Dict[str, str]], filename: str) -> None:
    """Save products to CSV file."""
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["name", "price", "rating"])
        writer.writeheader()
        writer.writerows(products)
    logging.info(f"Saved {len(products)} products to {filename}")


def save_to_json(products: List[Dict[str, str]], filename: str) -> None:
    """Save products to JSON file."""
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(products, f, indent=4)
    logging.info(f"Saved {len(products)} products to {filename}")


def main():
    """Main entry point for scraper."""
    base_url = "https://example.com/products?page={page}"  # Replace with real site
    products = scrape_site(base_url, pages=3)
    if products:
        save_to_csv(products, "products.csv")
        save_to_json(products, "products.json")
    else:
        logging.error("No products scraped.")


if __name__ == "__main__":
    main()

