"""
stock_tracker.py

A simple stock price tracker that fetches real‑time quotes, stores them in a
SQLite database, computes moving averages, and generates buy/sell signals
based on a SMA crossover strategy.

Dependencies:
    - requests
    - pandas
"""

from __future__ import annotations

import os
import sqlite3
import logging
import time
from datetime import datetime, timezone
from typing import List, Tuple, Optional

import pandas as pd
import requests

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #

API_URL = "https://www.alphavantage.co/query"
API_KEY = os.getenv("ALPHAVANTAGE_API_KEY")  # Set this in the environment
DB_PATH = os.getenv("STOCK_TRACKER_DB", "stock_data.db")
REQUEST_TIMEOUT = 10  # seconds
MAX_RETRIES = 3
RETRY_BACKOFF = 2  # seconds

# --------------------------------------------------------------------------- #
# Logging setup (security‑aware – no API keys in logs)
# --------------------------------------------------------------------------- #

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("stock_tracker")


# --------------------------------------------------------------------------- #
# Core functionality
# --------------------------------------------------------------------------- #


class StockTracker:
    """
    Tracks a single stock symbol: fetches price data, persists it,
    calculates moving averages and derives trading signals.
    """

    def __init__(self, symbol: str, db_path: str = DB_PATH) -> None:
        """
        Initialize the tracker.

        Args:
            symbol: Upper‑case ticker symbol (e.g., "AAPL").
            db_path: Filesystem path to the SQLite database.
        """
        self.symbol = symbol.upper()
        self.db_path = db_path
        self._initialize_db()

    # --------------------------------------------------------------------- #
    # Database helpers
    # --------------------------------------------------------------------- #

    def _initialize_db(self) -> None:
        """Create the price table if it does not exist."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS prices (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    datetime_utc TEXT NOT NULL,
                    price REAL NOT NULL,
                    UNIQUE(symbol, datetime_utc)
                )
                """
            )
            conn.commit()
        logger.debug("Database initialized at %s", self.db_path)

    def _store_price(self, price: float, dt: datetime) -> None:
        """Insert a price record into the database."""
        utc_iso = dt.astimezone(timezone.utc).isoformat()
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO prices (symbol, datetime_utc, price)
                    VALUES (?, ?, ?)
                    """,
                    (self.symbol, utc_iso, price),
                )
                conn.commit()
            logger.info("Stored price %.4f for %s at %s", price, self.symbol, utc_iso)
        except sqlite3.Error as exc:
            logger.error("Failed to store price: %s", exc)

    def _load_prices(self) -> pd.DataFrame:
        """Load all stored prices for the symbol as a DataFrame."""
        query = """
            SELECT datetime_utc, price FROM prices
            WHERE symbol = ?
            ORDER BY datetime_utc ASC
        """
        try:
            df = pd.read_sql_query(
                query, sqlite3.connect(self.db_path), params=(self.symbol,)
            )
            df["datetime"] = pd.to_datetime(df["datetime_utc"], utc=True)
            df.set_index("datetime", inplace=True)
            df.sort_index(inplace=True)
            return df["price"]
        except Exception as exc:  # pragma: no cover
            logger.error("Error loading prices from DB: %s", exc)
            return pd.Series(dtype=float)

    # --------------------------------------------------------------------- #
    # API interaction
    # --------------------------------------------------------------------- #

    def _fetch_price(self) -> Tuple[Optional[float], Optional[datetime]]:
        """
        Retrieve the latest price from Alpha Vantage.

        Returns:
            (price, timestamp) on success; (None, None) on failure.
        """
        if not API_KEY:
            logger.error("Alpha Vantage API key not set in environment.")
            return None, None

        params = {
            "function": "TIME_SERIES_INTRADAY",
            "symbol": self.symbol,
            "interval": "1min",
            "apikey": API_KEY,
            "outputsize": "compact",
        }

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = requests.get(API_URL, params=params, timeout=REQUEST_TIMEOUT)
                response.raise_for_status()
                data = response.json()
                # Check for API internal errors
                if "Error Message" in data:
                    logger.error("API error: %s", data["Error Message"])
                    return None, None
                if "Note" in data:  # Rate limiting notice
                    logger.warning("API note: %s", data["Note"])
                    time.sleep(RETRY_BACKOFF * attempt)
                    continue

                ts_key = "Time Series (1min)"
                if ts_key not in data:
                    logger.error("Unexpected API response structure.")
                    return None, None

                # Get the most recent entry
                latest_timestamp = max(data[ts_key].keys())
                latest_price = float(data[ts_key][latest_timestamp]["4. close"])
                dt = datetime.strptime(latest_timestamp, "%Y-%m-%d %H:%M:%S")
                dt = dt.replace(tzinfo=timezone.utc)

                logger.debug(
                    "Fetched price %.4f for %s at %s", latest_price, self.symbol, dt
                )
                return latest_price, dt
            except (requests.RequestException, ValueError) as exc:
                logger.warning(
                    "Attempt %d/%d failed to fetch price: %s", attempt, MAX_RETRIES, exc
                )
                time.sleep(RETRY_BACKOFF * attempt)

        logger.error("All attempts to fetch price failed.")
        return None, None

    # --------------------------------------------------------------------- #
    # Public API
    # --------------------------------------------------------------------- #

    def update_price(self) -> bool:
        """
        Fetch the latest price and persist it.

        Returns:
            True if a new price was stored; False otherwise.
        """
        price, dt = self._fetch_price()
        if price is None or dt is None:
            return False
        self._store_price(price, dt)
        return True

    def moving_average(self, window: int = 20) -> pd.Series:
        """
        Compute the simple moving average (SMA) over the given window.

        Args:
            window: Number of periods (minutes) for the SMA.

        Returns:
            Pandas Series indexed by datetime containing SMA values.
        """
        prices = self._load_prices()
        if prices.empty:
            logger.warning("No price data to calculate SMA.")
            return pd.Series(dtype=float)
        sma = prices.rolling(window=window, min_periods=1).mean()
        return sma

    def generate_signals(self, short_window: int = 5, long_window: int = 20) -> List[Tuple[datetime, str]]:
        """
        Generate buy/sell signals based on SMA crossovers.

        Args:
            short_window: Window size for the fast SMA.
            long_window: Window size for the slow SMA.

        Returns:
            List of (timestamp, signal) tuples where signal is "BUY" or "SELL".
        """
        prices = self._load_prices()
        if prices.empty:
            logger.warning("Insufficient data for signal generation.")
            return []

        fast_sma = prices.rolling(window=short_window, min_periods=1).mean()
        slow_sma = prices.rolling(window=long_window, min_periods=1).mean()

        signal_series = pd.Series(index=prices.index, dtype=object)

        # Detect crossovers
        prev_fast = fast_sma.shift(1)
        prev_slow = slow_sma.shift(1)

        buy_mask = (prev_fast <= prev_slow) & (fast_sma > slow_sma)
        sell_mask = (prev_fast >= prev_slow) & (fast_sma < slow_sma)

        signal_series[buy_mask] = "BUY"
        signal_series[sell_mask] = "SELL"

        signals = [
            (ts.to_pydatetime(), signal)
            for ts