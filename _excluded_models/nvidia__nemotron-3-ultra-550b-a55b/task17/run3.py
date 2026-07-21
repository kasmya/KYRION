"""
Stock Price Tracker Module

This module provides functionality to fetch stock prices from an API, store historical data
in a SQLite database, compute moving averages, and generate buy/sell signals based on
moving average crossovers.

Security Best Practices:
- API keys are loaded from environment variables
- SQL queries use parameterized statements to prevent injection
- Input validation and sanitization on all external inputs
- Comprehensive error handling with meaningful exceptions
- Logging for audit trails and debugging

Dependencies:
- requests (PyPI package for HTTP requests)
- Python standard library modules: sqlite3, os, logging, datetime, typing, statistics
"""

import os
import sqlite3
import logging
import statistics
from datetime import datetime, timezone
from typing import List, Tuple, Optional, Dict, Any
from dataclasses import dataclass

import requests

# Configure module logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)


class StockTrackerError(Exception):
    """Base exception for Stock Tracker errors."""
    pass


class APIError(StockTrackerError):
    """Exception raised for API-related errors."""
    pass


class DatabaseError(StockTrackerError):
    """Exception raised for database-related errors."""
    pass


class ValidationError(StockTrackerError):
    """Exception raised for input validation errors."""
    pass


@dataclass
class PriceRecord:
    """Data class representing a single price record."""
    symbol: str
    price: float
    timestamp: datetime
    source: str = "api"


@dataclass
class Signal:
    """Data class representing a buy/sell signal."""
    symbol: str
    signal_type: str  # "BUY" or "SELL"
    timestamp: datetime
    short_ma: float
    long_ma: float
    price: float


