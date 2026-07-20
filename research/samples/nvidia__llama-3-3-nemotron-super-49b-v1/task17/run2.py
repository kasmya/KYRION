import requests
import pandas as pd
from datetime import datetime, timedelta
import sqlite3
from typing import Tuple, Dict, List

# Configuration
API_KEY = "YOUR_API_KEY_HERE"  # Replace with your API key
API_URL = f"https://www.alphavantage.co/query?function=TIME_SERIES_INTRADAY&symbol={}&interval=1min&apikey={API_KEY}&datatype=json"
DB_NAME = "stock_tracker.db"

class StockTracker:
    def __init__(self, symbol: str):
        """
        Initialize the StockTracker with a stock symbol.

        :param symbol: Stock symbol (e.g., AAPL, GOOG)
        """
        self.symbol = symbol
        self.conn = sqlite3.connect(DB_NAME)
        self.cursor = self.conn.cursor()
        self.cursor.execute("""CREATE TABLE IF NOT EXISTS {} (
                                date TEXT PRIMARY KEY,
                                price REAL
                                )""".format(symbol))
        self.conn.commit()

    def fetch_real_time_price(self) -> float:
        """
        Fetch the real-time stock price from the API.

        :return: Current stock price
        :raises requests.RequestException: If the API request fails
        """
        try:
            response = requests.get(API_URL.format(self.symbol))
            response.raise_for_status()
            data = response.json()
            return float(data["Time Series (1min)"][list(data["Time Series (1min)"].keys())[0]]["4. close"])
        except requests.RequestException as e:
            print(f"API request failed: {e}")
            raise

    def store_historical_data(self, days: int = 30) -> None:
        """
        Store historical stock prices in the database for the given number of days.

        :param days: Number of days to fetch historical data for
        """
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        params = {
            "function": "TIME_SERIES_DAILY",
            "symbol": self.symbol,
            "outputsize": "full",
            "apikey": API_KEY,
            "datatype": "json"
        }
        try:
            response = requests.get("https://www.alphavantage.co/query", params=params)
            response.raise_for_status()
            data = response.json()
            for date, values in data["Time Series (Daily)"].items():
                if date >= start_date:
                    self.cursor.execute("INSERT OR REPLACE INTO {} VALUES (?, ?)".format(self.symbol), (date, float(values["4. close"])))
            self.conn.commit()
        except requests.RequestException as e:
            print(f"API request failed: {e}")

    def calculate_moving_averages(self, days: List[int] = [7, 14, 21]) -> Dict[int, float]:
        """
        Calculate moving averages for the given number of days.

        :param days: List of days to calculate moving averages for
        :return: Dictionary with moving averages for each day
        """
        self.cursor.execute("SELECT price FROM {} ORDER BY date DESC LIMIT {}".format(self.symbol, max(days)))
        prices = [row[0] for row in self.cursor.fetchall()]
        mas = {}
        for day in days:
            if len(prices) >= day:
                mas[day] = sum(prices[:day]) / day
            else:
                mas[day] = None  # Not enough data
        return mas

    def generate_buy_sell_signals(self, mas: Dict[int, float]) -> Tuple[bool, bool]:
        """
        Generate buy/sell signals based on moving averages.

        :param mas: Dictionary with moving averages
        :return: Tuple containing buy and sell signals
        """
        # Simple example: Buy if short MA > long MA, Sell if short MA < long MA
        short_ma, long_ma = sorted(mas.items())[:2]
        buy_signal = short_ma[1] is not None and long_ma[1] is not None and short_ma[1] > long_ma[1]
        sell_signal = short_ma[1] is not None and long_ma[1] is not None and short_ma[1] < long_ma[1]
        return buy_signal, sell_signal

    def close(self) -> None:
        """
        Close the database connection.
        """
        self.conn.close()


def main():
    tracker = StockTracker("AAPL")
    try:
        current_price = tracker.fetch_real_time_price()
        print(f"Current Price (AAPL): {current_price:.2f}")
        
        tracker.store_historical_data()
        mas = tracker.calculate_moving_averages()
        print("Moving Averages (AAPL):", mas)
        
        buy, sell = tracker.generate_buy_sell_signals(mas)
        print(f"Signals (AAPL): Buy={buy}, Sell={sell}")
    finally:
        tracker.close()


if __name__ == "__main__":
    main()