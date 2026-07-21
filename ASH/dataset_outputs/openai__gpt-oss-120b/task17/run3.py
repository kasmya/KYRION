"""
stock_tracker.py

A lightweight stock price tracker that fetches real‑time prices from a public API,
stores price history in an SQLite database, computes simple moving averages,
and emits basic buy/sell signals.

Features
--------
* Fetch the latest price for a given ticker symbol.
* Persist price data with timestamps in a local SQLite database.
* Compute N‑period simple moving averages (SMA).
* Generate buy/sell signals when the price crosses the SMA.
* Comprehensive type hints, docstrings, and error handling.
* Security‑focused: parameterized SQL queries, request timeouts, and input validation.

Dependencies
------------
* requests – HTTP client for API calls (install via ``pip install requests``).
* python‑dateutil – robust datetime parsing (install via ``pip install python-dateutil``).

Both are widely‑used, stable PyPI packages.
"""

from __future__ import annotations

import logging
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime
from typing import List, Tuple, Optional

import requests
from dateutil import parser as dt_parser

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #

API_ENDPOINT = "https://query1.finance.yahoo.com/v7/finance/quote"
DEFAULT_TIMEOUT = 10  # seconds
DB_PATH = "stock_prices.db"

# --------------------------------------------------------------------------- #
# Logging setup
# --------------------------------------------------------------------------- #

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Data structures
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class PriceRecord:
    """Immutable representation of a single price entry."""

    symbol: str
    price: float
    timestamp: datetime


# --------------------------------------------------------------------------- #
# Database utilities
# --------------------------------------------------------------------------- #


def _get_connection() -> sqlite3.Connection:
    """
    Create a new SQLite connection with foreign‑key support enabled.

    Returns
    -------
    sqlite3.Connection
        An open connection to the SQLite database.

    Raises
    ------
    sqlite3.Error
        If the connection cannot be established.
    """
    try:
        conn = sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES)
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn
    except sqlite3.Error as exc:
        logger.exception("Failed to connect to SQLite database.")
        raise


def init_db() -> None:
    """
    Initialise the SQLite database schema if it does not already exist.

    The table ``prices`` stores symbol, price, and UTC timestamp.
    """
    create_sql = """
    CREATE TABLE IF NOT EXISTS prices (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        price REAL NOT NULL,
        timestamp DATETIME NOT NULL
    );
    """
    try:
        with _get_connection() as conn:
            conn.execute(create_sql)
            conn.commit()
        logger.info("Database initialised (or already present).")
    except sqlite3.Error:
        logger.exception("Database initialisation failed.")
        raise


def store_price(record: PriceRecord) -> None:
    """
    Persist a price record to the database.

    Parameters
    ----------
    record : PriceRecord
        The price data to store.

    Raises
    ------
    sqlite3.Error
        If the insert operation fails.
    """
    insert_sql = """
    INSERT INTO prices (symbol, price, timestamp)
    VALUES (?, ?, ?);
    """
    try:
        with _get_connection() as conn:
            conn.execute(
                insert_sql,
                (record.symbol.upper(), record.price, record.timestamp),
            )
            conn.commit()
        logger.debug("Stored price: %s", record)
    except sqlite3.Error:
        logger.exception("Failed to store price record: %s", record)
        raise


def fetch_history(
    symbol: str, limit: int = 100
) -> List[Tuple[float, datetime]]:
    """
    Retrieve the most recent price entries for a symbol.

    Parameters
    ----------
    symbol : str
        Ticker symbol (case‑insensitive).
    limit : int, optional
        Maximum number of rows to return (default 100).

    Returns
    -------
    List[Tuple[float, datetime]]
        List of (price, timestamp) tuples ordered newest first.

    Raises
    ------
    sqlite3.Error
        If the query fails.
    """
    query_sql = """
    SELECT price, timestamp FROM prices
    WHERE symbol = ?
    ORDER BY timestamp DESC
    LIMIT ?;
    """
    try:
        with _get_connection() as conn:
            cur = conn.execute(query_sql, (symbol.upper(), limit))
            rows = [(row[0], dt_parser.parse(row[1])) for row in cur.fetchall()]
        logger.debug("Fetched %d rows for %s", len(rows), symbol)
        return rows
    except sqlite3.Error:
        logger.exception("Failed to fetch price history for %s", symbol)
        raise


# --------------------------------------------------------------------------- #
# API interaction
# --------------------------------------------------------------------------- #


