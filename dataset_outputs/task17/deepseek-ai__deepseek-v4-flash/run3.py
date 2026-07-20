import os
import sqlite3
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import pandas as pd
import requests


class StockPriceTracker:
    """
    A stock price tracker that fetches real-time prices from an API,
    stores historical data in a SQLite database, computes moving averages,
    and generates buy/sell signals based on crossovers.
    """

    def __init__(self, symbol: str, db_path: str = "stock_data.db") -> None:
        """
        Initialize the tracker.

        Args:
            symbol: Stock ticker symbol (e.g., 'AAPL').
            db_path: Path to the SQLite database file.

        Raises:
            ValueError: If API key is not set in environment.
        """
        self.api_key = os.environ.get("STOCK_API_KEY")
        if not self.api_key:
            raise ValueError(
                "API key not found. Please set the STOCK_API_KEY environment variable."
            )
        self.symbol = symbol.upper()
        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        """Create the database table if it doesn't exist."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS stock_prices (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    price REAL NOT NULL,
                    timestamp TEXT NOT NULL,
                    volume INTEGER,
                    UNIQUE(symbol, timestamp)
                )
                """
            )
            conn.commit()

    def _fetch_price(self, symbol: str) -> Dict:
        """
        Fetch the latest stock price from Alpha Vantage API.

        Args:
            symbol: Stock ticker.

        Returns:
            Dict with keys: 'price', 'timestamp', 'volume'.

        Raises:
            requests.RequestException: On network or API errors.
            ValueError: If API response indicates an error.
        """
        url = "https://www.alphavantage.co/query"
        params = {
            "function": "TIME_SERIES_INTRADAY",
            "symbol": symbol,
            "interval": "1min",
            "apikey": self.api_key,
        }
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        if "Time Series (1min)" not in data:
            error_message = data.get("Note", data.get("Error Message", "Unknown error"))
            raise ValueError(f"API error: {error_message}")

        # Get the most recent data point
        time_series = data["Time Series (1min)"]
        latest_timestamp = max(time_series.keys())
        latest_data = time_series[latest_timestamp]

        return {
            "symbol": self.symbol,
            "price": float(latest_data["4. close"]),
            "timestamp": latest_timestamp,
            "volume": int(latest_data["5. volume"]),
        }

    def _store_price(self, price_data: Dict) -> None:
        """
        Store a price data point into the database.

        Args:
            price_data: Dict with keys 'symbol', 'price', 'timestamp', 'volume'.
        """
        with sqlite3.connect(self.db_path) as conn:
            try:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO stock_prices (symbol, price, timestamp, volume)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        price_data["symbol"],
                        price_data["price"],
                        price_data["timestamp"],
                        price_data["volume"],
                    ),
                )
                conn.commit()
            except sqlite3.Error as e:
                print(f"Database error while storing price: {e}")

    def get_historical_data(self, days: int = 100) -> pd.DataFrame:
        """
        Retrieve historical price data from the database.

        Args:
            days: Number of past days to include.

        Returns:
            DataFrame with columns: 'timestamp', 'price', 'volume'.
        """
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        query = """
            SELECT timestamp, price, volume
            FROM stock_prices
            WHERE symbol = ? AND timestamp >= ?
            ORDER BY timestamp ASC
        """
        with sqlite3.connect(self.db_path) as conn:
            df = pd.read_sql_query(query, conn, params=(self.symbol, cutoff))
        return df

    def compute_moving_averages(
        self,
        data: pd.DataFrame,
        short_window: int = 5,
        long_window: int = 20,
    ) -> pd.DataFrame:
        """
        Add short and long simple moving averages to the DataFrame.

        Args:
            data: DataFrame with a 'price' column.
            short_window: Window for short MA.
            long_window: Window for long MA.

        Returns:
            DataFrame with added columns 'short_ma' and 'long_ma'.
        """
        result = data.copy()
        result["short_ma"] = result["price"].rolling(window=short_window).mean()
        result["long_ma"] = result["price"].rolling(window=long_window).mean()
        return result

    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Generate buy/sell signals based on moving average crossover.

        Signal rules:
            - Buy when short_ma crosses above long_ma
            - Sell when short_ma crosses below long_ma

        Args:
            data: DataFrame with columns 'short_ma' and 'long_ma'.

        Returns:
            DataFrame with added 'signal' column: 1=buy, -1=sell, 0=none.
        """
        result = data.copy()
        result["signal"] = 0

        # Determine crossovers
        result.loc[
            (result["short_ma"].notna()) & (result["long_ma"].notna()),
            "ma_diff",
        ] = result["short_ma"] - result["long_ma"]

        # Signal when the sign of ma_diff changes
        result["signal"] = result["ma_diff"].apply(
            lambda x: 1 if x > 0 else (-1 if x < 0 else 0)
        )
        result["signal"] = result["signal"] - result["signal"].shift(1)
        # Only keep the first change after a crossover
        result["signal"] = result["signal"].apply(
            lambda x: x if x in (1, -1) else 0
        )
        result.drop(columns=["ma_diff"], inplace=True)
        return result

    def run(self, retries: int = 3) -> None:
        """
        Execute a full cycle: fetch, store, compute, and print signals.

        Args:
            retries: Number of API call retries on failure.
        """
        # Fetch and store current price
        for attempt in range(retries):
            try:
                price_data = self._fetch_price(self.symbol)
                self._store_price(price_data)
                print(
                    f"Fetched price for {self.symbol}: ${price_data['price']:.2f} "
                    f"at {price_data['timestamp']}"
                )
                break
            except (requests.RequestException, ValueError) as e:
                print(f"Attempt {attempt+1} failed: {e}")
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)  # Exponential backoff
                else:
                    print("All retries exhausted. Skipping this cycle.")
                    return

        # Retrieve historical data and analyze
        try:
            historical = self.get_historical_data(days=30)
            if historical.empty:
                print("Not enough historical data to compute signals.")
                return

            data_with_ma = self.compute_moving_averages(historical)
            signals = self.generate_signals(data_with_ma)

            latest_row = signals.iloc[-1]
            if signals["signal"].notna().any():
                last_signal = signals[signals["signal"] != 0].iloc[-1]
                signal_text = "BUY" if last_signal["signal"] == 1 else "SELL"
                print(
                    f"Latest signal: {signal_text} "
                    f"(short MA: {latest_row['short_ma']:.2f}, "
                    f"long MA: {latest_row['long_ma']:.2f})"
                )
            else:
                print("No crossover signal detected.")
        except Exception as e:
            print(f"Error during analysis: {e}")


def main() -> None:
    """Example usage of StockPriceTracker."""
    tracker = StockPriceTracker(symbol="AAPL", db_path="stock_data.db")
    # Run periodically or once
    tracker.run()


if __name__ == "__main__":
    # Set your API key before running:
    # export STOCK_API_KEY='YOUR_ALPHA_VANTAGE_API_KEY'
    main()