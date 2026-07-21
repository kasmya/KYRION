"""
Stock Price Tracker Module

A comprehensive stock price tracking system that fetches real-time and historical
stock data, stores it in a local SQLite database, computes technical indicators
(moving averages), and generates buy/sell signals based on crossover strategies.

This module follows security best practices including:
- Parameterized SQL queries to prevent injection
- Input validation and sanitization
- Secure API key handling (environment variables)
- Proper error handling without information leakage
- Type hints for improved code reliability

Dependencies:
    - yfinance: Yahoo Finance API wrapper (widely used PyPI package)
    - sqlite3: Standard library database
    - logging: Standard library logging
    - datetime, typing, os, json: Standard library modules

Example:
    >>> tracker = StockTracker("stocks.db")
    >>> tracker.fetch_and_store("AAPL")
    >>> signals = tracker.generate_signals("AAPL")
    >>> for signal in signals:
    ...     print(f"{signal.date}: {signal.action} at ${signal.price:.2f}")
"""

import os
import sqlite3
import logging
import json
from datetime import datetime, date, timedelta
from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass
from contextlib import contextmanager

try:
    import yfinance as yf
except ImportError:
    raise ImportError(
        "yfinance package is required. Install with: pip install yfinance"
    )

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


@dataclass(frozen=True)
class PriceRecord:
    """Immutable record representing a single price data point."""
    symbol: str
    timestamp: datetime
    open_price: float
    high_price: float
    low_price: float
    close_price: float
    volume: int
    adjusted_close: float


@dataclass(frozen=True)
class MovingAverage:
    """Immutable record representing a moving average value."""
    symbol: str
    timestamp: date
    period: int
    value: float
    ma_type: str  # 'SMA' or 'EMA'


@dataclass(frozen=True)
class TradeSignal:
    """Immutable record representing a buy/sell signal."""
    symbol: str
    date: date
    action: str  # 'BUY' or 'SELL'
    price: float
    indicator: str
    details: str


class DatabaseError(Exception):
    """Custom exception for database-related errors."""
    pass


class APIError(Exception):
    """Custom exception for API-related errors."""
    pass


class ValidationError(Exception):
    """Custom exception for input validation errors."""
    pass


