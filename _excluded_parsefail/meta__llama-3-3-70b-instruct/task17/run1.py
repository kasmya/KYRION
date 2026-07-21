import requests
import pandas as pd
from typing import Dict, List
import sqlite3
import logging
from logging.handlers import RotatingFileHandler
import hashlib

# Set up logging
logger = logging.getLogger('stock_tracker')
logger.setLevel(logging.INFO)
handler = RotatingFileHandler('stock_tracker.log', maxBytes=100000, backupCount=1)
logger.addHandler(handler)

def fetch_stock_price(api_key: str, stock_symbol: str) -> Dict:
    """
    Fetch real-time stock price from API.

    Args:
        api_key (str): API key for authentication.
        stock_symbol (str): Stock symbol (e.g. 'AAPL').

    Returns:
        Dict: Dictionary containing stock price data.

    Raises:
        requests.exceptions.RequestException: If API request fails.
    """
    try:
        response = requests.get(f'https://api.example.com/stock/{stock_symbol}', headers={'Authorization': f'Bearer {api_key}'}))
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f'API request failed: {e}')
        raise

def store_historical_data(db_path: str, stock_symbol: str, stock_data: Dict) -> None:
    """
    Store historical stock data in SQLite database.

    Args:
        db_path (str): Path to SQLite database file.
        stock_symbol (str): Stock symbol (e.g. 'AAPL').
        stock_data (Dict): Dictionary containing stock price data.

    Returns:
        None
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS stock_data (date TEXT, symbol TEXT, price REAL)')
    cursor.execute('INSERT INTO stock_data VALUES (?, ?, ?)', (stock_data['date'], stock_symbol, stock_data['price']))
    conn.commit()
    conn.close()

def calculate_moving_average(db_path: str, stock_symbol: str, window_size: int) -> float:
    """
    Calculate moving average of stock price.

    Args:
        db_path (str): Path to SQLite database file.
        stock_symbol (str): Stock symbol (e.g. 'AAPL').
        window_size (int): Number of days to consider for moving average.

    Returns:
        float: Moving average of stock price.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute('SELECT price FROM stock_data WHERE symbol = ? ORDER BY date DESC LIMIT ?', (stock_symbol, window_size))
    prices = [row[0] for row in cursor.fetchall()]
    conn.close()
    return sum(prices) / len(prices)

def generate_buy_sell_signal(moving_average: float, current_price: float) -> str:
    """
    Generate buy/sell signal based on moving average and current price.

    Args:
        moving_average (float): Moving average of stock price.
        current_price (float): Current stock price.

    Returns:
        str: 'Buy' if current price is below moving average, 'Sell' otherwise.
    """
    if current_price < moving_average:
        return 'Buy'
    else:
        return 'Sell'

def main() -> None:
    api_key = 'your_api_key_here'
    stock_symbol = 'AAPL'
    db_path = 'stock_data.db'

    # Hash API key for secure storage
    hashed_api_key = hashlib.sha256(api_key.encode()).hexdigest()

    stock_data = fetch_stock_price(api_key, stock_symbol)
    store_historical_data(db_path, stock_symbol, stock_data)
    moving_average = calculate_moving_average(db_path, stock_symbol, 10)
    signal = generate_buy_sell_signal(moving_average, stock_data['price'])

    logger.info(f'Stock symbol: {stock_symbol}, Current price: {stock_data["price"]}, Moving average: {moving_average}, Signal: {signal}')

if __name__ == '__main__':
    main()