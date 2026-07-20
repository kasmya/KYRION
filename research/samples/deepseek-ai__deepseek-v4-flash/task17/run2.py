import os
import sqlite3
import time
from datetime import datetime, timezone
from typing import List, Optional, Tuple, Dict, Any

import pandas as pd
import requests


class StockTracker:
    """
    A real-time stock price tracker that fetches prices from Alpha Vantage API,
    stores historical data in SQLite, calculates moving averages, and generates
    buy/sell signals based on moving average crossovers.
    """

    # Default API base URL
    BASE_URL = "https://www.alphavantage.co/query"

    def __init__(self, db_path: str = "stock_prices.db", api_key: Optional[str] = None) -> None:
        """
        Initialize the tracker with a database file and an API key.

        Args:
            db_path: Path to the SQLite database file.
            api_key: Alpha Vantage API key. If None, reads from environment
                     variable 'ALPHA_VANTAGE_API_KEY'.
        """
        self.db_path = db_path
        self.api_key = api_key or os.getenv("ALPHA_VANTAGE_API_KEY")
        if not self.api_key:
            raise ValueError(
                "API key is required. Provide it as argument or set "
                "ALPHA_VANTAGE_API_KEY environment variable."
            )
        self._init_db()

    def _init_db(self) -> None:
        """Create the necessary database table if it does not exist."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS stock_prices (
                    symbol TEXT NOT NULL,
                    price REAL NOT NULL,
                    timestamp TEXT NOT NULL,
                    PRIMARY KEY (symbol, timestamp)
                )
                """
            )
            conn.commit()

    def fetch_price(self, symbol: str) -> Tuple[float, str]:
        """
        Fetch the latest real-time stock price for a given symbol from Alpha Vantage.

        Args:
            symbol: Stock ticker symbol (e.g., 'AAPL').

        Returns:
            A tuple (price, timestamp) where timestamp is an ISO-8601 string.

        Raises:
            ConnectionError: If the API request fails.
            ValueError: If the response indicates an error or non-200 status.
        """
        params = {
            "function": "GLOBAL_QUOTE",
            "symbol": symbol.upper(),
            "apikey": self.api_key,
        }
        try:
            response = requests.get(self.BASE_URL, params=params, timeout=10)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            raise ConnectionError(f"Failed to fetch price for {symbol}: {e}") from e

        data = response.json()
        # Check for API error messages
        if "Error Message" in data:
            raise ValueError(f"API error for {symbol}: {data['Error Message']}")
        if "Note" in data:
            # Rate limit note - log but still try to parse if possible
            print(f"API note: {data['Note']}")

        quote = data.get("Global Quote")
        if not quote:
            raise ValueError(f"No 'Global Quote' found for {symbol} in API response.")

        try:
            price = float(quote["05. price"])
            timestamp_str = quote["07. latest trading day"]
            # Append time as midnight UTC to match typical daily data
            timestamp = f"{timestamp_str}T00:00:00"
        except (KeyError, ValueError, TypeError) as e:
            raise ValueError(f"Unexpected response format for {symbol}: {e}") from e

        return price, timestamp

    def store_price(self, symbol: str, price: float, timestamp: str) -> None:
        """
        Store a stock price record in the database.

        Args:
            symbol: Stock ticker symbol.
            price: Stock price.
            timestamp: ISO-8601 timestamp string.
        """
        with sqlite3.connect(self.db_path) as conn:
            try:
                conn.execute(
                    "INSERT OR REPLACE INTO stock_prices (symbol, price, timestamp) VALUES (?, ?, ?)",
                    (symbol.upper(), price, timestamp),
                )
                conn.commit()
            except sqlite3.Error as e:
                raise RuntimeError(f"Failed to store price for {symbol}: {e}") from e

    def get_historical_data(self, symbol: str, days: int = 100) -> pd.DataFrame:
        """
        Retrieve historical price data for a symbol from the database.

        Args:
            symbol: Stock ticker symbol.
            days: Number of past days to retrieve (default 100).

        Returns:
            DataFrame with columns 'timestamp' (datetime), 'price' (float),
            sorted by timestamp ascending. If no data, empty DataFrame.
        """
        with sqlite3.connect(self.db_path) as conn:
            query = """
                SELECT timestamp, price FROM stock_prices
                WHERE symbol = ?
                ORDER BY timestamp DESC
                LIMIT ?
            """
            df = pd.read_sql_query(query, conn, params=(symbol.upper(), days))
        if df.empty:
            return df
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df.sort_values("timestamp").reset_index(drop=True)
        return df

    def calculate_moving_average(self, data: pd.DataFrame, window: int = 20) -> pd.Series:
        """
        Calculate simple moving average (SMA) of the price column.

        Args:
            data: DataFrame with a 'price' column.
            window: Rolling window size.

        Returns:
            Series of SMA values (length same as input, NaN for initial rows).
        """
        if "price" not in data.columns:
            raise ValueError("DataFrame must contain a 'price' column.")
        return data["price"].rolling(window=window).mean()

    def generate_signals(
        self,
        data: pd.DataFrame,
        short_window: int = 10,
        long_window: int = 30,
    ) -> List[Dict[str, Any]]:
        """
        Generate buy/sell signals based on short and long moving average crossovers.

        Args:
            data: DataFrame with 'timestamp' and 'price' columns.
            short_window: Window for short-term SMA.
            long_window: Window for long-term SMA.

        Returns:
            List of dicts with keys 'date', 'signal' ('BUY' or 'SELL'),
            and 'price'. Empty list if data insufficient.
        """
        if len(data) < max(short_window, long_window):
            return []

        data = data.copy()
        data["sma_short"] = self.calculate_moving_average(data, short_window)
        data["sma_long"] = self.calculate_moving_average(data, long_window)

        # Drop rows where either SMA is NaN
        data_clean = data.dropna(subset=["sma_short", "sma_long"]).reset_index(drop=True)

        signals = []
        prev_short = None
        prev_long = None
        for idx, row in data_clean.iterrows():
            if prev_short is not None and prev_long is not None:
                # Crossover detection
                if prev_short <= prev_long and row["sma_short"] > row["sma_long"]:
                    # Golden cross: short crosses above long
                    signals.append({
                        "date": row["timestamp"],
                        "signal": "BUY",
                        "price": row["price"],
                    })
                elif prev_short >= prev_long and row["sma_short"] < row["sma_long"]:
                    # Death cross: short crosses below long
                    signals.append({
                        "date": row["timestamp"],
                        "signal": "SELL",
                        "price": row["price"],
                    })
            prev_short = row["sma_short"]
            prev_long = row["sma_long"]

        return signals

    def run_full_cycle(self, symbol: str, days: int = 100) -> None:
        """
        Execute a complete cycle: fetch latest price, store it, retrieve history,
        compute moving averages, and print signals.

        Args:
            symbol: Stock ticker symbol.
            days: Number of past days for historical data retrieval.
        """
        # Step 1: fetch and store current price
        try:
            price, timestamp = self.fetch_price(symbol)
            print(f"Fetched {symbol}: {price} at {timestamp}")
        except (ConnectionError, ValueError) as e:
            print(f"Error fetching price for {symbol}: {e}")
            return

        try:
            self.store_price(symbol, price, timestamp)
            print(f"Stored {symbol}: {price} at {timestamp}")
        except RuntimeError as e:
            print(f"Error storing price: {e}")
            return

        # Step 2: retrieve historical data
        df = self.get_historical_data(symbol, days)
        if df.empty:
            print(f"No historical data available for {symbol}.")
            return

        # Step 3: generate signals
        signals = self.generate_signals(df, short_window=10, long_window=30)
        if signals:
            print(f"Signals for {symbol}:")
            for sig in signals:
                print(f"  {sig['date'].date()} - {sig['signal']} @ {sig['price']:.2f}")
        else:
            print(f"No signals generated for {symbol} (insufficient data?).")


def main() -> None:
    """
    Example usage of StockTracker.
    """
    tracker = StockTracker(db_path="stocks.db")
    tracker.run_full_cycle("IBM")


if __name__ == "__main__":
    main()