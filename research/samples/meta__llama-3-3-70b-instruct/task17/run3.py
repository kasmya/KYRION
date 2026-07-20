import requests
import pandas as pd
from typing import Dict, List
import sqlite3
import logging
from logging.handlers import RotatingFileHandler

# Set up logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = RotatingFileHandler('stock_tracker.log', maxBytes=1000000, backupCount=1)
logger.addHandler(handler)

def fetch_stock_price(api_key: str, stock_symbol: str) -> float:
    """
    Fetches the current stock price from the API.

    Args:
    - api_key (str): The API key for authentication.
    - stock_symbol (str): The symbol of the stock to fetch.

    Returns:
    - float: The current stock price.

    Raises:
    - requests.exceptions.RequestException: If the API request fails.
    """
    try:
        response = requests.get(f'https://api.example.com/stock/{stock_symbol}?api_key={api_key}')
        response.raise_for_status()
        return response.json()['price']
    except requests.exceptions.RequestException as e:
        logger.error(f'Failed to fetch stock price: {e}')
        raise

def store_historical_data(db_path: str, stock_symbol: str, price: float) -> None:
    """
    Stores the historical stock price data in the database.

    Args:
    - db_path (str): The path to the SQLite database file.
    - stock_symbol (str): The symbol of the stock to store.
    - price (float): The current stock price.

    Raises:
    - sqlite3.Error: If the database operation fails.
    """
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('CREATE TABLE IF NOT EXISTS stock_prices (symbol TEXT, price REAL, timestamp TEXT DEFAULT CURRENT_TIMESTAMP)')
            cursor.execute('INSERT INTO stock_prices (symbol, price) VALUES (?, ?)', (stock_symbol, price))
            conn.commit()
    except sqlite3.Error as e:
        logger.error(f'Failed to store historical data: {e}')
        raise

def calculate_moving_average(db_path: str, stock_symbol: str, window_size: int) -> float:
    """
    Calculates the moving average of the stock price over a given window size.

    Args:
    - db_path (str): The path to the SQLite database file.
    - stock_symbol (str): The symbol of the stock to calculate.
    - window_size (int): The size of the moving average window.

    Returns:
    - float: The moving average of the stock price.

    Raises:
    - sqlite3.Error: If the database operation fails.
    """
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT price FROM stock_prices WHERE symbol = ? ORDER BY timestamp DESC LIMIT ?', (stock_symbol, window_size))
            prices = [row[0] for row in cursor.fetchall()]
            return sum(prices) / len(prices)
    except sqlite3.Error as e:
        logger.error(f'Failed to calculate moving average: {e}')
        raise

def generate_buy_sell_signals(db_path: str, stock_symbol: str, short_window_size: int, long_window_size: int) -> Dict[str, bool]:
    """
    Generates buy/sell signals based on the moving averages.

    Args:
    - db_path (str): The path to the SQLite database file.
    - stock_symbol (str): The symbol of the stock to generate signals for.
    - short_window_size (int): The size of the short moving average window.
    - long_window_size (int): The size of the long moving average window.

    Returns:
    - Dict[str, bool]: A dictionary containing the buy and sell signals.
    """
    try:
        short_ma = calculate_moving_average(db_path, stock_symbol, short_window_size)
        long_ma = calculate_moving_average(db_path, stock_symbol, long_window_size)
        return {
            'buy': short_ma > long_ma,
            'sell': short_ma < long_ma
        }
    except Exception as e:
        logger.error(f'Failed to generate buy/sell signals: {e}')
        raise

def main() -> None:
    api_key = 'YOUR_API_KEY'
    stock_symbol = 'AAPL'
    db_path = 'stock_prices.db'
    short_window_size = 50
    long_window_size = 200

    current_price = fetch_stock_price(api_key, stock_symbol)
    store_historical_data(db_path, stock_symbol, current_price)
    signals = generate_buy_sell_signals(db_path, stock_symbol, short_window_size, long_window_size)

    print(f'Current price: {current_price}')
    print(f'Buy signal: {signals["buy"]}')
    print(f'Sell signal: {signals["sell"]}')

if __name__ == '__main__':
    main()