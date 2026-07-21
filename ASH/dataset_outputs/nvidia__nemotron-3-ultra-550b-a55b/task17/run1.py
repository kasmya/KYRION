"""
Stock Price Tracker Module

This module fetches stock prices from Alpha Vantage API, stores historical data in SQLite,
computes moving averages, and generates buy/sell signals based on moving average crossovers.

Security Best Practices:
- API key loaded from environment variable (never hardcoded)
- Parameterized SQL queries to prevent injection
- Input validation and sanitization
- HTTPS enforced for API requests
- Comprehensive error handling with logging

Dependencies:
- requests (PyPI)
- python-dotenv (PyPI) for loading .env files (optional)
"""

import os
import sqlite3
import logging
import time
from datetime import datetime, timezone
from typing import List, Tuple, Optional, Dict, Any
from dataclasses import dataclass

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Constants
DEFAULT_DB_PATH = "stock_data.db"
ALPHA_VANTAGE_BASE_URL = "https://www.alphavantage.co/query"
REQUEST_TIMEOUT = 10  # seconds
MAX_RETRIES = 3
BACKOFF_FACTOR = 1


@dataclass
class StockPrice:
    """Represents a single stock price data point."""
    symbol: str
    timestamp: datetime
    open_price: float
    high_price: float
    low_price: float
    close_price: float
    volume: int


@dataclass
class MovingAverage:
    """Represents a moving average calculation."""
    symbol: str
    timestamp: datetime
    period: int
    value: float


@dataclass
class Signal:
    """Represents a buy/sell signal."""
    symbol: str
    timestamp: datetime
    signal_type: str  # "BUY" or "SELL"
    short_ma: float
    long_ma: float
    current_price: float


