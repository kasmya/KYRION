"""
Stock Price Tracker

Features:
- Fetch real‑time stock quotes from a public API.
- Store historical quotes in an SQLite database.
- Compute short‑ and long‑term moving averages.
- Generate simple buy/sell signals based on moving‑average crossovers.

Dependencies:
    - requests
    - pandas
Standard library only otherwise.
"""

from __future__ import annotations

import os
import sys
import time
import json
import logging
import sqlite3
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import requests
import pandas as pd

# --------------------------------------------------------------------------- #
# Configuration & Logging
# --------------------------------------------------------------------------- #

API_URL = "https://finnhub.io/api/v1/quote"
API_KEY_ENV = "FINNHUB_API_KEY"
DB_PATH = "stock_data.db"
REQUEST_TIMEOUT = 10  # seconds
MAX_RETRIES = 3
RETRY_BACKOFF = 2  # exponential backoff factor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("stock_tracker")


def get_api_key() -> str:
    """Retrieve the API key from the environment."""
    key = os.getenv(API_KEY_ENV)
    if not key:
        log.error("API key not set. Please define the %s environment variable.", API_KEY_ENV)
        raise EnvironmentError(f"Missing environment variable: {API_KEY_ENV}")
    return key


# --------------------------------------------------------------------------- #
# API Client
# --------------------------------------------------------------------------- #

class StockAPIError(RuntimeError):
    """Custom exception raised when the stock API request fails."""


class StockAPIClient:
    """Client for fetching real‑time stock quotes."""

    def __init__(self, api_key: str, session: Optional[requests.Session] = None) -> None:
        """
        Args:
            api_key: Finnhub API key.
            session: Optional custom ``requests.Session`` for advanced use‑cases.
        """
        self.api_key = api_key
        self.session = session or requests.Session()
        self.session.headers.update({"Accept": "application/json"})

    def _request(self, symbol: str) -> Dict[str, Any]:
        """Make a GET request with retries and exponential backoff."""
        params = {"symbol": symbol, "token": self.api_key}
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = self.session.get(
                    API_URL,
                    params=params,
                    timeout=REQUEST_TIMEOUT,
                    verify=True,  # enforce SSL verification
                )
                resp.raise_for_status()
                data = resp.json()
                if not isinstance(data, dict):
                    raise StockAPIError("Unexpected response format")
                return data
            except (requests.RequestException, json.JSONDecodeError) as exc:
                log.warning(
                    "API request failed for %s (attempt %d/%d): %s",
                    symbol,
                    attempt,
                    MAX_RETRIES,
                    exc,
                )
                if attempt == MAX_RETRIES:
                    raise StockAPIError(f"Failed to fetch data for {symbol}") from exc
                time.sleep(RETRY_BACKOFF ** (attempt - 1))

    def fetch_price(self, symbol: str) -> Tuple[float, datetime]:
        """
        Retrieve the latest price for ``symbol``.

        Returns:
            A tuple ``(price, timestamp)``.
        """
        raw = self._request(symbol)
        # Finnhub returns fields: c (current price), t (timestamp in Unix seconds)
        price = float(raw.get("c", 0.0))
        ts = datetime.utcfromtimestamp(int(raw.get("t", datetime.utcnow().timestamp())))
        log.debug("Fetched %s: price=%s timestamp=%s", symbol, price, ts.isoformat())
        return price, ts


# --------------------------------------------------------------------------- #
# Database Handler
# --------------------------------------------------------------------------- #

class DatabaseError(RuntimeError):
    """Error interacting with the SQLite database."""


class SQLiteDB:
    """Thin wrapper around SQLite for storing price history."""

    def __init__(self, db_path: str = DB_PATH) -> None:
        self.db_path = db_path
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        try:
            conn = sqlite3.connect(self.db_path, detect_types=sqlite3.PARSE_DECLTYPES)
            conn.execute("PRAGMA foreign_keys = ON;")
            return conn
        except sqlite3.Error as exc:
            raise DatabaseError("Unable to connect to SQLite database") from exc

    def _ensure_schema(self) -> None:
        """Create required table if it does not exist."""
        create_sql = """
        CREATE TABLE IF NOT EXISTS prices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            price REAL NOT NULL,
            ts TIMESTAMP NOT NULL,
            UNIQUE(symbol, ts)
        );
        """
        with self._connect() as conn:
            conn.execute(create_sql)
            conn.commit()

    def insert_price(self, symbol: str, price: float, ts: datetime) -> None:
        """Insert a single price point. Duplicate timestamps are ignored."""
        sql = """
        INSERT OR IGNORE INTO prices (symbol, price, ts)
        VALUES (?, ?, ?);
        """
        try:
            with self._connect() as conn:
                conn.execute(sql, (symbol, price, ts))
                conn.commit()
            log.debug("Inserted %s price %.4f at %s", symbol, price, ts.isoformat())
        except sqlite3.Error as exc:
            raise DatabaseError("Failed to insert price data") from exc

    def fetch_history(
        self,
        symbol: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> pd.DataFrame:
        """
        Return historical price data as a pandas DataFrame.

        Columns: ['ts', 'price']
        """
        sql = "SELECT ts, price FROM prices WHERE symbol = ?"
        params: List[Any] = [symbol]

        if start:
            sql += " AND ts >= ?"
            params.append(start)
        if end:
            sql += " AND ts <= ?"
            params.append(end)

        sql += " ORDER BY ts ASC;"

        try:
            with self._connect() as conn:
                df = pd.read_sql_query(sql, conn, params=params, parse_dates=["ts"])
            return df
        except (sqlite3.Error, pd.io.sql.DatabaseError) as exc:
            raise DatabaseError("Failed to fetch historical data") from exc


# --------------------------------------------------------------------------- #
# Core Logic: Moving Average & Signal Generation
# --------------------------------------------------------------------------- #

class Signal(str):
    """Enum‑like class for signalling."""
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


def calculate_moving_average(
    df: pd.DataFrame,
    window: int,
    column: str = "price",
) -> pd.Series:
    """
    Compute the simple moving average (SMA) on ``column`` over ``window`` periods.
    """
    if window <= 0:
        raise ValueError("window must be a positive integer")
    return df[column].rolling(window=window, min_periods=1).mean()


def generate_signals(
    df: pd.DataFrame,
    short_window: int,
    long_window: int,
) -> pd.DataFrame:
    """
    Generate BUY/SELL/HOLD signals based on SMA crossovers.

    - BUY: short SMA crosses above long SMA.
    - SELL: short SMA crosses below long SMA.
    - HOLD: otherwise.

    Returns the original DataFrame with additional columns:
        - short_sma
        - long_sma
        - signal
    """
    if short_window >= long_window:
        raise ValueError("short_window must be smaller than long_window")

    df = df.copy()
    df["short_sma"] = calculate_moving_average(df, short_window)
    df["long_sma"] = calculate_moving_average(df, long_window)

    # Determine crossovers
    df["prev_short"] = df["short_sma"].shift(1)
    df["prev_long"] = df["long_sma"].shift(1)

    conditions = [