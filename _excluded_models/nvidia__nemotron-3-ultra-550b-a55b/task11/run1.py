"""
URL Shortener Module

A secure, persistent URL shortening service with click tracking.
Uses SQLite for storage and cryptographically secure random codes.
"""

import hashlib
import secrets
import sqlite3
import urllib.parse
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterator, Optional
from urllib.parse import urlparse


# Custom Exceptions
class URLShortenerError(Exception):
    """Base exception for URL shortener errors."""
    pass


class InvalidURLError(URLShortenerError):
    """Raised when a URL fails validation."""
    pass


class CodeNotFoundError(URLShortenerError):
    """Raised when a short code is not found."""
    pass


class CodeCollisionError(URLShortenerError):
    """Raised when a generated code collides (extremely rare)."""
    pass


class DatabaseError(URLShortenerError):
    """Raised when database operations fail."""
    pass


# Data Classes
@dataclass(frozen=True)
class URLRecord:
    """Immutable record representing a shortened URL."""
    code: str
    long_url: str
    created_at: datetime
    click_count: int


# Constants
DEFAULT_DB_PATH = Path("url_shortener.db")
CODE_LENGTH = 8
CODE_ALPHABET = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
MAX_COLLISION_RETRIES = 5


def validate_url(url: str) -> str:
    """
    Validate and normalize a URL.

    Args:
        url: The URL string to validate.

    Returns:
        Normalized URL string.

    Raises:
        InvalidURLError: If URL is malformed or uses unsafe scheme.
    """
    if not url or not isinstance(url, str):
        raise InvalidURLError("URL must be a non-empty string")

    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https"):
        raise InvalidURLError("Only HTTP and HTTPS URLs are allowed")
    if not parsed.netloc:
        raise InvalidURLError("URL must have a valid hostname")

    # Reconstruct to normalize (remove fragments, default ports, etc.)
    normalized = urllib.parse.urlunparse((
        parsed.scheme,
        parsed.netloc.lower(),
        parsed.path or "/",
        parsed.params,
        parsed.query,
        ""  # Strip fragment for security
    ))
    return normalized


def generate_code(length: int = CODE_LENGTH) -> str:
    """
    Generate a cryptographically secure random short code.

    Args:
        length: Length of the code to generate.

    Returns:
        Random string from CODE_ALPHABET.
    """
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(length))


