import os
import logging
import sqlite3
from typing import Tuple, Dict, List
import requests
import pandas as pd
from datetime import datetime, timedelta

# Configuration
API_KEY = os.environ['API_KEY']  # Load API key from environment variable
API_URL = "https://www.alphavantage.co/query"
DB_NAME = "stock_tracker.db"

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def fetch_stock_price(symbol: str) -> Dict:
    """
    Fetch real-time stock price from Alpha Vantage API.

    Args:
    - symbol (str): Stock symbol (e.g., AAPL)

    Returns:
    - Dict: Stock price data (or empty dict on failure)
    """
    params = {
        "function": "GLOBAL_QUOTE",
        "symbol": symbol,
        "apikey": API_KEY
    }
    try:
        response = requests.get(API_URL, params=params)
        response.raise_for_status()  # Raise exception for HTTP errors
        return response.json()
    except requests.RequestException as e:
        logger.error(f"API request failed: {e}")
        return {}

def store_historical_data(symbol: str, data: Dict) -> None:
    """
    Store historical stock price data in SQLite database.

    Args:
    - symbol (str): Stock symbol
    - data (Dict): Stock price data
    """
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # Create table if not exists
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS stock_prices (
            id INTEGER PRIMARY KEY,
            symbol TEXT NOT NULL,
            price REAL NOT NULL,
            timestamp TEXT NOT NULL
        )
    """)
    # Insert data
    cursor.execute("""
        INSERT INTO stock_prices (symbol, price, timestamp)
        VALUES (?, ?, ?)
    """, (symbol, data['Global Quote']['05. price'], datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()

def calculate_moving_averages(symbol: str, days: int = 50) -> Tuple[float, float]:
    """
    Calculate simple moving averages (SMA) for the given stock symbol.

    Args:
    - symbol (str): Stock symbol
    - days (int): Number of days for SMA (default: 50)

    Returns:
    - Tuple[float, float]: Short-term SMA (20 days), Long-term SMA (default days)
    """
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT price FROM stock_prices
        WHERE symbol = ? AND timestamp >= DATE('now', ?)
        ORDER BY timestamp DESC
    """, (symbol, f"-{days} days"))
    prices = [row[0] for row in cursor.fetchall()]
    conn.close()
    if not prices:
        return 0.0, 0.0  # Avoid division by zero
    short_term_sma = sum(prices[:20]) / min(20, len(prices))
    long_term_sma = sum(prices) / len(prices)
    return short_term_sma, long_term_sma

def generate_buy_sell_signals(symbol: str) -> str:
    """
    Generate buy/sell signals based on moving averages.

    Args:
    - symbol (str): Stock symbol

    Returns:
    - str: "BUY", "SELL", or "HOLD"
    """
    short_sma, long_sma = calculate_moving_averages(symbol)
    if short_sma > long_sma:
        return "BUY"
    elif short_sma < long_sma:
        return "SELL"
    else:
        return "HOLD"

def main() -> None:
    symbol = "AAPL"  # Example stock symbol
    price_data = fetch_stock_price(symbol)
    if price_data:
        store_historical_data(symbol, price_data)
        signal = generate_buy_sell_signals(symbol)
        logger.info(f"Signal for {symbol}: {signal}")
    else:
        logger.error(f"Failed to fetch price data for {symbol}")

if __name__ == "__main__":
    main()