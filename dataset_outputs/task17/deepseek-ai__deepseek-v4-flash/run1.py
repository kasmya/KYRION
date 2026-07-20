import os
import sqlite3
import time
from typing import List, Optional, Tuple

import pandas as pd
import requests


class StockPriceTracker:
    """
    A stock price tracker that fetches real-time prices from Alpha Vantage API,
    stores historical data in SQLite, calculates moving averages, and generates
    buy/sell signals based on crossover strategy.
    """

    DB_PATH = "stock_prices.db"
    API_BASE_URL = "https://www.alphavantage.co/query"
    # Sleep to respect API rate limit (5 calls per minute for free tier)
    API_CALL_INTERVAL = 15  # seconds

    def __init__(self, api_key: Optional[str] = None) -> None:
        """
        Initialize the tracker with an API key.

        Args:
            api_key: Alpha Vantage API key. If None, reads from ALPHA_VANTAGE_API_KEY env var.
        Raises:
            ValueError: If no API key is provided or found in environment.
        """
        self.api_key = api_key or os.environ.get("ALPHA_VANTAGE_API_KEY")
        if not self.api_key:
            raise ValueError(
                "API key must be provided or set in ALPHA_VANTAGE_API_KEY environment variable."
            )
        self._init_db()

    def _init_db(self) -> None:
        """Create database and table if they don't exist."""
        with sqlite3.connect(self.DB_PATH) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS stock_prices (
                    ticker TEXT NOT NULL,
                    date TEXT NOT NULL,
                    open REAL,
                    high REAL,
                    low REAL,
                    close REAL,
                    volume INTEGER,
                    PRIMARY KEY (ticker, date)
                );
            """)
            conn.commit()

    def _insert_prices(self, ticker: str, records: List[dict]) -> None:
        """
        Insert daily price records into the database.

        Args:
            ticker: Stock symbol.
            records: List of dicts with keys: date, open, high, low, close, volume.
        """
        with sqlite3.connect(self.DB_PATH) as conn:
            for rec in records:
                conn.execute(
                    """INSERT OR IGNORE INTO stock_prices
                       (ticker, date, open, high, low, close, volume)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        ticker.upper(),
                        rec["date"],
                        rec["open"],
                        rec["high"],
                        rec["low"],
                        rec["close"],
                        rec["volume"],
                    ),
                )
            conn.commit()

    def fetch_and_store(self, ticker: str, outputsize: str = "compact") -> None:
        """
        Fetch daily stock data from Alpha Vantage and store in database.

        Args:
            ticker: Stock symbol (e.g., 'AAPL').
            outputsize: 'compact' (last 100 days) or 'full' (up to 20 years).

        Raises:
            requests.RequestException: If API request fails.
            ValueError: If API response indicates error or rate limit.
        """
        params = {
            "function": "TIME_SERIES_DAILY_ADJUSTED",
            "symbol": ticker,
            "apikey": self.api_key,
            "outputsize": outputsize,
        }
        try:
            response = requests.get(self.API_BASE_URL, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            raise requests.RequestException(f"API request failed: {e}")
        except ValueError as e:
            raise ValueError(f"Invalid JSON response: {e}")

        if "Time Series (Daily)" not in data:
            error_msg = data.get("Note", data.get("Information", "Unknown API error"))
            raise ValueError(f"API error: {error_msg}")

        records = []
        for date_str, values in data["Time Series (Daily)"].items():
            try:
                record = {
                    "date": date_str,
                    "open": float(values["1. open"]),
                    "high": float(values["2. high"]),
                    "low": float(values["3. low"]),
                    "close": float(values["4. close"]),
                    "volume": int(values["6. volume"]),
                }
                records.append(record)
            except (KeyError, ValueError, TypeError) as e:
                # Skip malformed records
                continue

        self._insert_prices(ticker, records)
        # Respect API rate limit
        print(f"Fetched {len(records)} records for {ticker}.")
        time.sleep(self.API_CALL_INTERVAL)

    def get_moving_average(
        self, ticker: str, window: int = 20, start_date: Optional[str] = None
    ) -> pd.Series:
        """
        Calculate simple moving average of closing prices.

        Args:
            ticker: Stock symbol.
            window: Window size for moving average.
            start_date: Optional cutoff date (inclusive) in 'YYYY-MM-DD' format.

        Returns:
            pd.Series with moving average values indexed by date.
        """
        query = "SELECT date, close FROM stock_prices WHERE ticker = ?"
        params: Tuple = (ticker.upper(),)
        if start_date:
            query += " AND date >= ?"
            params += (start_date,)
        query += " ORDER BY date ASC"

        with sqlite3.connect(self.DB_PATH) as conn:
            df = pd.read_sql_query(query, conn, params=params)

        if df.empty:
            return pd.Series(dtype=float)

        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date")
        return df["close"].rolling(window=window).mean()

    def generate_signals(
        self,
        ticker: str,
        short_window: int = 10,
        long_window: int = 50,
        start_date: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        Generate buy/sell signals based on moving average crossover strategy.

        Buy signal when short-term MA crosses above long-term MA.
        Sell signal when short-term MA crosses below long-term MA.

        Args:
            ticker: Stock symbol.
            short_window: Window for short moving average.
            long_window: Window for long moving average.
            start_date: Optional cutoff date.

        Returns:
            DataFrame with columns: date, close, short_ma, long_ma, signal (1=buy, -1=sell, 0=hold).
        """
        # Fetch closing prices
        query = "SELECT date, close FROM stock_prices WHERE ticker = ?"
        params: Tuple = (ticker.upper(),)
        if start_date:
            query += " AND date >= ?"
            params += (start_date,)
        query += " ORDER BY date ASC"

        with sqlite3.connect(self.DB_PATH) as conn:
            df = pd.read_sql_query(query, conn, params=params)

        if df.empty:
            print(f"No data found for {ticker}.")
            return pd.DataFrame()

        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date")

        df["short_ma"] = df["close"].rolling(window=short_window).mean()
        df["long_ma"] = df["close"].rolling(window=long_window).mean()

        # Generate signals (1=buy, -1=sell)
        df["signal"] = 0
        df.loc[df["short_ma"] > df["long_ma"], "signal"] = 1
        df.loc[df["short_ma"] < df["long_ma"], "signal"] = -1

        # Remove rows with NaN in MA columns
        df = df.dropna(subset=["short_ma", "long_ma"])

        # Identify crossover points where signal changes
        df["signal_change"] = df["signal"].diff()
        buy_signals = df[df["signal_change"] == 2]  # from -1 to 1
        sell_signals = df[df["signal_change"] == -2]  # from 1 to -1

        # Keep only crossover days (set others to 0)
        df["final_signal"] = 0
        df.loc[buy_signals.index, "final_signal"] = 1
        df.loc[sell_signals.index, "final_signal"] = -1

        result = df[["close", "short_ma", "long_ma", "final_signal"]].rename(
            columns={"final_signal": "signal"}
        )
        return result.reset_index()


# Example usage (requires setting ALPHA_VANTAGE_API_KEY environment variable)
if __name__ == "__main__":
    try:
        tracker = StockPriceTracker()
        # Fetch data for a stock (adjust ticker as needed)
        tracker.fetch_and_store("AAPL", outputsize="compact")

        # Calculate 20-day moving average
        ma = tracker.get_moving_average("AAPL", window=20)
        print("20-day MA (last 5):")
        print(ma.tail())

        # Generate signals using 10/50 crossover
        signals = tracker.generate_signals("AAPL", short_window=10, long_window=50)
        print("\nSignal Table (last 10 rows):")
        print(signals.tail(10))

        # Show recent buy/sell signals
        recent_signals = signals[signals["signal"] != 0]
        if not recent_signals.empty:
            print("\nRecent Buy/Sell Signals:")
            print(recent_signals.tail())
        else:
            print("No crossover signals found in the data.")

    except ValueError as e:
        print(f"Configuration error: {e}")
    except requests.RequestException as e:
        print(f"Network or API error: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")