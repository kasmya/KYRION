"""
stock_tracker.py

A lightweight stock price tracker that fetches real‑time prices from a public API,
stores historical data in an SQLite database, computes simple moving averages,
and emits basic buy/sell signals based on a short‑term vs long‑term average
crossover strategy.

Only the Python standard library and the widely‑used third‑party packages
`requests` and `python-dotenv` are required.

Typical usage:

    from stock_tracker import run_tracker

    run_tracker(
        symbols=["AAPL", "MSFT"],
        db_path="prices.db",
        short_window=5,
        long_window=20,
        poll_interval=60,
    )
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, List, Sequence, Tuple

import requests
from dotenv import load_dotenv

# --------------------------------------------------------------------------- #
# Configuration & Logging
# --------------------------------------------------------------------------- #

load_dotenv()  # Load .env files for API keys etc.

API_URL: str = "https://www.alphavantage.co/query"
API_KEY: str | None = os.getenv("ALPHAVANTAGE_API_KEY")
if not API_KEY:
    logging.error("Missing ALPHAVANTAGE_API_KEY environment variable.")
    sys.exit(1)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Database helpers
# --------------------------------------------------------------------------- #


def init_db(db_path: str | Path) -> None:
    """
    Initialise the SQLite database and ensure that the required table exists.

    Parameters
    ----------
    db_path: str | Path
        Path to the SQLite database file.
    """
    create_table_sql = """
    CREATE TABLE IF NOT EXISTS price_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        price REAL NOT NULL,
        ts_utc TEXT NOT NULL,
        UNIQUE(symbol, ts_utc)
    );
    """
    try:
        with sqlite3.connect(db_path) as conn:
            conn.execute(create_table_sql)
        logger.debug("Database initialised at %s", db_path)
    except sqlite3.Error as exc:
        logger.exception("Failed to initialise database: %s", exc)
        raise


def store_price(
    db_path: str | Path,
    symbol: str,
    price: float,
    timestamp: datetime,
) -> None:
    """
    Insert a new price record into the database.

    Parameters
    ----------
    db_path: str | Path
        Path to the SQLite database file.
    symbol: str
        Stock ticker symbol.
    price: float
        Current price.
    timestamp: datetime
        UTC timestamp of the price.
    """
    insert_sql = """
    INSERT OR IGNORE INTO price_history (symbol, price, ts_utc)
    VALUES (?, ?, ?);
    """
    try:
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                insert_sql,
                (symbol.upper(), price, timestamp.isoformat()),
            )
        logger.debug("Stored %s price %.2f at %s", symbol, price, timestamp)
    except sqlite3.Error as exc:
        logger.exception("Failed to store price for %s: %s", symbol, exc)
        raise


def get_price_history(
    db_path: str | Path,
    symbol: str,
    limit: int,
) -> List[Tuple[datetime, float]]:
    """
    Retrieve the most recent price records for a symbol.

    Parameters
    ----------
    db_path: str | Path
        Path to the SQLite database file.
    symbol: str
        Stock ticker symbol.
    limit: int
        Maximum number of recent records to fetch.

    Returns
    -------
    List[Tuple[datetime, float]]
        List of (timestamp, price) tuples ordered from oldest to newest.
    """
    query_sql = """
    SELECT ts_utc, price FROM price_history
    WHERE symbol = ?
    ORDER BY ts_utc DESC
    LIMIT ?;
    """
    try:
        with sqlite3.connect(db_path) as conn:
            rows = conn.execute(query_sql, (symbol.upper(), limit)).fetchall()
        # rows are newest first; reverse for chronological order
        history = [
            (datetime.fromisoformat(ts), price) for ts, price in reversed(rows)
        ]
        logger.debug("Fetched %d records for %s", len(history), symbol)
        return history
    except sqlite3.Error as exc:
        logger.exception("Failed to fetch history for %s: %s", symbol, exc)
        raise
    except ValueError as exc:
        logger.exception("Timestamp parsing error: %s", exc)
        raise


# --------------------------------------------------------------------------- #
# API interaction
# --------------------------------------------------------------------------- #


def fetch_price(symbol: str, timeout: int = 10) -> float:
    """
    Retrieve the latest price for a given stock symbol from Alpha Vantage.

    Parameters
    ----------
    symbol: str
        Stock ticker symbol.
    timeout: int, optional
        HTTP request timeout in seconds (default: 10).

    Returns
    -------
    float
        Latest price.

    Raises
    ------
    RuntimeError
        If the API response is malformed or the request fails.
    """
    params = {
        "function": "GLOBAL_QUOTE",
        "symbol": symbol,
        "apikey": API_KEY,
    }
    try:
        response = requests.get(API_URL, params=params, timeout=timeout)
        response.raise_for_status()
        data = response.json()
        logger.debug("API response for %s: %s", symbol, json.dumps(data)[:200])
    except requests.RequestException as exc:
        logger.exception("HTTP request failed for %s: %s", symbol, exc)
        raise RuntimeError(f"Failed to fetch price for {symbol}") from exc
    except json.JSONDecodeError as exc:
        logger.exception("Invalid JSON response for %s: %s", symbol, exc)
        raise RuntimeError(f"Invalid API response for {symbol}") from exc

    quote_key = "Global Quote"
    price_key = "05. price"
    try:
        price_str = data[quote_key][price_key]
        price = float(price_str)
        logger.info("Fetched price for %s: %.2f", symbol, price)
        return price
    except (KeyError, TypeError, ValueError) as exc:
        logger.exception("Unexpected API format for %s: %s", symbol, exc)
        raise RuntimeError(f"Unexpected API format for {symbol}") from exc


# --------------------------------------------------------------------------- #
# Analysis utilities
# --------------------------------------------------------------------------- #


def simple_moving_average(
    values: Sequence[float],
    window: int,
) -> float:
    """
    Compute the simple moving average (SMA) of the last ``window`` values.

    Parameters
    ----------
    values: Sequence[float]
        Historical price values ordered chronologically.
    window: int
        Number of most recent points to include in the average.

    Returns
    -------
    float
        The SMA. If there are fewer than ``window`` points, the average of
        the available points is returned.

    Raises
    ------
    ValueError
        If ``window`` is less than 1 or ``values`` is empty.
    """
    if window < 1:
        raise ValueError("window must be at least 1")
    if not values:
        raise ValueError("values sequence is empty")
    recent = list(values)[-window:]
    avg = sum(recent) / len(recent)
    logger.debug("SMA (window=%d) over %d points = %.4f", window, len(recent), avg)
    return avg


def generate_signal(
    short_ma: float,
    long_ma: float,
    tolerance: float = 0.001,
) -> str:
    """
    Produce a trading signal based on SMA crossover.

    Parameters
    ----------
    short_ma: float
        Short‑term moving average.
    long_ma: float
        Long‑term moving average.
    tolerance: float, optional
        Relative tolerance to avoid flickering on near‑equal averages.

    Returns
    -------
    str
        One of ``"BUY"``, ``"SELL"``, or ``"HOLD"``.
    """
    if short_ma > long_ma * (1 + tolerance):
        signal = "BUY"
    elif short_ma < long_ma * (1 - tolerance):
        signal = "SELL"
    else:
        signal = "HOLD"
    logger.info(
        "Signal generated (short=%.4f, long=%.4f) -> %s", short_ma, long_ma, signal
    )
    return signal


# --------------------------------------------------------------------------- #
# Main orchestration
# --------------------------------------------------------------------------- #


def run_tracker(
    symbols: List[str],
    db_path: str | Path,
    short_window: int = 5,
    long_window: int = 20,
    poll_interval: int = 60,
) -> None:
    """
    Continuously fetch prices, store them, compute SMAs and emit signals.

    Parameters
    ----------
    symbols: List[str]
        Stock ticker symbols to monitor.
    db_path: str | Path
        Path to the SQLite database file.
    short_window: int, optional
        Window size for the short‑term SMA (default: 5).
    long_window: int, optional
        Window size for the long‑term SMA (default: 20).
    poll_interval: int, optional
        Seconds to wait between successive fetch cycles (default: 60).
    """
    if short_window >= long_window:
        raise ValueError("short_window must be smaller than long_window")

    init_db(db_path)

    try:
        while True:
            for symbol in symbols:
                try:
                    price = fetch_price(symbol)
                    now = datetime.utcnow()
                    store_price(db_path, symbol, price, now)

                    history = get_price_history(db_path, symbol, long_window)
                    prices = [p for _, p in history]

                    short_ma = simple_moving_average(prices, short_window)
                    long_ma = simple_moving_average(prices, long_window)

                    signal = generate_signal(short_ma, long_ma)
                    logger.info(
                        "Symbol: %s | Price: %.2f | Short MA: %.2f | Long MA: %.2f | Signal: %s",
                        symbol,
                        price,
                        short_ma,
                        long_ma,
                        signal,
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.error("Error processing %s: %s", symbol, exc, exc_info=True)

            logger.debug("Sleeping for %d seconds...", poll_interval)
            time.sleep(poll_interval)
    except KeyboardInterrupt:
        logger.info("Tracker stopped by user.")
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected error in main loop: %s", exc)
        raise


if __name__ == "__main__":
    # Simple CLI entry point
    import argparse

    parser = argparse.ArgumentParser(description="Run the stock price tracker.")
    parser.add_argument(
        "symbols",
        nargs="+",
        help="One or more stock ticker symbols (e.g., AAPL MSFT).",
    )
    parser.add_argument(
        "--db",
        default="price_history.db",
        help="SQLite database file path (default: price_history.db).",
    )
    parser.add_argument(
        "--short",
        type=int,
        default=5,
        help="Short‑term SMA window size (default: 5).",
    )
    parser.add_argument(
        "--long",
        type=int,
        default=20,
        help="Long‑term SMA window size (default: 20).",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=60,
        help="Polling interval in seconds (default: 60).",
    )
    args = parser.parse_args()

    run_tracker(
        symbols=args.symbols,
        db_path=args.db,
        short_window=args.short,
        long_window=args.long,
        poll_interval=args.interval,
    )