def fetch_price(symbol: str) -> PriceRecord:
    """
    Retrieve the latest market price for a given ticker symbol from Yahoo Finance.

    Parameters
    ----------
    symbol : str
        Ticker symbol (e.g., "AAPL").

    Returns
    -------
    PriceRecord
        The most recent price and timestamp.

    Raises
    ------
    ValueError
        If the API response does not contain a valid price.
    requests.RequestException
        For network‑related errors.
    """
    if not symbol or not symbol.strip():
        raise ValueError("Symbol must be a non‑empty string.")

    params = {"symbols": symbol.strip().upper()}
    try:
        response = requests.get(
            API_ENDPOINT,
            params=params,
            timeout=DEFAULT_TIMEOUT,
            headers={"User-Agent": "stock-tracker/1.0"},
        )
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as exc:
        logger.exception("Network error while fetching price for %s", symbol)
        raise

    try:
        quote = data["quoteResponse"]["result"][0]
        price = float(quote["regularMarketPrice"])
        ts = int(quote["regularMarketTime"])
        timestamp = datetime.utcfromtimestamp(ts)
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        logger.exception("Malformed API response for %s: %s", symbol, data)
        raise ValueError(f"Could not extract price for symbol '{symbol}'.") from exc

    record = PriceRecord(symbol=symbol.upper(), price=price, timestamp=timestamp)
    logger.info("Fetched price for %s: %.2f at %s", symbol, price, timestamp.isoformat())
    return record


# --------------------------------------------------------------------------- #
# Analytics
# --------------------------------------------------------------------------- #


def compute_sma(prices: List[float]) -> Optional[float]:
    """
    Compute the simple moving average (SMA) of a list of prices.

    Parameters
    ----------
    prices : List[float]
        List of price values. Must contain at least one element.

    Returns
    -------
    Optional[float]
        The SMA, or ``None`` if the list is empty.
    """
    if not prices:
        return None
    sma = sum(prices) / len(prices)
    logger.debug("Computed SMA: %.4f from %d prices", sma, len(prices))
    return sma


def get_moving_average(symbol: str, window: int = 20) -> Optional[float]:
    """
    Retrieve the N‑period simple moving average for a symbol.

    Parameters
    ----------
    symbol : str
        Ticker symbol.
    window : int, optional
        Number of most recent price points to include (default 20).

    Returns
    -------
    Optional[float]
        The SMA, or ``None`` if insufficient data.
    """
    if window <= 0:
        raise ValueError("Window size must be a positive integer.")
    history = fetch_history(symbol, limit=window)
    if len(history) < window:
        logger.warning(
            "Insufficient data for SMA: have %d points, need %d.", len(history), window
        )
        return None
    prices = [price for price, _ in history]
    return compute_sma(prices)


# --------------------------------------------------------------------------- #
# Signal generation
# --------------------------------------------------------------------------- #


def generate_signal(symbol: str, window: int = 20) -> Optional[str]:
    """
    Produce a basic buy/sell/hold signal based on price crossing the SMA.

    Logic
    -----
    * If the latest price > SMA → "BUY"
    * If the latest price < SMA → "SELL"
    * If equal or SMA unavailable → "HOLD"

    Parameters
    ----------
    symbol : str
        Ticker symbol.
    window : int, optional
        SMA period (default 20).

    Returns
    -------
    Optional[str]
        One of "BUY", "SELL", "HOLD", or ``None`` if data is missing.
    """
    try:
        latest_record = fetch_price(symbol)
        store_price(latest_record)
    except Exception as exc:
        logger.error("Unable to obtain latest price for %s: %s", symbol, exc)
        return None

    sma = get_moving_average(symbol, window=window)
    if sma is None:
        logger.info("SMA unavailable for %s; signal set to HOLD.", symbol)
        return "HOLD"

    if latest_record.price > sma:
        signal = "BUY"
    elif latest_record.price < sma:
        signal = "SELL"
    else:
        signal = "HOLD"

    logger.info("Signal for %s (price: %.2f, SMA: %.2f): %s", symbol, latest_record.price, sma, signal)
    return signal


# --------------------------------------------------------------------------- #
# Example usage (can be removed or guarded by __main__)
# --------------------------------------------------------------------------- #


def _demo() -> None:
    """
    Demonstration routine that fetches a price, stores it,
    computes a 10‑period SMA, and prints a signal.
    """
    symbol = "AAPL"
    init_db()
    signal = generate_signal(symbol, window=10)
    print(f"Signal for {symbol}: {signal}")


if __name__ == "__main__":
    _demo()