class DatabaseManager:
    """Manages SQLite database operations for stock data storage."""

    def __init__(self, db_path: str = DEFAULT_DB_PATH) -> None:
        """
        Initialize database connection and create tables if they don't exist.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self._init_database()

    def _init_database(self) -> None:
        """Create database tables if they don't exist."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            # Stock prices table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS stock_prices (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    timestamp DATETIME NOT NULL,
                    open_price REAL NOT NULL,
                    high_price REAL NOT NULL,
                    low_price REAL NOT NULL,
                    close_price REAL NOT NULL,
                    volume INTEGER NOT NULL,
                    UNIQUE(symbol, timestamp)
                )
            """)
            # Moving averages table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS moving_averages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    timestamp DATETIME NOT NULL,
                    period INTEGER NOT NULL,
                    value REAL NOT NULL,
                    UNIQUE(symbol, timestamp, period)
                )
            """)
            # Signals table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    timestamp DATETIME NOT NULL,
                    signal_type TEXT NOT NULL,
                    short_ma REAL NOT NULL,
                    long_ma REAL NOT NULL,
                    current_price REAL NOT NULL
                )
            """)
            # Indexes for performance
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_prices_symbol_time ON stock_prices(symbol, timestamp)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_ma_symbol_time ON moving_averages(symbol, timestamp)")
            conn.commit()
        logger.info("Database initialized at %s", self.db_path)

    def store_prices(self, prices: List[StockPrice]) -> int:
        """
        Store stock prices in database, ignoring duplicates.

        Args:
            prices: List of StockPrice objects to store

        Returns:
            Number of new records inserted
        """
        if not prices:
            return 0

        inserted = 0
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            for price in prices:
                try:
                    cursor.execute("""
                        INSERT OR IGNORE INTO stock_prices 
                        (symbol, timestamp, open_price, high_price, low_price, close_price, volume)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (
                        price.symbol,
                        price.timestamp.isoformat(),
                        price.open_price,
                        price.high_price,
                        price.low_price,
                        price.close_price,
                        price.volume
                    ))
                    if cursor.rowcount > 0:
                        inserted += 1
                except sqlite3.Error as e:
                    logger.error("Failed to insert price for %s: %s", price.symbol, e)
            conn.commit()
        logger.info("Inserted %d new price records", inserted)
        return inserted

    def store_moving_averages(self, mas: List[MovingAverage]) -> int:
        """
        Store moving averages in database, ignoring duplicates.

        Args:
            mas: List of MovingAverage objects to store

        Returns:
            Number of new records inserted
        """
        if not mas:
            return 0

        inserted = 0
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            for ma in mas:
                try:
                    cursor.execute("""
                        INSERT OR IGNORE INTO moving_averages 
                        (symbol, timestamp, period, value)
                        VALUES (?, ?, ?, ?)
                    """, (
                        ma.symbol,
                        ma.timestamp.isoformat(),
                        ma.period,
                        ma.value
                    ))
                    if cursor.rowcount > 0:
                        inserted += 1
                except sqlite3.Error as e:
                    logger.error("Failed to insert MA for %s: %s", ma.symbol, e)
            conn.commit()
        logger.info("Inserted %d new moving average records", inserted)
        return inserted

    def store_signals(self, signals: List[Signal]) -> int:
        """
        Store trading signals in database.

        Args:
            signals: List of Signal objects to store

        Returns:
            Number of records inserted
        """
        if not signals:
            return 0

        inserted = 0
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            for signal in signals:
                try:
                    cursor.execute("""
                        INSERT INTO signals 
                        (symbol, timestamp, signal_type, short_ma, long_ma, current_price)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (
                        signal.symbol,
                        signal.timestamp.isoformat(),
                        signal.signal_type,
                        signal.short_ma,
                        signal.long_ma,
                        signal.current_price
                    ))
                    inserted += 1
                except sqlite3.Error as e:
                    logger.error("Failed to insert signal for %s: %s", signal.symbol, e)
            conn.commit()
        logger.info("Inserted %d new signal records", inserted)
        return inserted

    def get_prices(self, symbol: str, limit: int = 100) -> List[StockPrice]:
        """
        Retrieve recent stock prices for a symbol.

        Args:
            symbol: Stock symbol
            limit: Maximum number of records to return

        Returns:
            List of StockPrice objects ordered by timestamp ascending
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT symbol, timestamp, open_price, high_price, low_price, close_price, volume
                FROM stock_prices
                WHERE symbol = ?
                ORDER BY timestamp ASC
                LIMIT ?
            """, (symbol, limit))
            rows = cursor.fetchall()

        prices = []
        for row in rows:
            prices.append(StockPrice(
                symbol=row["symbol"],
                timestamp=datetime.fromisoformat(row["timestamp"]),
                open_price=row["open_price"],
                high_price=row["high_price"],
                low_price=row["low_price"],
                close_price=row["close_price"],
                volume=row["volume"]
            ))
        return prices

    def get_latest_moving_average(self, symbol: str, period: int) -> Optional[MovingAverage]:
        """
        Get the most recent moving average for a symbol and period.

        Args:
            symbol: Stock symbol
            period: Moving average period

        Returns:
            MovingAverage object or None if not found
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT symbol, timestamp, period, value
                FROM moving_averages
                WHERE symbol = ? AND period = ?
                ORDER BY timestamp DESC
                LIMIT 1
            """, (symbol, period))
            row = cursor.fetchone()

        if row:
            return MovingAverage(
                symbol=row["symbol"],
                timestamp=datetime.fromisoformat(row["timestamp"]),
                period=row["period"],
                value=row["value"]
            )
        return None


class AlphaVantageClient:
    """Client for fetching stock data from Alpha Vantage API."""

    def __init__(self, api_key: str) -> None:
        """
        Initialize API client with session and retry strategy.

        Args:
            api_key: Alpha Vantage API key
        """
        if not api_key:
            raise ValueError("API key cannot be empty")
        self.api_key = api_key
        self.session = self._create_session()

    def _create_session(self) -> requests.Session:
        """Create requests session with retry strategy."""
        session = requests.Session()
        retry_strategy = Retry(
            total=MAX_RETRIES,
            backoff_factor=BACKOFF_FACTOR,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session

    def fetch_daily_prices(self, symbol: str) -> List[StockPrice]:
        """
        Fetch daily adjusted stock prices for a symbol.

        Args:
            symbol: Stock symbol (e.g., "AAPL")

        Returns:
            List of StockPrice objects

        Raises:
            requests.RequestException: If API request fails
            ValueError: If response parsing fails
        """
        params = {
            "function": "TIME_SERIES_DAILY_ADJUSTED",
            "symbol": symbol.upper(),
            "apikey": self.api_key,
            "outputsize": "compact",  # Last 100 data points
            "datatype": "json"
        }

        logger.info("Fetching daily prices for %s", symbol)
        response = self.session.get(
            ALPHA_VANTAGE_BASE_URL,
            params=params,
            timeout=REQUEST_TIMEOUT
        )
        response.raise_for_status()
        data = response.json()

        # Check for API errors
        if "Error Message" in data:
            raise ValueError(f"API Error: {data['Error Message']}")
        if "Note" in data:
            raise ValueError(f"API Limit: {data['Note']}")

        time_series = data.get("Time Series (Daily)")
        if not time_series:
            raise ValueError(f"No time series data in response for {symbol}")

        prices = []
        for date_str, values in time_series.items():
            try:
                timestamp = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                prices.append(StockPrice(
                    symbol=symbol.upper(),
                    timestamp=timestamp,
                    open_price=float(values["1. open"]),
                    high_price=float(values["2. high"]),
                    low_price=float(values["3. low"]),
                    close_price=float(values["4. close"]),
                    volume=int(values["6. volume"])
                ))
            except (KeyError, ValueError) as e:
                logger.warning("Skipping invalid data point for %s on %s: %s", symbol, date_str, e)

        # Sort by timestamp ascending (oldest first)
        prices.sort(key=lambda p: p.timestamp)
        logger.info("Fetched %d price records for %s", len(prices), symbol)
        return prices


def compute_moving_averages(prices: List[StockPrice], periods: List[int]) -> List[MovingAverage]:
    """
    Compute simple moving averages for given periods.

    Args:
        prices: List of StockPrice objects (must be sorted by timestamp ascending)
        periods: List of periods for moving averages (e.g., [20, 50])

    Returns:
        List of MovingAverage objects
    """
    if not prices:
        return []

    if len(prices) < max(periods):
        logger.warning("Insufficient data points (%d) for periods %s", len(prices), periods)
        return []

    mas = []
    close_prices = [p.close_price for p in prices]

    for period in periods:
        for i in range(period - 1, len(prices)):
            window = close_prices[i - period + 1:i + 1]
            ma_value = sum(window) / period
            mas.append(MovingAverage(
                symbol=prices[i].symbol,
                timestamp=prices[i].timestamp,
                period=period,
                value=round(ma_value, 4)
            ))

    logger.info("Computed %d moving averages for %s", len(mas), prices[0].symbol if prices else "unknown")
    return mas


def generate_signals(
    prices: List[StockPrice],
    short_ma_period: int,
    long_ma_period: int,
    short_mas: List[MovingAverage],
    long_mas: List[MovingAverage]
) -> List[Signal]:
    """
    Generate buy/sell signals based on moving average crossovers.

    Args:
        prices: List of StockPrice objects
        short_ma_period: Short moving average period
        long_ma_period: Long moving average period
        short_mas: Precomputed short period moving averages
        long_mas: Precomputed long period moving averages

    Returns:
        List of Signal objects
    """
    if not prices or not short_mas or not long_mas:
        return []

    # Create lookup dictionaries for MAs by timestamp
    short_ma_dict = {ma.timestamp: ma.value for ma in short_mas}
    long_ma_dict = {ma.timestamp: ma.value for ma in long_mas}

    signals = []
    prev_short = None
    prev_long = None

    for price in prices:
        short_val = short_ma_dict.get(price.timestamp)
        long_val = long_ma_dict.get(price.timestamp)

        if short_val is None or long_val is None:
            continue

        # Check for crossover
        if prev_short is not None and prev_long is not None:
            # Golden cross: short MA crosses above long MA
            if prev_short <= prev_long and short_val > long_val:
                signals.append(Signal(
                    symbol=price.symbol,
                    timestamp=price.timestamp,
                    signal_type="BUY",
                    short_ma=short_val,
                    long_ma=long_val,
                    current_price=price.close_price
                ))
            # Death cross: short MA crosses below long MA
            elif prev_short >= prev_long and short_val < long_val:
                signals.append(Signal(
                    symbol=price.symbol,
                    timestamp=price.timestamp,
                    signal_type="SELL",
                    short_ma=short_val,
                    long_ma=long_val,
                    current_price=price.close_price
                ))

        prev_short = short_val
        prev_long = long_val

    logger.info("Generated %d signals for %s", len(signals), prices[0].symbol if prices else "unknown")
    return signals


def validate_symbol(symbol: str) -> bool:
    """
    Validate stock symbol format.

    Args:
        symbol: Stock symbol to validate

    Returns:
        True if valid, False otherwise
    """
    if not symbol or not isinstance(symbol, str):
        return False
    # Basic validation: alphanumeric, 1-5 chars, optionally with dot for exchanges
    symbol = symbol.strip().upper()
    return bool(symbol) and len(symbol) <= 10 and all(c.isalnum() or c == '.' for c in symbol)


def run_tracker(
    symbols: List[str],
    db_path: str = DEFAULT_DB_PATH,
    short_ma_period: int = 20,
    long_ma_period: int = 50,
    api_key: Optional[str] = None
) -> Dict[str, Any]:
    """
    Main function to run the stock price tracker for given symbols.

    Args:
        symbols: List of stock symbols to track
        db_path: Path to SQLite database
        short_ma_period: Short moving average period
        long_ma_period: Long moving average period
        api_key: Alpha Vantage API key (defaults to env var ALPHA_VANTAGE_API_KEY)