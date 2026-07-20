import requests
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
from sqlite3 import Error, connect
import logging
import os

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class StockTracker:
    def __init__(self, api_key: str, db_path: str):
        """
        Initializes the stock tracker.

        Args:
        api_key (str): The API key for the stock price API.
        db_path (str): The path to the SQLite database.
        """
        self.api_key = api_key
        self.db_path = db_path
        self.conn = None

    def connect_to_db(self) -> None:
        """
        Connects to the SQLite database.
        """
        try:
            self.conn = connect(self.db_path)
            logger.info("Connected to database.")
        except Error as e:
            logger.error(f"Failed to connect to database: {e}")

    def fetch_stock_price(self, symbol: str) -> Dict[str, str]:
        """
        Fetches the current stock price from the API.

        Args:
        symbol (str): The stock symbol.

        Returns:
        Dict[str, str]: A dictionary containing the stock price and timestamp.
        """
        url = f"https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol={symbol}&apikey={self.api_key}"
        try:
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()
            price = data["Global Quote"]["05. price"]
            timestamp = data["Global Quote"]["07. latest trading day"]
            return {"price": price, "timestamp": timestamp}
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch stock price: {e}")
            return None

    def store_historical_data(self, symbol: str, price_data: Dict[str, str]) -> None:
        """
        Stores the historical stock price data in the database.

        Args:
        symbol (str): The stock symbol.
        price_data (Dict[str, str]): A dictionary containing the stock price and timestamp.
        """
        if self.conn is None:
            self.connect_to_db()
        cursor = self.conn.cursor()
        query = """
            INSERT INTO stock_prices (symbol, price, timestamp)
            VALUES (?, ?, ?)
        """
        try:
            cursor.execute(query, (symbol, price_data["price"], price_data["timestamp"]))
            self.conn.commit()
            logger.info("Stored historical data.")
        except Error as e:
            logger.error(f"Failed to store historical data: {e}")

    def calculate_moving_averages(self, symbol: str, window: int) -> List[Tuple[str, str]]:
        """
        Calculates the moving averages of the stock price.

        Args:
        symbol (str): The stock symbol.
        window (int): The moving average window.

        Returns:
        List[Tuple[str, str]]: A list of tuples containing the moving average and timestamp.
        """
        if self.conn is None:
            self.connect_to_db()
        cursor = self.conn.cursor()
        query = """
            SELECT price, timestamp
            FROM stock_prices
            WHERE symbol = ?
            ORDER BY timestamp DESC
            LIMIT ?
        """
        try:
            cursor.execute(query, (symbol, window))
            rows = cursor.fetchall()
            moving_averages = []
            for i in range(len(rows)):
                avg_price = sum(row[0] for row in rows[:i+1]) / (i+1)
                moving_averages.append((avg_price, rows[i][1]))
            return moving_averages
        except Error as e:
            logger.error(f"Failed to calculate moving averages: {e}")
            return None

    def generate_buy_sell_signals(self, symbol: str, window: int) -> Tuple[str, str]:
        """
        Generates buy/sell signals based on the moving averages.

        Args:
        symbol (str): The stock symbol.
        window (int): The moving average window.

        Returns:
        Tuple[str, str]: A tuple containing the buy/sell signal and timestamp.
        """
        moving_averages = self.calculate_moving_averages(symbol, window)
        if moving_averages is None:
            return None
        latest_avg = moving_averages[0][0]
        prev_avg = moving_averages[1][0]
        if latest_avg > prev_avg:
            return ("Buy", moving_averages[0][1])
        elif latest_avg < prev_avg:
            return ("Sell", moving_averages[0][1])
        else:
            return ("Hold", moving_averages[0][1])

def main():
    api_key = os.environ.get("API_KEY")
    db_path = "stock_prices.db"
    stock_tracker = StockTracker(api_key, db_path)
    stock_tracker.connect_to_db()
    symbol = "AAPL"
    price_data = stock_tracker.fetch_stock_price(symbol)
    if price_data is not None:
        stock_tracker.store_historical_data(symbol, price_data)
        moving_averages = stock_tracker.calculate_moving_averages(symbol, 50)
        signal = stock_tracker.generate_buy_sell_signals(symbol, 50)
        if signal is not None:
            logger.info(f"Buy/Sell Signal: {signal[0]} at {signal[1]}")

if __name__ == "__main__":
    main()