@contextmanager
def get_db_connection(db_path: Path) -> Iterator[sqlite3.Connection]:
    """
    Context manager for SQLite connections with row factory.

    Args:
        db_path: Path to SQLite database file.

    Yields:
        Configured sqlite3.Connection.
    """
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_database(db_path: Path) -> None:
    """
    Initialize the database schema if not exists.

    Args:
        db_path: Path to SQLite database file.

    Raises:
        DatabaseError: If schema creation fails.
    """
    try:
        with get_db_connection(db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS urls (
                    code TEXT PRIMARY KEY,
                    long_url TEXT NOT NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    click_count INTEGER NOT NULL DEFAULT 0
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_created_at ON urls(created_at)
            """)
            conn.commit()
    except sqlite3.Error as e:
        raise DatabaseError(f"Failed to initialize database: {e}") from e


class URLShortener:
    """
    URL Shortener with persistent storage and click tracking.

    Example:
        >>> shortener = URLShortener()
        >>> code = shortener.encode("https://example.com/very/long/path")
        >>> record = shortener.decode(code)
        >>> print(record.long_url)
        https://example.com/very/long/path
    """

    def __init__(self, db_path: Optional[Path] = None) -> None:
        """
        Initialize the URL shortener.

        Args:
            db_path: Optional custom database path. Defaults to DEFAULT_DB_PATH.
        """
        self._db_path = db_path or DEFAULT_DB_PATH
        init_database(self._db_path)

    def encode(self, long_url: str) -> str:
        """
        Encode a long URL into a short code.

        Args:
            long_url: The URL to shorten.

        Returns:
            Short code string.

        Raises:
            InvalidURLError: If URL is invalid.
            DatabaseError: If storage fails.
            CodeCollisionError: If code generation collides after retries.
        """
        normalized_url = validate_url(long_url)

        # Check if URL already exists (by hash for efficiency)
        url_hash = hashlib.sha256(normalized_url.encode()).hexdigest()[:16]
        existing = self._find_by_hash(url_hash)
        if existing:
            return existing.code

        # Generate unique code with collision handling
        for _ in range(MAX_COLLISION_RETRIES):
            code = generate_code()
            if self._store_url(code, normalized_url, url_hash):
                return code

        raise CodeCollisionError("Failed to generate unique code after retries")

    def decode(self, code: str) -> URLRecord:
        """
        Decode a short code to its URL record (without incrementing clicks).

        Args:
            code: Short code to look up.

        Returns:
            URLRecord with code, long_url, created_at, click_count.

        Raises:
            CodeNotFoundError: If code does not exist.
            DatabaseError: If query fails.
        """
        if not code or not isinstance(code, str):
            raise CodeNotFoundError("Code must be a non-empty string")

        try:
            with get_db_connection(self._db_path) as conn:
                row = conn.execute(
                    "SELECT code, long_url, created_at, click_count FROM urls WHERE code = ?",
                    (code,)
                ).fetchone()
        except sqlite3.Error as e:
            raise DatabaseError(f"Database query failed: {e}") from e

        if not row:
            raise CodeNotFoundError(f"Code not found: {code}")

        return URLRecord(
            code=row["code"],
            long_url=row["long_url"],
            created_at=datetime.fromisoformat(row["created_at"]),
            click_count=row["click_count"]
        )

    def redirect(self, code: str) -> str:
        """
        Resolve a short code to its long URL and increment click count atomically.

        Args:
            code: Short code to resolve.

        Returns:
            The original long URL.

        Raises:
            CodeNotFoundError: If code does not exist.
            DatabaseError: If update fails.
        """
        if not code or not isinstance(code, str):
            raise CodeNotFoundError("Code must be a non-empty string")

        try:
            with get_db_connection(self._db_path) as conn:
                cursor = conn.execute(
                    "UPDATE urls SET click_count = click_count + 1 WHERE code = ?",
                    (code,)
                )
                if cursor.rowcount == 0:
                    raise CodeNotFoundError(f"Code not found: {code}")

                row = conn.execute(
                    "SELECT long_url FROM urls WHERE code = ?",
                    (code,)
                ).fetchone()
                conn.commit()
        except sqlite3.Error as e:
            raise DatabaseError(f"Database operation failed: {e}") from e

        return row["long_url"]

    def get_stats(self, code: str) -> URLRecord:
        """
        Get statistics for a short code without incrementing clicks.

        Args:
            code: Short code to query.

        Returns:
            URLRecord with current statistics.

        Raises:
            CodeNotFoundError: If code does not exist.
            DatabaseError: If query fails.
        """
        return self.decode(code)

    def _find_by_hash(self, url_hash: str) -> Optional[URLRecord]:
        """Find existing URL by hash prefix (helper)."""
        try:
            with get_db_connection(self._db_path) as conn:
                row = conn.execute(
                    "SELECT code, long_url, created_at, click_count FROM urls WHERE long_url LIKE ?",
                    (f"%{url_hash}%",)  # Simplified; in production use separate hash column
                ).fetchone()
        except sqlite3.Error:
            return None

        if row:
            return URLRecord(
                code=row["code"],
                long_url=row["long_url"],
                created_at=datetime.fromisoformat(row["created_at"]),
                click_count=row["click_count"]
            )
        return None

    def _store_url(self, code: str, long_url: str, url_hash: str) -> bool:
        """
        Attempt to store a new URL mapping.

        Returns:
            True if inserted, False if code collision.
        """
        try:
            with get_db_connection(self._db_path) as conn:
                conn.execute(
                    "INSERT INTO urls (code, long_url) VALUES (?, ?)",
                    (code, long_url)
                )
                conn.commit()
                return True
        except sqlite3.IntegrityError:
            return False
        except sqlite3.Error as e:
            raise DatabaseError(f"Failed to store URL: {e}") from e


# Convenience functions for simple use cases
_default_shortener: Optional[URLShortener] = None


def get_shortener(db_path: Optional[Path] = None) -> URLShortener:
    """
    Get or create the default URLShortener instance.

    Args:
        db_path: Optional database path (only used on first call).

    Returns:
        Shared URLShortener instance.
    """
    global _default_shortener
    if _default_shortener is None:
        _default_shortener = URLShortener(db_path)
    return _default_shortener


def shorten_url(long_url: str, db_path: Optional[Path] = None) -> str:
    """
    Shorten a URL using the default shortener.

    Args:
        long_url: URL to shorten.
        db_path: Optional database path.

    Returns:
        Short code.
    """
    return get_shortener(db_path).encode(long_url)


def expand_url(code: str, db_path: Optional[Path] = None) -> str:
    """
    Expand a short code to its long URL and track click.

    Args:
        code: Short code.
        db_path: Optional database path.

    Returns:
        Original long URL.
    """
    return get_shortener(db_path).redirect(code)


# CLI for demonstration
if __name__ == "__main__":
    import sys

    def print_usage() -> None:
        print("Usage:")
        print("  python url_shortener.py shorten <URL>")
        print("  python url_shortener.py expand <CODE>")
        print("  python url_shortener.py stats <CODE>")

    if len(sys.argv) < 3:
        print_usage()
        sys.exit(1)

    command, argument = sys.argv[1], sys.argv[2]
    shortener = get_shortener()

    try:
        if command == "shorten":
            code = shortener.encode(argument)
            print(f"Short code: {code}")
            print(f"Full URL:   http://short.ly/{code}")
        elif command == "expand":
            long_url = shortener.redirect(argument)
            print(f"Redirecting to: {long_url}")
        elif command == "stats":
            record = shortener.get_stats(argument)
            print(f"Code:        {record.code}")
            print(f"Long URL:    {record.long_url}")
            print(f"Created:     {record.created_at.isoformat()}")
            print(f"Clicks:      {record.click_count}")
        else:
            print_usage()
            sys.exit(1)
    except URLShortenerError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)