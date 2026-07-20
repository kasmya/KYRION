import requests
import pandas as pd
from typing import Dict, List
from datetime import datetime, timedelta
import sqlite3
from sqlite3 import Error

class StockTracker:
    """
    A class to track stock prices, calculate moving averages and generate buy/sell signals.
    
    Attributes:
    ----------
    api_key : str
        API key for stock price API
    stock_symbol : str
        Symbol of the stock to track
    db_name : str
        Name of the SQLite database file
    """

    def __init__(self, api_key: str, stock_symbol: str, db_name: str):
        """
        Initializes the StockTracker class.

        Parameters:
        ----------
        api_key : str
            API key for stock price API
        stock_symbol : str
            Symbol of the stock to track
        db_name : str
            Name of the SQLite database file
        """
        self.api_key = api_key
        self.stock_symbol = stock_symbol
        self.db_name = db_name
        self.create_table()

    def create_table(self) -> None:
        """
        Creates a table in the SQLite database to store historical stock prices.
        """
        try:
            conn = sqlite3.connect(self.db_name)
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS stock_prices (
                    date TEXT PRIMARY KEY,
                    open REAL,
                    high REAL,
                    low REAL,
                    close REAL
                );
            """)
            conn.commit()
        except Error as e:
            print(e)

    def fetch_stock_price(self) -> Dict[str, float]:
        """
        Fetches the current stock price from the API.

        Returns:
        -------
        Dict[str, float]
            Dictionary containing the current stock price
        """
        try:
            response = requests.get(
                f"https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol={self.stock_symbol}&apikey={self.api_key}"
            )
            response.raise_for_status()
            data = response.json()
            return {
                "open": float(data["Global Quote"]["02. open"]),
                "high": float(data["Global Quote"]["03. high"]),
                "low": float(data["Global Quote"]["04. low"]),
                "close": float(data["Global Quote"]["05. price"]),
            }
        except requests.exceptions.RequestException as e:
            print(f"API request failed: {e}")
            return {}

    def store_historical_data(self, data: Dict[str, float]) -> None:
        """
        Stores the historical stock price data in the SQLite database.

        Parameters:
        ----------
        data : Dict[str, float]
            Dictionary containing the historical stock price data
        """
        try:
            conn = sqlite3.connect(self.db_name)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO stock_prices (date, open, high, low, close)
                VALUES (?, ?, ?, ?, ?);
            """, (datetime.now().strftime("%Y-%m-%d"), data["open"], data["high"], data["low"], data["close"]))
            conn.commit()
        except Error as e:
            print(e)

    def calculate_moving_averages(self) -> List[float]:
        """
        Calculates the moving averages of the stock price.

        Returns:
        -------
        List[float]
            List of moving averages
        """
        try:
            conn = sqlite3.connect(self.db_name)
            cursor = conn.cursor()
            cursor.execute("SELECT close FROM stock_prices ORDER BY date DESC LIMIT 10;")
            rows = cursor.fetchall()
            close_prices = [row[0] for row in rows]
            moving_averages = []
            for i in range(len(close_prices)):
                moving_average = sum(close_prices[:i+1]) / (i+1)
                moving_averages.append(moving_average)
            return moving_averages
        except Error as e:
            print(e)
            return []

    def generate_buy_sell_signals(self, moving_averages: List[float]) -> str:
        """
        Generates buy/sell signals based on the moving averages.

        Parameters:
        ----------
        moving_averages : List[float]
            List of moving averages

        Returns:
        -------
        str
            Buy/sell signal
        """
        if len(moving_averages) < 2:
            return "No signal"
        if moving_averages[-1] > moving_averages[-2]:
            return "Buy"
        else:
            return "Sell"

def main() -> None:
    api_key = "YOUR_API_KEY"
    stock_symbol = "AAPL"
    db_name = "stock_prices.db"
    tracker = StockTracker(api_key, stock_symbol, db_name)
    current_price = tracker.fetch_stock_price()
    tracker.store_historical_data(current_price)
    moving_averages = tracker.calculate_moving_averages()
    signal = tracker.generate_buy_sell_signals(moving_averages)
    print(f"Current price: {current_price}")
    print(f"Moving averages: {moving_averages}")
    print(f"Signal: {signal}")

if __name__ == "__main__":
    main()