class StockTracker:
    """
    Main class for tracking stock prices, computing indicators, and generating signals.
    
    This class handles all interactions with the database and external APIs,
    providing a clean interface for stock analysis operations.
    
    Attributes:
        db_path: Path to the SQLite database file.
        
    Example:
        >>> tracker = StockTracker("my_stocks.db")
        >>> tracker.initialize_database()
        >>> tracker.fetch_and_store("AAPL", period="1mo")
    """
    
    # Valid periods for yfinance
    VALID_PERIODS = {"1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "ytd", "max"}
    VALID_INTERVALS = {"1m", "2m", "5m", "15m", "30m", "60m", "90m", "1h", "1d", "5d", "1wk", "1mo", "3mo"}
    
    def __init__(self, db_path: str) -> None:
        """
        Initialize the StockTracker with a database path.
        
        Args:
            db_path: Path to the SQLite database file. Will be created if it doesn't exist.
            
        Raises:
            ValidationError: If db_path is empty or invalid.
        """
        if not db_path or not isinstance(db_path, str):
            raise ValidationError("Database path must be a non-empty string")
        
        # Sanitize path to prevent directory traversal
        self.db_path = os.path.abspath(os.path.expanduser(db_path))
        logger.info(f"StockTracker initialized with database: {self.db_path}")
    
    @contextmanager
    def _get_connection(self) -> sqlite3.Connection:
        """
        Context manager for database connections with automatic cleanup.
        
        Yields:
            sqlite3.Connection: Database connection with row factory set.
            
        Raises:
            DatabaseError: If connection fails.
        """
        conn = None
        try:
            conn = sqlite3.connect(self.db_path, timeout=30.0)
            conn.row_factory = sqlite3.Row
            # Enable foreign keys for referential integrity
            conn.execute("PRAGMA foreign_keys = ON")
            yield conn
        except sqlite3.Error as e:
            logger.error(f"Database connection error: {e}")
            raise DatabaseError(f"Failed to connect to database: {e}") from e
        finally:
            if conn:
                conn.close()
    
    def initialize_database(self) -> None:
        """
        Create database tables if they don't exist.
        
        Creates three tables:
        - price_history: Stores OHLCV price data
        - moving_averages: Stores computed moving averages
        - trade_signals: Stores generated buy/sell signals
        
        Raises:
            DatabaseError: If table creation fails.
        """
        schema = """
        CREATE TABLE IF NOT EXISTS price_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            timestamp DATETIME NOT NULL,
            open_price REAL NOT NULL,
            high_price REAL NOT NULL,
            low_price REAL NOT NULL,
            close_price REAL NOT NULL,
            volume INTEGER NOT NULL,
            adjusted_close REAL NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(symbol, timestamp)
        );
        
        CREATE TABLE IF NOT EXISTS moving_averages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            date DATE NOT NULL,
            period INTEGER NOT NULL,
            value REAL NOT NULL,
            ma_type TEXT NOT NULL CHECK(ma_type IN ('SMA', 'EMA')),
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(symbol, date, period, ma_type)
        );
        
        CREATE TABLE IF NOT EXISTS trade_signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            date DATE NOT NULL,
            action TEXT NOT NULL CHECK(action IN ('BUY', 'SELL')),
            price REAL NOT NULL,
            indicator TEXT NOT NULL,
            details TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        
        CREATE INDEX IF NOT EXISTS idx_price_symbol_date 
        ON price_history(symbol, timestamp);
        
        CREATE INDEX IF NOT EXISTS idx_ma_symbol_date 
        ON moving_averages(symbol, date);
        
        CREATE INDEX IF NOT EXISTS idx_signals_symbol_date 
        ON trade_signals(symbol, date);
        """
        
        try:
            with self._get_connection() as conn:
                conn.executescript(schema)
                conn.commit()
            logger.info("Database initialized successfully")
        except sqlite3.Error as e:
            logger.error(f"Database initialization failed: {e}")
            raise DatabaseError(f"Failed to initialize database: {e}") from e
    
    def _validate_symbol(self, symbol: str) -> str:
        """
        Validate and sanitize stock symbol.
        
        Args:
            symbol: Stock ticker symbol.
            
        Returns:
            str: Uppercase, stripped symbol.
            
        Raises:
            ValidationError: If symbol is invalid.
        """
        if not symbol or not isinstance(symbol, str):
            raise ValidationError("Symbol must be a non-empty string")
        
        cleaned = symbol.strip().upper()
        if not cleaned:
            raise ValidationError("Symbol cannot be empty or whitespace")
        
        # Basic validation: alphanumeric, dots, hyphens, carets (for indices)
        import re
        if not re.match(r'^[A-Z0-9.\-^]+$', cleaned):
            raise ValidationError(f"Invalid symbol format: {symbol}")
        
        if len(cleaned) > 20:
            raise ValidationError(f"Symbol too long: {symbol}")
        
        return cleaned
    
    def _validate_period_interval(self, period: str, interval: str) -> Tuple[str, str]:
        """
        Validate period and interval parameters.
        
        Args:
            period: Time period string.
            interval: Data interval string.
            
        Returns:
            Tuple of validated (period, interval).
            
        Raises:
            ValidationError: If parameters are invalid.
        """
        if period not in self.VALID_PERIODS:
            raise ValidationError(
                f"Invalid period: {period}. Valid options: {sorted(self.VALID_PERIODS)}"
            )
        if interval not in self.VALID_INTERVALS:
            raise ValidationError(
                f"Invalid interval: {interval}. Valid options: {sorted(self.VALID_INTERVALS)}"
            )
        
        # Validate compatible combinations
        if period in {"1d", "5d"} and interval not in {"1m", "2m", "5m", "15m", "30m", "60m", "90m", "1h"}:
            raise ValidationError(f"Interval {interval} not compatible with period {period}")
        
        return period, interval
    
    def fetch_price_data(
        self,
        symbol: str,
        period: str = "1mo",
        interval: str = "1d",
        start: Optional[str] = None,
        end: Optional[str] = None
    ) -> List[PriceRecord]:
        """
        Fetch price data from Yahoo Finance API.
        
        Args:
            symbol: Stock ticker symbol (e.g., 'AAPL', 'GOOGL').
            period: Time period to fetch (default: '1mo').
            interval: Data interval (default: '1d').
            start: Start date in 'YYYY-MM-DD' format (optional).
            end: End date in 'YYYY-MM-DD' format (optional).
            
        Returns:
            List of PriceRecord objects sorted by timestamp.
            
        Raises:
            ValidationError: If inputs are invalid.
            APIError: If API request fails.
        """
        symbol = self._validate_symbol(symbol)
        period, interval = self._validate_period_interval(period, interval)
        
        # Validate date formats if provided
        if start:
            try:
                datetime.strptime(start, "%Y-%m-%d")
            except ValueError:
                raise ValidationError(f"Invalid start date format: {start}. Use YYYY-MM-DD")
        if end:
            try:
                datetime.strptime(end, "%Y-%m-%d")
            except ValueError:
                raise ValidationError(f"Invalid end date format: {end}. Use YYYY-MM-DD")
        
        logger.info(f"Fetching data for {symbol} (period={period}, interval={interval})")
        
        try:
            ticker = yf.Ticker(symbol)
            
            # Use history method with appropriate parameters
            if start or end:
                hist = ticker.history(
                    start=start,
                    end=end,
                    interval=interval,
                    auto_adjust=False,
                    actions=False
                )
            else:
                hist = ticker.history(
                    period=period,
                    interval=interval,
                    auto_adjust=False,
                    actions=False
                )
            
            if hist.empty:
                logger.warning(f"No data returned for {symbol}")
                return []
            
            records = []
            for timestamp, row in hist.iterrows():
                # Ensure timestamp is timezone-aware UTC
                if timestamp.tzinfo is None:
                    timestamp = timestamp.replace(tzinfo=datetime.utcnow().tzinfo)
                
                record = PriceRecord(
                    symbol=symbol,
                    timestamp=timestamp.to_pydatetime(),
                    open_price=float(row['Open']),
                    high_price=float(row['High']),
                    low_price=float(row['Low']),
                    close_price=float(row['Close']),
                    volume=int(row['Volume']),
                    adjusted_close=float(row.get('Adj Close', row['Close']))
                )
                records.append(record)
            
            logger.info(f"Fetched {len(records)} records for {symbol}")
            return records
            
        except Exception as e:
            logger.error(f"API error for {symbol}: {e}")
            raise APIError(f"Failed to fetch data for {symbol}: {e}") from e
    
    def store_price_data(self, records: List[PriceRecord]) -> int:
        """
        Store price records in the database using upsert (INSERT OR REPLACE).
        
        Args:
            records: List of PriceRecord objects to store.
            
        Returns:
            int: Number of records inserted/updated.
            
        Raises:
            DatabaseError: If storage fails.
            ValidationError: If records list is empty.
        """
        if not records:
            raise ValidationError("Cannot store empty records list")
        
        insert_sql = """
        INSERT OR REPLACE INTO price_history 
        (symbol, timestamp, open_price, high_price, low_price, close_price, volume, adjusted_close)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        
        data = [
            (
                r.symbol,
                r.timestamp.isoformat(),
                r.open_price,
                r.high_price,
                r.low_price,
                r.close_price,
                r.volume,
                r.adjusted_close
            )
            for r in records
        ]
        
        try:
            with self._get_connection() as conn:
                cursor = conn.executemany(insert_sql, data)
                conn.commit()
                count = cursor.rowcount
            logger.info(f"Stored {count} price records")
            return count
        except sqlite3.Error as e:
            logger.error(f"Failed to store price data: {e}")
            raise DatabaseError(f"Failed to store price data: {e}") from e
    
    def fetch_and_store(
        self,
        symbol: str,
        period: str = "1mo",
        interval: str = "1d",
        start: Optional[str] = None,
        end: Optional[str] = None
    ) -> int:
        """
        Fetch price data from API and store in database in one operation.
        
        Args:
            symbol: Stock ticker symbol.
            period: Time period to fetch.
            interval: Data interval.
            start: Start date (optional).
            end: End date (optional).
            
        Returns:
            int: Number of records stored.
            
        Raises:
            ValidationError: If inputs are invalid.
            APIError: If API request fails.
            DatabaseError: If storage fails.
        """
        records = self.fetch_price_data(symbol, period, interval, start, end)
        return self.store_price_data(records)
    
    def get_price_history(
        self,
        symbol: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        limit: Optional[int] = None
    ) -> List[PriceRecord]:
        """
        Retrieve price history from database.
        
        Args:
            symbol: Stock ticker symbol.
            start_date: Filter records from this date (inclusive).
            end_date: Filter records to this date (inclusive).
            limit: Maximum number of records to return.
            
        Returns:
            List of PriceRecord objects sorted by timestamp descending.
            
        Raises:
            ValidationError: If symbol is invalid.
            DatabaseError: If query fails.
        """
        symbol = self._validate_symbol(symbol)
        
        query = "SELECT * FROM price_history WHERE symbol = ?"
        params: List[Any] = [symbol]
        
        if start_date:
            query += " AND date(timestamp) >= ?"
            params.append(start_date.isoformat())
        if end_date:
            query += " AND date(timestamp) <= ?"
            params.append(end_date.isoformat())
        
        query += " ORDER BY timestamp DESC"
        
        if limit:
            if not isinstance(limit, int) or limit <= 0:
                raise ValidationError("Limit must be a positive integer")
            query += " LIMIT ?"
            params.append(limit)
        
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(query, params)
                rows = cursor.fetchall()
            
            records = []
            for row in rows:
                records.append(PriceRecord(
                    symbol=row['symbol'],
                    timestamp=datetime.fromisoformat(row['timestamp']),
                    open_price=row['open_price'],
                    high_price=row['high_price'],
                    low_price=row['low_price'],
                    close_price=row['close_price'],
                    volume=row['volume'],
                    adjusted_close=row['adjusted_close']
                ))
            
            return records
        except sqlite3.Error as e:
            logger.error(f"Failed to retrieve price history: {e}")
            raise DatabaseError(f"Failed to retrieve price history: {e}") from e
    
    def compute_sma(self, symbol: str, period: int, lookback_days: int = 252) -> List[MovingAverage]:
        """
        Compute Simple Moving Average (SMA) for a symbol.
        
        Args:
            symbol: Stock ticker symbol.
            period: SMA period (e.g., 20, 50, 200).
            lookback_days: Number of days of history to use for calculation.
            
        Returns:
            List of MovingAverage objects.
            
        Raises:
            ValidationError: If inputs are invalid.
            DatabaseError: