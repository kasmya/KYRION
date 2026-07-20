"""Stock price tracker with real‑time fetching, persistence, SMA calculation,
and simple buy/sell signal generation.

Dependencies:
    - requests
    - pandas
    - python standard library (sqlite3, logging, datetime, os, typing)
"""

import os
import logging
import sqlite3
from datetime import datetime
from typing import List, Tuple, Optional, Dict

import requests
import pandas as pd

# --------------------------------------------------------------------------- #
# Configuration & Logging
# --------------------------------------------------------------------------- #

API_ENDPOINT = "https://api.example.com/v1/quote"
API_KEY_ENV = "STOCK_API_KEY"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# API Client
# --------------------------------------------------------------------------- #


class StockAPIError(RuntimeError):
    """Raised when the external stock API returns an error or is unreachable."""


class StockAPIClient:
    """Thin wrapper around the external stock price API.

    The client expects an API key stored in the environment variable
    defined by ``API_KEY_ENV`` and sends it using the ``Authorization`` header.
    """

    def __init__(self, api_key: Optional[str] = None) -> None:
        self.api_key = api_key or os.getenv(API_KEY_ENV)
        if not self.api_key:
            raise ValueError(
                f"API key not found. Set the environment variable {API_KEY_ENV}."
            )
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {self.api_key}"})

    def fetch_price(self, symbol: str) -> Tuple[datetime, float]:
        """Fetch the latest price for ``symbol`` from the API.

        Returns:
            A tuple of (timestamp, price).

        Raises:
            StockAPIError: If the request fails or the response is malformed.
        """
        try:
            resp = self.session.get(API_ENDPOINT, params={"symbol": symbol}, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            # Expected JSON format: {"symbol": "...", "price": 123.45, "timestamp": "2023-01-01T12:00:00Z"}
            price = float(data["price"])
            ts_str = data["timestamp"]
            timestamp = datetime.fromisoformat(ts_str.rstrip("Z"))
            logger.debug("Fetched %s price: %s at %s", symbol, price, timestamp)
            return timestamp, price
        except (requests.RequestException, KeyError, ValueError) as exc:
            logger.error("Failed to fetch price for %s: %s", symbol, exc)
            raise StockAPIError(f"Unable to fetch price for {symbol}") from exc


# --------------------------------------------------------------------------- #
# Database Manager
# --------------------------------------------------------------------------- #


class DatabaseManager:
    """Handles SQLite persistence of historical stock prices."""

    def __init__(self, db_path: str = "stock_data.db") -> None:
        self.db_path = db_path
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, detect_types=sqlite3.PARSE_DECLTYPES)
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS stock_prices (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    timestamp TIMESTAMP NOT NULL,
                    price REAL NOT NULL,
                    UNIQUE(symbol, timestamp)
                );
                """
            )
            conn.commit()

    def insert_price(
        self, symbol: str, timestamp: datetime, price: float
    ) -> None:
        """Insert a price record; ignores duplicates."""
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO stock_prices (symbol, timestamp, price)
                    VALUES (?, ?, ?);
                    """,
                    (symbol, timestamp, price),
                )
                conn.commit()
                logger.debug("Inserted price for %s at %s", symbol, timestamp)
        except sqlite3.DatabaseError as exc:
            logger.error("Database error while inserting price: %s", exc)
            raise

    def fetch_history(
        self, symbol: str, start: Optional[datetime] = None, end: Optional[datetime] = None
    ) -> pd.DataFrame:
        """Return historical price data as a DataFrame sorted by timestamp."""
        query = "SELECT timestamp, price FROM stock_prices WHERE symbol = ?"
        params: List = [symbol]

        if start:
            query += " AND timestamp >= ?"
            params.append(start)
        if end:
            query += " AND timestamp <= ?"
            params.append(end)

        query += " ORDER BY timestamp ASC;"

        with self._connect() as conn:
            df = pd.read_sql_query(query, conn, params=params, parse_dates=["timestamp"])
        logger.debug("Fetched %d rows for %s", len(df), symbol)
        return df


# --------------------------------------------------------------------------- #
# Tracker & Signal Logic
# --------------------------------------------------------------------------- #


class Signal(str):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class StockTracker:
    """Main orchestrator: fetches live prices, stores them, computes SMA,
    and generates signals.
    """

    def __init__(
        self,
        api_client: StockAPIClient,
        db_manager: DatabaseManager,
        sma_window: int = 20,
    ) -> None:
        self.api = api_client
        self.db = db_manager
        self.sma_window = sma_window

    def update_price(self, symbol: str) -> None:
        """Fetch latest price and persist it."""
        ts, price = self.api.fetch_price(symbol)
        self.db.insert_price(symbol, ts, price)

    def compute_sma(self, symbol: str) -> pd.Series:
        """Calculate the simple moving average (SMA) over the configured window.

        Returns:
            pandas Series indexed by timestamp containing SMA values.
        """
        df = self.db.fetch_history(symbol)
        if df.empty:
            raise ValueError(f"No price data for symbol {symbol}")
        series = df.set_index("timestamp")["price"]
        sma = series.rolling(window=self.sma_window, min_periods=1).mean()
        logger.debug("Computed SMA for %s", symbol)
        return sma

    def generate_signal(self, symbol: str) -> str:
        """Generate a BUY/SELL/HOLD signal based on the latest price crossing SMA.

        Logic:
            - BUY  when price crosses above SMA.
            - SELL when price crosses below SMA.
            - HOLD otherwise.

        Returns:
            One of the values in ``Signal``.
        """
        df = self.db.fetch_history(symbol)
        if len(df) < 2:
            return Signal.HOLD

        df = df.sort_values("timestamp")
        df["sma"] = df["price"].rolling(window=self.sma_window, min_periods=1).mean()
        latest = df.iloc[-1]
        previous = df.iloc[-2]

        # Detect crossing
        if previous["price"] <= previous["sma"] and latest["price"] > latest["sma"]:
            logger.info("Signal BUY for %s", symbol)
            return Signal.BUY
        if previous["price"] >= previous["sma"] and latest["price"] < latest["sma"]:
            logger.info("Signal SELL for %s", symbol)
            return Signal.SELL
        return Signal.HOLD

    def run_cycle(self, symbols: List[str]) -> Dict[str, str]:
        """Execute a full update‑fetch‑signal cycle for a list of symbols.

        Returns:
            Mapping of symbol -> generated signal.
        """
        signals: Dict[str, str] = {}
        for sym in symbols:
            try:
                self.update_price(sym)
                signal = self.generate_signal(sym)
                signals[sym] = signal
            except (StockAPIError, ValueError, sqlite3.DatabaseError) as exc:
                logger.error("Error processing %s: %s", sym, exc)
                signals[sym] = Signal.HOLD
        return signals


# --------------------------------------------------------------------------- #
# Example usage (can be removed or adapted for production)
# --------------------------------------------------------------------------- #

if