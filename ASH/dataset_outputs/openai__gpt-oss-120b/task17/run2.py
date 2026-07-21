"""
stock_tracker.py

A lightweight stock price tracker that fetches real‑time prices from a public API,
stores historical data in a SQLite database, computes simple moving averages,
and emits basic buy/sell/hold signals based on a short‑term vs. long‑term average
crossover strategy.

The module follows security best practices:
- Uses HTTPS for all external requests.
- Retrieves API keys from environment variables (never hard‑coded).
- Employs parameterised SQL queries to prevent injection.
- Handles and logs errors explicitly without leaking sensitive data.

Only the Python standard library and the widely‑used ``requests`` package are required.
"""

from __future__ import annotations

import datetime as _dt
import json as _json
import logging as _logging
import os as _os
import sqlite3 as _sqlite3
import sys as _sys
from dataclasses import dataclass
from statistics import mean as _mean
from typing import List, Optional, Tuple

import requests as _requests

# --------------------------------------------------------------------------- #
# Configuration & Logging
# --------------------------------------------------------------------------- #

_API_ENDPOINT = "https://api.example.com/price"  # Placeholder; replace with a real API.
_API_KEY_ENV = "STOCK_API_KEY"
_DB_PATH = _os.getenv("STOCK_DB_PATH", "stock_prices.db")

