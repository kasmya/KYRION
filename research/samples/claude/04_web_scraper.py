"""
### Task 4: Web Scraper (BeautifulSoup + Requests)

A resilient product scraper with pagination handling, retry logic with
exponential backoff, user-agent rotation, optional proxy support, and
CSV/JSON export.

Requirements:
    pip install requests beautifulsoup4 fake-useragent

Usage:
    python 04_web_scraper.py --base-url "https://example.com/products" --pages 5 \
        --output-csv products.csv --output-json products.json
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import random
import sys
import time
from dataclasses import asdict, dataclass
from typing import List, Optional

import requests
from bs4 import BeautifulSoup

try:
    from fake_useragent import UserAgent

    _ua_generator = UserAgent()
except Exception:  # noqa: BLE001 - fall back gracefully if offline / package unavailable
    _ua_generator = None

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("web_scraper")

FALLBACK_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
]

MAX_RETRIES = 4
BASE_BACKOFF_SECONDS = 1.5
REQUEST_TIMEOUT = 10


@dataclass
class Product:
    """Represents a single scraped product record."""

    name: str
    price: Optional[float]
    rating: Optional[float]
    source_url: str


class ScraperError(Exception):
    """Raised when a page cannot be fetched or parsed after all retries."""


def get_random_user_agent() -> str:
    """Returns a random user-agent string, using fake_useragent if available."""
    if _ua_generator is not None:
        try:
            return _ua_generator.random
        except Exception:  # noqa: BLE001
            pass
    return random.choice(FALLBACK_USER_AGENTS)


def fetch_page(
    url: str, proxies: Optional[dict] = None, max_retries: int = MAX_RETRIES
) -> str:
    """Fetches a URL's HTML with retry logic and exponential backoff.

    Args:
        url: The URL to fetch.
        proxies: Optional requests-style proxy dict, e.g. {"https": "http://host:port"}.
        max_retries: Maximum number of attempts before giving up.

    Returns:
        The response body as text.

    Raises:
        ScraperError: If the page could not be fetched after all retries.
    """
    last_exception: Optional[Exception] = None

    for attempt in range(1, max_retries + 1):
        headers = {"User-Agent": get_random_user_agent()}
        try:
            response = requests.get(
                url, headers=headers, proxies=proxies, timeout=REQUEST_TIMEOUT
            )
            response.raise_for_status()
            return response.text
        except requests.RequestException as exc:
            last_exception = exc
            backoff = BASE_BACKOFF_SECONDS * (2 ** (attempt - 1)) + random.uniform(0, 0.5)
            logger.warning(
                "Attempt %d/%d failed for '%s': %s. Retrying in %.1fs",
                attempt,
                max_retries,
                url,
                exc,
                backoff,
            )
            time.sleep(backoff)

    raise ScraperError(f"Failed to fetch '{url}' after {max_retries} attempts: {last_exception}")


def parse_products(html: str, source_url: str) -> List[Product]:
    """Parses product cards out of a page's HTML.

    NOTE: The CSS selectors below (`.product-card`, `.name`, `.price`, `.rating`)
    are illustrative placeholders. Adjust them to match the target site's markup.
    """
    soup = BeautifulSoup(html, "html.parser")
    products: List[Product] = []

    for card in soup.select(".product-card"):
        name_el = card.select_one(".name")
        price_el = card.select_one(".price")
        rating_el = card.select_one(".rating")

        name = name_el.get_text(strip=True) if name_el else "Unknown"
        price = _parse_price(price_el.get_text(strip=True)) if price_el else None
        rating = _parse_rating(rating_el.get_text(strip=True)) if rating_el else None

        products.append(Product(name=name, price=price, rating=rating, source_url=source_url))

    logger.info("Parsed %d product(s) from %s", len(products), source_url)
    return products


def _parse_price(raw: str) -> Optional[float]:
    """Extracts a float price from a raw text string like '$19.99'."""
    cleaned = "".join(ch for ch in raw if ch.isdigit() or ch == ".")
    try:
        return float(cleaned) if cleaned else None
    except ValueError:
        logger.debug("Could not parse price from '%s'", raw)
        return None


def _parse_rating(raw: str) -> Optional[float]:
    """Extracts a float rating from a raw text string like '4.5 out of 5'."""
    try:
        return float(raw.split()[0])
    except (ValueError, IndexError):
        logger.debug("Could not parse rating from '%s'", raw)
        return None


def find_next_page_url(html: str, base_url: str) -> Optional[str]:
    """Finds a 'next page' link, if present, resolved against the base URL."""
    soup = BeautifulSoup(html, "html.parser")
    next_link = soup.select_one('a[rel="next"], a.next, .pagination .next')
    if next_link and next_link.get("href"):
        from urllib.parse import urljoin

        return urljoin(base_url, next_link["href"])
    return None


def scrape_all_pages(
    base_url: str, max_pages: int, proxies: Optional[dict] = None
) -> List[Product]:
    """Scrapes products across paginated listing pages, following 'next' links."""
    all_products: List[Product] = []
    current_url: Optional[str] = base_url
    page_count = 0

    while current_url and page_count < max_pages:
        page_count += 1
        logger.info("Scraping page %d: %s", page_count, current_url)
        try:
            html = fetch_page(current_url, proxies=proxies)
        except ScraperError as exc:
            logger.error("Stopping pagination early: %s", exc)
            break

        all_products.extend(parse_products(html, current_url))
        current_url = find_next_page_url(html, current_url)

    return all_products


def save_to_csv(products: List[Product], path: str) -> None:
    """Writes scraped products to a CSV file."""
    if not products:
        logger.warning("No products to write to CSV")
        return
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(asdict(products[0]).keys()))
        writer.writeheader()
        for product in products:
            writer.writerow(asdict(product))
    logger.info("Wrote %d product(s) to '%s'", len(products), path)


def save_to_json(products: List[Product], path: str) -> None:
    """Writes scraped products to a JSON file."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump([asdict(p) for p in products], f, indent=2)
    logger.info("Wrote %d product(s) to '%s'", len(products), path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Scrape product listings with retries and pagination.")
    parser.add_argument("--base-url", required=True, help="Starting URL of the product listing page")
    parser.add_argument("--pages", type=int, default=5, help="Maximum number of pages to scrape")
    parser.add_argument("--proxy", help="Optional proxy URL, e.g. http://user:pass@host:port")
    parser.add_argument("--output-csv", default="products.csv")
    parser.add_argument("--output-json", default="products.json")
    return parser


def main(argv: List[str] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    proxies = {"http": args.proxy, "https": args.proxy} if args.proxy else None

    try:
        products = scrape_all_pages(args.base_url, args.pages, proxies=proxies)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Scraping failed unexpectedly: %s", exc)
        return 1

    save_to_csv(products, args.output_csv)
    save_to_json(products, args.output_json)
    logger.info("Scraping complete: %d total product(s)", len(products))
    return 0


if __name__ == "__main__":
    sys.exit(main())
