"""
URL Shortener Module

Provides functionality to encode long URLs into short codes, decode them back,
handle HTTP redirects, and track click counts. Uses SQLite for persistence
and follows security best practices.
"""

import hashlib
import sqlite3
import string
import secrets
import re
from typing import Optional, Tuple, Dict, Any
from urllib.parse import urlparse


# Constants
ALPHABET = string.ascii_letters + string.digits
CODE_LENGTH = 7
MAX_URL_LENGTH = 2048
MIN_URL_LENGTH = 10
MAX_ATTEMPTS = 5


class URLShortener:
    """
    A URL shortener service with persistence, click tracking, and validation.
    Uses SQLite database for storage.
    """

    def __init__(self, db_path: str = ":memory:") -> None:
        """
        Initialize the URL shortener with a database connection.

        Args:
            db_path: Path to the SQLite database file. Defaults to in-memory.

        Raises:
            sqlite3.Error: If database connection fails.
        """
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self) -> None:
        """Create the necessary database tables if they don't exist."""
        with self.conn:
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS urls (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    short_code TEXT UNIQUE NOT NULL,
                    long_url TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS clicks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    short_code TEXT NOT NULL,
                    clicked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    user_agent TEXT,
                    ip_address TEXT,
                    FOREIGN KEY (short_code) REFERENCES urls(short_code)
                )
            """)

    @staticmethod
    def _validate_url(url: str) -> bool:
        """
        Validate a URL for proper format and security.

        Args:
            url: The URL string to validate.

        Returns:
            True if the URL is valid, False otherwise.
        """
        if not isinstance(url, str):
            return False

        url = url.strip()
        if not url or len(url) > BASE_URL_LENGTH or len(url) < MIN_URL_LENGTH:
            return False

        # Basic URL structure validation
        pattern = re.compile(
            r'^https?://'  # scheme
            r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain...
            r'localhost|'  # localhost...
            r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or ip
            r'(?::\d+)?'  # optional port
            r'(?:/?|[/?]\S+)$', re.IGNORECASE)
        return bool(pattern.match(url))

    @staticmethod
    def _sanitize_input(input_str: str) -> str:
        """
        Sanitize input strings to prevent injection attacks.

        Args:
            input_str: The string to sanitize.

        Returns:
            Sanitized string.
        """
        if not isinstance(input_str, str):
            return ""
        # Remove any characters that aren't alphanumeric, basic punctuation, or URL-safe
        sanitized = re.sub(r'[^\w\-._~:/?#\[\]@!$&\'()*+,;=%]', '', input_str.strip())
        return sanitized

    def _generate_code(self, long_url: str) -> str:
        """
        Generate a unique short code for a URL using SHA-256 hashing.

        Args:
            long_url: The long URL to encode.

        Returns:
            A unique short code string.
        """
        for attempt in range(MAX_ATTEMPTS):
            # Add some randomness to avoid collisions
            salt = str(random.getrandbits(64))
            hash_input = f"{long_url}{salt}{attempt}".encode('utf-8')
            hash_digest = hashlib.sha256(hash_input).digest()

            # Convert hash to base62-like code
            code = ""
            for i in range(CODE_LENGTH):
                code += ALPHORET[hash_digest[i] % len(ALPHORET)]

            # Check if code already exists
            if not self._code_exists(code):
                return code

        raise RuntimeError("Failed to generate unique short code after maximum attempts")

    def _code_exists(self, code: str) -> bool:
        """
        Check if a short code already exists in the database.

        Args:
            code: The short code to check.

        Returns:
            True if the code exists, False otherwise.
        """
        cursor = self.conn.execute(
            "SELECT 1 FROM urls WHERE short_code = ? LIMIT 1",
            (code,)
        )
        return cursor.fetchone() is not None

    def encode(self, long_url: str) -> Dict[str, Any]:
        """
        Encode a long URL into a short code.

        Args:
            long_url: The long URL to shorten.

        Returns:
            Dictionary containing 'short_code' and 'long_url' on success.

        Raises:
            ValueError: If the URL is invalid or empty.
            RuntimeError: If code generation fails.
        """
        if not long_url or not isinstance(long_url, str):
            raise ValueError("URL must be a non-empty string")

        # Sanitize and validate
        sanitized_url = self._sanitize_input(long_url)
        if not self._validate_url(sanitized_url):
            raise ValueError(f"Invalid URL format: {sanitized_url}")

        # Check if URL already shortened
        cursor = self.conn.execute(
            "SELECT short_code FROM urls WHERE long_url = ? LIMIT 1",
            (sanitized_url,)
        )
        existing = cursor.fetchone()
        if existing:
            return {"short_code": existing["short_code"], "long_url": sanitized_url}

        # Generate new code
        short_code = self._generate_code(sanitized_url)

        # Store in database
        with self.conn:
            self.conn.execute(
                "INSERT INTO urls (short_code, long_url) VALUES (?, ?)",
                (short_code, sanitized_url)
            )

        return {"short_code": short_code, "long_url": sanitized_url}

    def decode(self, short_code: str) -> Optional[Dict[str, Any]]:
        """
        Decode a short code back to the original long URL.

        Args:
            short_code: The short code to decode.

        Returns:
            Dictionary with URL data if found, None otherwise.

        Raises:
            ValueError: If short_code is invalid.
        """
        if not short_code or not isinstance(short_code, str):
            raise ValueError("Short code must be a non-empty string")

        # Sanitize and validate short code format
        sanitized_code = self._sanitize_input(short_code)
        if not re.match(r'^[a-zA-Z0-9]+$', sanitized_code):
            raise ValueError("Invalid short code format")

        cursor = self.conn.execute(
            "SELECT short_code, long_url, created_at FROM urls WHERE short_code = ?",
            (sanitized_code,)
        )
        result = cursor.fetchone()
        if result is None:
            return None

        return {
            "short_code": result["short_code"],
            "long_url": result["long_url"],
            "created_at": result["created_at"]
        }

    def redirect(self, short_code: str, user_agent: Optional[str] = None,
                 ip_address: Optional[str] = None) -> Optional[str]:
        """
        Handle redirect by recording a click and returning the long URL.

        Args:
            short_code: The short code to redirect from.
            user_agent: Optional user agent string for tracking.
            ip_address: Optional IP address for tracking.

        Returns:
            The long URL if found, None otherwise.

        Raises:
            ValueError: If short_code is invalid.
        """
        decoded = self.decode(short_code)
        if decoded is None:
            return None

        # Record the click
        sanitized_ua = self._sanitize_input(user_agent) if user_agent else None
        sanitized_ip = self._sanitize_input(ip_address) if ip_address else None

        with self.conn:
            self.conn.execute(
                "INSERT INTO clicks (short_code, user_agent, ip_address) VALUES (?, ?, ?)",
                (decoded["short_code"], sanitized_ua, sanitized_ip)
            )

        return decoded["long_url"]

    def get_click_count(self, short_code: str) -> int:
        """
        Get the total number of clicks for a given short code.

        Args:
            short_code: The short code to query.

        Returns:
            Number of clicks recorded.

        Raises:
            ValueError: If short_code is invalid.
        """
        if not short_code or not isinstance(short_code, str):
            raise ValueError("Short code must be a non-empty string")

        sanitized_code = self._sanitize_input(short_code)
        if not re.match(r'^[a-zA-Z0-9]+$', sanitized_code):
            raise ValueError("Invalid short code format")

        cursor = self.conn.execute(
            "SELECT COUNT(*) as count FROM clicks WHERE short_code = ?",
            (sanitized_code,)
        )
        result = cursor.fetchone()
        return result["count"] if result else 0

    def get_stats(self, short_code: str) -> Optional[Dict[str, Any]]:
        """
        Get comprehensive statistics for a short code.

        Args:
            short_code: The short code to query.

        Returns:
            Dictionary with URL info and click count, or None if not found.

        Raises:
            ValueError: If short_code is invalid.
        """
        decoded = self.decode(short_code)
        if decoded is None:
            return None

        click_count = self.get_click_count(decoded["short_code"])
        return {
            **decoded,
            "click_count": click_count
        }

    def close(self) -> None:
        """Close the database connection."""
        if self.conn:
            self.conn.close()

    def __enter__(self) -> 'URLShortener':
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit with cleanup."""
        self.close()