_logger = _logging.getLogger(__name__)
_handler = _logging.StreamHandler(_sys.stdout)
_formatter = _logging.Formatter(
    "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
_handler.setFormatter(_formatter)
_logger.addHandler(_handler)
_logger.setLevel(_logging.INFO)


# --------------------------------------------------------------------------- #
# Exceptions
# --------------------------------------------------------------------------- #

class StockTrackerError(Exception):
    """Base exception for all stock tracker related errors."""
    pass


class APIFetchError(StockTrackerError):
    """Raised when the price fetching from the external API fails."""
    pass


class DatabaseError(StockTrackerError):
    """Raised for any SQLite related errors."""
    pass


# --------------------------------------------------------------------------- #
# Data Model
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class PriceRecord:
    """Immutable representation of a stored price point."""
    symbol: str
    price: float
    timestamp: _dt.datetime


# --------------------------------------------------------------------------- #
# Core Functionality
# --------------------------------------------------------------------------- #

def _get_api_key() -> str:
    """
    Retrieve the API key from the environment.

    Raises:
        StockTrackerError: If the environment variable is missing.
    """
    api_key = _os.getenv(_API_KEY_ENV)
    if not api_key:
        raise StockTrackerError(
            f"Required environment variable '{_API_KEY_ENV}' not set."
        )
    return api_key


def fetch_price(symbol: str) -> float:
    """
    Fetch the latest price for a given stock symbol from the configured API.

    Args:
        symbol: The ticker symbol (e.g., "AAPL").

    Returns:
        The latest price as a float.

    Raises:
        APIFetchError: If the request fails or the response is malformed.
    """
    api_key = _get_api_key()
    params = {"symbol": symbol, "apikey": api_key}
    try:
        response = _requests.get(_API_ENDPOINT, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        price = float(data["price"])
        _logger.debug("Fetched price %s for symbol %s", price, symbol)
        return price
    except (_requests.RequestException, KeyError, ValueError) as exc:
        _logger.error("Failed to fetch price for %s: %s", symbol, exc)
        raise APIFetchError(f"Could not retrieve price for {symbol}") from exc


def _init_db(conn: _sqlite3.Connection) -> None:
    """
    Initialise the SQLite database with the required schema if it does not exist.

    Args:
        conn: An open SQLite connection.

    Raises:
        DatabaseError: If table creation fails.
    """
    create_table_sql = """
    CREATE TABLE IF NOT EXISTS prices (
        symbol TEXT NOT NULL,
        price REAL NOT NULL,
        timestamp TEXT NOT NULL,
        PRIMARY KEY (symbol, timestamp)
    );
    """
    try:
        conn.execute(create_table_sql)
        conn.commit()
        _logger.debug("Database schema ensured.")
    except _sqlite3.Error as exc:
        _logger.error("Database initialisation error: %s", exc)
        raise DatabaseError("Failed to initialise the database.") from exc


def store_price(record: PriceRecord) -> None:
    """
    Persist a price record into the SQLite database.

    Args:
        record: The PriceRecord instance to store.

    Raises:
        DatabaseError: If insertion fails.
    """
    try:
        with _sqlite3.connect(_DB_PATH) as conn:
            _init_db(conn)
            insert_sql = """
            INSERT OR REPLACE INTO prices (symbol, price, timestamp)
            VALUES (?, ?, ?);
            """
            conn.execute(
                insert_sql,
                (record.symbol, record.price, record.timestamp.isoformat()),
            )
            conn.commit()
            _logger.info(
                "Stored price %.2f for %s at %s",
                record.price,
                record.symbol,
                record.timestamp.isoformat(),
            )
    except _sqlite3.Error as exc:
        _logger.error("Failed to store price: %s", exc)
        raise DatabaseError("Could not store price record.") from exc


def _fetch_recent_prices(
    symbol: str, limit: int
) -> List[Tuple[float, _dt.datetime]]:
    """
    Retrieve the most recent ``limit`` price entries for a given symbol.

    Args:
        symbol: The ticker symbol.
        limit: Number of recent records to fetch.

    Returns:
        A list of (price, timestamp) tuples ordered from newest to oldest.

    Raises:
        DatabaseError: If the query fails.
    """
    query_sql = """
    SELECT price, timestamp FROM prices
    WHERE symbol = ?
    ORDER BY timestamp DESC
    LIMIT ?;
    """
    try:
        with _sqlite3.connect(_DB_PATH) as conn:
            cursor = conn.execute(query_sql, (symbol, limit))
            rows = cursor.fetchall()
            result = [
                (price, _dt.datetime.fromisoformat(ts)) for price, ts in rows
            ]
            _logger.debug(
                "Fetched %d recent prices for %s", len(result), symbol
            )
            return result
    except _sqlite3.Error as exc:
        _logger.error("Error fetching recent prices: %s", exc)
        raise DatabaseError("Failed to fetch recent prices.") from exc


def compute_moving_average(symbol: str, window: int) -> Optional[float]:
    """
    Compute the simple moving average (SMA) of the last ``window`` prices.

    Args:
        symbol: The ticker symbol.
        window: Number of periods to include in the average.

    Returns:
        The SMA as a float, or ``None`` if insufficient data.

    Raises:
        DatabaseError: Propagated from underlying DB operations.
    """
    if window <= 0:
        raise ValueError("Window size must be a positive integer.")
    recent = _fetch_recent_prices(symbol, window)
    if len(recent) < window:
        _logger.warning(
            "Insufficient data to compute SMA for %s (need %d, have %d).",
            symbol,
            window,
            len(recent),
        )
        return None
    prices = [price for price, _ in recent]
    sma = _mean(prices)
    _logger.info("SMA(%d) for %s = %.4f", window, symbol, sma)
    return sma


def generate_signal(
    symbol: str,
    short_window: int = 5,
    long_window: int = 20,
) -> str:
    """
    Generate a trading signal based on SMA crossover.

    - If short‑term SMA > long‑term SMA → "buy".
    - If short‑term SMA < long‑term SMA → "sell".
    - Otherwise → "hold".

    Args:
        symbol: The ticker symbol.
        short_window: Period for the short‑term SMA.
        long_window: Period for the long‑term SMA.

    Returns:
        One of "buy", "sell", or "hold".

    Raises:
        DatabaseError: If data retrieval fails.
    """
    if short_window >= long_window:
        raise ValueError("short_window must be less than long_window.")
    short_ma = compute_moving_average(symbol, short_window)
    long_ma = compute_moving_average(symbol, long_window)

    if short_ma is None or long_ma is None:
        _logger.info("Not enough data to emit a signal for %s.", symbol)
        return "hold"

    if short_ma > long_ma:
        signal = "buy"
    elif short_ma < long_ma:
        signal = "sell"
    else:
        signal = "hold"

    _logger.info(
        "Signal for %s (SMA%dd=%.4f, SMA%dd=%.4f): %s",
        symbol,
        short_window,
        short_ma,
        long_window,
        long_ma,
        signal,
    )
    return signal


def track_and_signal(symbol: str) -> str:
    """
    Fetch the latest price, store it, and emit a trading signal.

    This is a convenience wrapper for typical daily/interval execution.

    Args:
        symbol: The ticker symbol.

    Returns:
        The generated signal ("buy", "sell", or "hold").

    Raises:
        APIFetchError, DatabaseError: Propagated from underlying operations.
    """
    price = fetch_price(symbol)
    record = PriceRecord(
        symbol=symbol,
        price=price,
        timestamp=_dt.datetime.utcnow(),
    )
    store_price(record)
    return generate_signal(symbol)


# --------------------------------------------------------------------------- #
# Example usage (executed when run as a script)
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    import argparse as _argparse

    parser = _argparse.ArgumentParser(
        description="Fetch a stock price, store it, and compute a trade signal."
    )
    parser.add_argument("symbol", help="Ticker symbol, e.g., AAPL")
    parser.add_argument(
        "--short",
        type=int,
        default=5,
        help="Short‑term SMA window (default: 5)",
    )
    parser.add_argument(
        "--long",
        type=int,
        default=20,
        help="Long‑term SMA window (default: 20)",
    )
    args = parser.parse_args()

    try:
        signal = track_and_signal(args.symbol.upper())
        print(f"Signal for {args.symbol.upper()}: {signal}")
    except StockTrackerError as e:
        _logger.error("Operation failed: %s", e)
        _sys.exit(1)