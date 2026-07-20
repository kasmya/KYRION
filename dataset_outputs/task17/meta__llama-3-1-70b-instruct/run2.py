import requests
import pandas as pd
from sqlite3 import connect
from typing import Tuple, List
from enum import Enum
from datetime import datetime
from functools import lru_cache

# Constants
API_KEY = "YOUR_API_KEY"
API_URL = "https://www.alphavantage.co/query"
DATABASE_FILE = "stock_prices.db"
TABLE_NAME = "stock_prices"

class Signal(Enum):
    """Buy or sell signal"""
    BUY = "Buy"
    SELL = "Sell"

class StockPriceTracker:
    """Tracks stock prices and generates buy/sell signals"""
    
    def __init__(self, api_key: str, api_url: str, database_file: str):
        """
        Initializes the stock price tracker.

        Args:
            api_key (str): API key for Alpha Vantage.
            api_url (str): API URL for Alpha Vantage.
            database_file (str): File path for the SQLite database.
        """
        self.api_key = api_key
        self.api_url = api_url
        self.database_file = database_file
        self._create_table()

    def _create_table(self) -> None:
        """Creates the stock prices table in the database if it does not exist"""
        with connect(self.database_file) as conn:
            cursor = conn.cursor()
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
                    date TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    price REAL NOT NULL
                );
            """)

    def _fetch_price(self, symbol: str) -> float:
        """
        Fetches the current stock price from the API.

        Args:
            symbol (str): Stock symbol.

        Returns:
            float: Current stock price.

        Raises:
            Exception: If the API request fails.
        """
        try:
            params = {
                "function": "GLOBAL_QUOTE",
                "symbol": symbol,
                "apikey": self.api_key
            }
            response = requests.get(self.api_url, params=params)
            response.raise_for_status()
            data = response.json()
            return float(data["Global Quote"]["05. price"])
        except requests.RequestException as e:
            raise Exception("API request failed") from e

    def _store_price(self, symbol: str, price: float) -> None:
        """Stores the current stock price in the database"""
        date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with connect(self.database_file) as conn:
            cursor = conn.cursor()
            cursor.execute(f"""
                INSERT INTO {TABLE_NAME} (date, symbol, price)
                VALUES (?, ?, ?);
            """, (date, symbol, price))

    def _get_historical_prices(self, symbol: str) -> pd.DataFrame:
        """
        Retrieves historical stock prices from the database.

        Args:
            symbol (str): Stock symbol.

        Returns:
            pd.DataFrame: Historical stock prices.
        """
        with connect(self.database_file) as conn:
            return pd.read_sql_query(f"""
                SELECT date, price
                FROM {TABLE_NAME}
                WHERE symbol = ?;
            """, conn, params=(symbol,))

    def _calculate_moving_average(self, prices: pd.DataFrame, window: int) -> float:
        """
        Calculates the moving average of the stock prices.

        Args:
            prices (pd.DataFrame): Historical stock prices.
            window (int): Moving average window size.

        Returns:
            float: Moving average.
        """
        return prices["price"].rolling(window).mean().iloc[-1]

    def get_signal(self, symbol: str, window: int) -> Tuple[Signal, float]:
        """
        Generates a buy or sell signal based on the moving average.

        Args:
            symbol (str): Stock symbol.
            window (int): Moving average window size.

        Returns:
            Tuple[Signal, float]: Buy or sell signal and current stock price.
        """
        price = self._fetch_price(symbol)
        self._store_price(symbol, price)
        prices = self._get_historical_prices(symbol)
        if len(prices) < window:
            return Signal.SELL, price
        moving_average = self._calculate_moving_average(prices, window)
        if price > moving_average:
            return Signal.BUY, price
        else:
            return Signal.SELL, price

# Example usage
tracker = StockPriceTracker(API_KEY, API_URL, DATABASE_FILE)
signal, price = tracker.get_signal("AAPL", 5)
print(f"Signal: {signal.value}, Price: {price}")