class StockTracker:
    """
    Main class for tracking stock prices, computing moving averages, and generating signals.
    
    Attributes:
        api_key: Alpha Vantage API key (loaded from environment variable)
        db_path: Path to SQLite database file
        base_url: Base URL for Alpha Vantage API
    """
    
    def __init__(
        self,
        db_path: str = "stock_history.db",
        api_key: Optional[str] = None,
        base_url: str = "https://www.alphavantage.co/query"
    ) -> None:
        """
        Initialize the StockTracker.
        
        Args:
            db_path: Path to SQLite database file
            api_key: Alpha Vantage API key (defaults to ALPHA_VANTAGE_API_KEY env var)
            base_url: Base URL for the API endpoint
            
        Raises:
            ValidationError: If API key is not provided or invalid
        """
        self.db_path = db_path
        self.base_url = base_url
        
        # Load API key from environment if not provided
        self.api_key = api_key or os.getenv("ALPHA_VANTAGE_API_KEY")
        if not self.api_key:
            raise ValidationError(
                "API key required. Set ALPHA_VANTAGE_API_KEY environment variable "
                "or pass api_key parameter."
            )
        
        # Initialize database
        self._init_database()
        logger.info("StockTracker initialized with database: %s", db_path)
    
    def _init_database(self) -> None:
        """Initialize the database schema."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS price_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        symbol TEXT NOT NULL,
                        price REAL NOT NULL,
                        timestamp TEXT NOT NULL,
                        source TEXT DEFAULT 'api',
                        UNIQUE(symbol, timestamp)
                    )
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_symbol_timestamp 
                    ON price_history(symbol, timestamp DESC)
                """)
                conn.commit()
        except sqlite3.Error as e:
            logger.error("Database initialization failed: %s", e)
            raise DatabaseError(f"Failed to initialize database: {e}") from e
    
    def fetch_price(self, symbol: str) -> PriceRecord:
        """
        Fetch current stock price from Alpha Vantage API.
        
        Args:
            symbol: Stock symbol (e.g., "AAPL", "MSFT")
            
        Returns:
            PriceRecord with current price and timestamp
            
        Raises:
            ValidationError: If symbol is invalid
            APIError: If API request fails or returns error
        """
        # Validate symbol
        if not symbol or not isinstance(symbol, str):
            raise ValidationError("Symbol must be a non-empty string")
        
        symbol = symbol.upper().strip()
        if not symbol.isalnum() and not all(c.isalnum() or c in ".-" for c in symbol):
            raise ValidationError(f"Invalid symbol format: {symbol}")
        
        params = {
            "function": "GLOBAL_QUOTE",
            "symbol": symbol,
            "apikey": self.api_key
        }
        
        try:
            response = requests.get(self.base_url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as e:
            logger.error("API request failed for %s: %s", symbol, e)
            raise APIError(f"API request failed: {e}") from e
        
        # Check for API errors
        if "Error Message" in data:
            raise APIError(f"API error: {data['Error Message']}")
        if "Note" in data:
            raise APIError(f"API rate limit: {data['Note']}")
        
        # Parse response
        try:
            quote = data.get("Global Quote", {})
            price_str = quote.get("05. price")
            if not price_str:
                raise APIError("Price not found in API response")
            
            price = float(price_str)
            timestamp = datetime.now(timezone.utc)
            
            return PriceRecord(
                symbol=symbol,
                price=price,
                timestamp=timestamp,
                source="api"
            )
        except (KeyError, ValueError, TypeError) as e:
            logger.error("Failed to parse API response for %s: %s", symbol, e)
            raise APIError(f"Failed to parse API response: {e}") from e
    
    def store_price(self, record: PriceRecord) -> None:
        """
        Store a price record in the database.
        
        Args:
            record: PriceRecord to store
            
        Raises:
            DatabaseError: If database operation fails
        """
        if not isinstance(record, PriceRecord):
            raise ValidationError("record must be a PriceRecord instance")
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO price_history 
                    (symbol, price, timestamp, source)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        record.symbol,
                        record.price,
                        record.timestamp.isoformat(),
                        record.source
                    )
                )
                conn.commit()
            logger.debug("Stored price for %s: %.2f", record.symbol, record.price)
        except sqlite3.Error as e:
            logger.error("Failed to store price for %s: %s", record.symbol, e)
            raise DatabaseError(f"Failed to store price: {e}") from e
    
    def get_historical_prices(
        self, 
        symbol: str, 
        limit: int = 100
    ) -> List[PriceRecord]:
        """
        Retrieve historical prices from database.
        
        Args:
            symbol: Stock symbol
            limit: Maximum number of records to return (default: 100)
            
        Returns:
            List of PriceRecord objects sorted by timestamp descending
            
        Raises:
            ValidationError: If symbol is invalid or limit is not positive
            DatabaseError: If database query fails
        """
        if not symbol or not isinstance(symbol, str):
            raise ValidationError("Symbol must be a non-empty string")
        
        if not isinstance(limit, int) or limit <= 0:
            raise ValidationError("Limit must be a positive integer")
        
        symbol = symbol.upper().strip()
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    """
                    SELECT symbol, price, timestamp, source
                    FROM price_history
                    WHERE symbol = ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                    """,
                    (symbol, limit)
                )
                rows = cursor.fetchall()
        except sqlite3.Error as e:
            logger.error("Failed to retrieve history for %s: %s", symbol, e)
            raise DatabaseError(f"Failed to retrieve history: {e}") from e
        
        records = []
        for row in rows:
            try:
                records.append(PriceRecord(
                    symbol=row["symbol"],
                    price=row["price"],
                    timestamp=datetime.fromisoformat(row["timestamp"]),
                    source=row["source"]
                ))
            except (ValueError, KeyError) as e:
                logger.warning("Skipping invalid row for %s: %s", symbol, e)
                continue
        
        return records
    
    def compute_moving_average(
        self, 
        prices: List[float], 
        window: int
    ) -> List[Optional[float]]:
        """
        Compute Simple Moving Average (SMA) for a price series.
        
        Args:
            prices: List of prices (most recent first)
            window: Moving average window size
            
        Returns:
            List of SMA values (None for insufficient data points)
            
        Raises:
            ValidationError: If window is not positive or prices list is empty
        """
        if not prices:
            raise ValidationError("Prices list cannot be empty")
        
        if not isinstance(window, int) or window <= 0:
            raise ValidationError("Window must be a positive integer")
        
        if window > len(prices):
            logger.warning("Window size %d exceeds data points %d", window, len(prices))
        
        # Reverse to chronological order (oldest first)
        chronological = list(reversed(prices))
        sma_values = []
        
        for i in range(len(chronological)):
            if i < window - 1:
                sma_values.append(None)
            else:
                window_data = chronological[i - window + 1:i + 1]
                sma_values.append(statistics.mean(window_data))
        
        # Reverse back to most-recent-first order
        return list(reversed(sma_values))
    
    def generate_signals(
        self,
        symbol: str,
        short_window: int = 10,
        long_window: int = 50,
        min_periods: int = 50
    ) -> List[Signal]:
        """
        Generate buy/sell signals based on moving average crossover.
        
        A BUY signal is generated when the short MA crosses above the long MA.
        A SELL signal is generated when the short MA crosses below the long MA.
        
        Args:
            symbol: Stock symbol
            short_window: Short-term MA window (default: 10)
            long_window: Long-term MA window (default: 50)
            min_periods: Minimum periods required before generating signals (default: 50)
            
        Returns:
            List of Signal objects
            
        Raises:
            ValidationError: If parameters are invalid
            DatabaseError: If insufficient historical data
        """
        if short_window >= long_window:
            raise ValidationError("Short window must be less than long window")
        
        if min_periods < long_window:
            raise ValidationError("min_periods must be >= long_window")
        
        # Fetch enough historical data
        records = self.get_historical_prices(symbol, limit=min_periods + 10)
        
        if len(records) < min_periods:
            raise DatabaseError(
                f"Insufficient data: {len(records)} records, need at least {min_periods}"
            )
        
        # Extract prices (most recent first)
        prices = [r.price for r in records]
        timestamps = [r.timestamp for r in records]
        
        # Compute moving averages
        short_ma = self.compute_moving_average(prices, short_window)
        long_ma = self.compute_moving_average(prices, long_window)
        
        # Generate signals based on crossovers
        signals = []
        previous_short = None
        previous_long = None
        
        # Iterate from oldest to newest (reverse of our lists)
        for i in range(len(prices) - 1, -1, -1):
            curr_short = short_ma[i]
            curr_long = long_ma[i]
            
            # Skip if either MA is not yet available
            if curr_short is None or curr_long is None:
                previous_short = curr_short
                previous_long = curr_long
                continue
            
            # Check for crossover
            if previous_short is not None and previous_long is not None:
                # BUY: short crosses above long
                if previous_short <= previous_long and curr_short > curr_long:
                    signals.append(Signal(
                        symbol=symbol,
                        signal_type="BUY",
                        timestamp=timestamps[i],
                        short_ma=curr_short,
                        long_ma=curr_long,
                        price=prices[i]
                    ))
                # SELL: short crosses below long
                elif previous_short >= previous_long and curr_short < curr_long:
                    signals.append(Signal(
                        symbol=symbol,
                        signal_type="SELL",
                        timestamp=timestamps[i],
                        short_ma=curr_short,
                        long_ma=curr_long,
                        price=prices[i]
                    ))
            
            previous_short = curr_short
            previous_long = curr_long
        
        # Reverse to chronological order
        signals.reverse()
        logger.info("Generated %d signals for %s", len(signals), symbol)
        return signals
    
    def update_and_analyze(
        self,
        symbol: str,
        short_window: int = 10,
        long_window: int = 50
    ) -> Tuple[PriceRecord, List[Signal]]:
        """
        Fetch latest price, store it, and generate updated signals.
        
        This is a convenience method that performs the full update cycle.
        
        Args:
            symbol: Stock symbol
            short_window: Short-term MA window
            long_window: Long-term MA window
            
        Returns:
            Tuple of (latest PriceRecord, list of Signals)
            
        Raises:
            StockTrackerError: If any step fails
        """
        # Fetch and store latest price
        record = self.fetch_price(symbol)
        self.store_price(record)
        
        # Generate signals
        signals = self.generate_signals(symbol, short_window, long_window)
        
        return record, signals


def main() -> None:
    """
    Demonstration of StockTracker usage.
    
    This function shows how to use the StockTracker class.
    Requires ALPHA_VANTAGE_API_KEY environment variable to be set.
    """
    try:
        # Initialize tracker (will load API key from environment)
        tracker = StockTracker(db_path="demo_stocks.db")
        
        # Example: Track Apple stock
        symbol = "AAPL"
        
        print(f"Fetching latest price for {symbol}...")
        record, signals = tracker.update_and_analyze(symbol)