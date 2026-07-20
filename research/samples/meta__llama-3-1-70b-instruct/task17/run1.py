import logging
import os
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, Tuple

import pandas as pd
import requests

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Set up database connection
DB_NAME = "stock_prices.db"

def create_database():
    """Create the database schema if it does not exist."""
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS stock_prices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                price REAL NOT NULL,
                date TEXT NOT NULL
            );
            """
        )
        conn.commit()

def fetch_stock_price(symbol: str, api_key: str) -> float:
    """
    Fetch the current stock price from the API.

    Args:
        symbol (str): The stock symbol (e.g. "AAPL").
        api_key (str): The API key.

    Returns:
        float: The current stock price.

    Raises:
        requests.exceptions.RequestException: If the API request fails.
    """
    url = f"https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol={symbol}&apikey={api_key}"
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        return float(data["Global Quote"]["05. price"])
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to fetch stock price: {e}")
        raise

def store_historical_price(symbol: str, price: float) -> None:
    """
    Store the historical stock price in the database.

    Args:
        symbol (str): The stock symbol (e.g. "AAPL").
        price (float): The stock price.
    """
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO stock_prices (symbol, price, date)
            VALUES (?, ?, ?);
            """,
            (symbol, price, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        )
        conn.commit()

def get_historical_prices(symbol: str) -> pd.DataFrame:
    """
    Get the historical stock prices from the database.

    Args:
        symbol (str): The stock symbol (e.g. "AAPL").

    Returns:
        pd.DataFrame: The historical stock prices.
    """
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT price, date
            FROM stock_prices
            WHERE symbol = ?;
            """,
            (symbol,),
        )
        rows = cursor.fetchall()
        return pd.DataFrame(rows, columns=["price", "date"])

def calculate_moving_average(prices: pd.DataFrame, window: int) -> float:
    """
    Calculate the moving average of the stock prices.

    Args:
        prices (pd.DataFrame): The historical stock prices.
        window (int): The moving average window.

    Returns:
        float: The moving average.
    """
    return prices["price"].rolling(window).mean().iloc[-1]

def generate_buy_sell_signal(
    symbol: str, short_window: int, long_window: int, api_key: str
) -> Tuple[str, float]:
    """
    Generate a buy/sell signal based on the moving averages.

    Args:
        symbol (str): The stock symbol (e.g. "AAPL").
        short_window (int): The short moving average window.
        long_window (int): The long moving average window.
        api_key (str): The API key.

    Returns:
        Tuple[str, float]: The buy/sell signal and the current stock price.
    """
    current_price = fetch_stock_price(symbol, api_key)
    historical_prices = get_historical_prices(symbol)
    short_ma = calculate_moving_average(historical_prices, short_window)
    long_ma = calculate_moving_average(historical_prices, long_window)

    if short_ma > long_ma:
        return ("Buy", current_price)
    elif short_ma < long_ma:
        return ("Sell", current_price)
    else:
        return ("Hold", current_price)

def main():
    api_key = os.environ["API_KEY"]
    symbol = "AAPL"
    short_window = 20
    long_window = 50

    create_database()

    current_price = fetch_stock_price(symbol, api_key)
    store_historical_price(symbol, current_price)

    signal, current_price = generate_buy_sell_signal(
        symbol, short_window, long_window, api_key
    )
    logger.info(f"Signal: {signal}, Current Price: {current_price:.2f}")

if __name__ == "__main__":
    main()