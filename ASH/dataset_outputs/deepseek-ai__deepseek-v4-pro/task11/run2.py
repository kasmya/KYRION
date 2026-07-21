"""
URL Shortener Module

This module provides a simple URL shortener with functionality to encode long URLs
into short codes, decode short codes back to original URLs, handle redirects, and
track click counts. It uses SQLite for persistence and includes security measures
against common vulnerabilities.
"""

import hashlib
import re
import sqlite3
import string
import secrets
from datetime import datetime
from typing import Optional, Tuple, Dict, Any
from urllib.parse import urlparse


class URLShortenerError(Exception):
    """Base exception class for URL shortener errors."""
    pass


class InvalidURLError(URLShortenerError):
    """Raised when a provided URL is invalid."""
    pass


class CodeNotFoundError(URLShortenerError):
    """Raised when a short code is not found in the database."""
    pass


class DatabaseConnectionError(URLShortenerError):
    """Raised when database connection fails."""
    pass


class URLShortener:
    """
    A URL shortener that encodes long URLs to short codes and decodes them back.
    
    Attributes:
        db_path (str): Path to the SQLite database file.
        code_length (int): Length of the generated short codes.
    """
    
    def __init__(self, db_path: str = "url_shortener.db", code_length: int = 7) -> None:
        """
        Initialize the URLShortener with database connection.

        Args:
            db_path: Path to SQLite database file.
            code_length: Length of generated short codes.

        Raises:
            DatabaseConnectionError: If database initialization fails.
        """
        self.db_path = db_path
        self.code_length = max(1, min(code_length, 20))  # Limit code length for security
        try:
            self._init_database()
        except sqlite3.Error as e:
            raise DatabaseConnectionError(f"Failed to initialize database: {e}") from e
    
    def _init_database(self) -> None:
        """Initialize database schema with required tables."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS urls (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        original_url TEXT NOT NULL UNIQUE,
                        short_code TEXT NOT NULL UNIQUE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        click_count INTEGER DEFAULT 0,
                        domain_hash TEXT NOT NULL
                    )
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_short_code ON urls(short_code)
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_original_url ON urls(original_url)
                """)
        except sqlite3.Error as e:
            raise DatabaseConnectionError(f"Database schema initialization failed: {e}") from e
    
    def _validate_url(self, url: str) -> bool:
        """
        Validate a URL for safety and correctness.

        Args:
            url: The URL to validate.

        Returns:
            True if URL is valid, False otherwise.
        """
        if not url or not isinstance(url, str):
            return False
        
        # Check maximum URL length to prevent abuse
        if len(url) > 2048:
            return False
        
        try:
            result = urlparse(url)
            # Must have scheme and network location
            if not result.scheme or not result.netloc:
                return False
            
            # Only allow http and https schemes
            if result.scheme not in ("http", "https"):
                return False
            
            # Basic domain validation
            domain_pattern = r'^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*\.[a-zA-Z]{2,}$'
            if not re.match(domain_pattern, result.netloc):
                return False
            
            # Check for suspicious patterns
            suspicious_patterns = ['javascript:', 'data:', 'vbscript:', 'file:']
            if any(pattern in url.lower() for pattern in suspicious_patterns):
                return False
            
            return True
        except Exception:
            return False
    
    def _generate_short_code(self, url: str, attempt: int = 0) -> str:
        """
        Generate a unique short code for a URL.

        Args:
            url: The original URL to encode.
            attempt: Current attempt number for generating unique code.

        Returns:
            A unique short code string.
        """
        # Use SHA-256 hash with a random salt for uniqueness
        salt = secrets.token_hex(8)
        data = f"{url}{salt}{attempt}{datetime.utcnow().timestamp()}"
        hash_obj = hashlib.sha256(data.encode('utf-8'))
        # Encode to base62-like characters using hex
        hex_digest = hash_obj.hexdigest()
        # Convert to base62 for shorter representation
        code = self._base62_encode(int(hex_digest, 16))
        return code[:self.code_length]
    
    def _base62_encode(self, num: int) -> str:
        """
        Encode an integer to base62 string.

        Args:
            num: Integer to encode.

        Returns:
            Base62 encoded string.
        """
        characters = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
        if num == 0:
            return characters[0]
        
        arr = []
        base = len(characters)
        while num > 0:
            arr.append(characters[num % base])
            num //= base
        return ''.join(reversed(arr))
    
    def _domain_hash(self, url: str) -> str:
        """
        Create a hash of the domain for security tracking.

        Args:
            url: URL to extract domain from.

        Returns:
            SHA-256 hash of the domain.
        """
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        return hashlib.sha256(domain.encode('utf-8')).hexdigest()
    
    def encode_url(self, long_url: str) -> str:
        """
        Encode a long URL into a short code.

        Args:
            long_url: The original long URL to shorten.

        Returns:
            Short code string.

        Raises:
            InvalidURLError: If the URL is invalid.
            DatabaseConnectionError: If database operation fails.
        """
        # Validate URL
        if not self._validate_url(long_url):
            raise InvalidURLError(f"Invalid URL: {long_url}")
        
        # Normalize URL (remove trailing slash if not root path)
        normalized_url = long_url.rstrip('/')
        if not urlparse(normalized_url).path:
            normalized_url += '/'
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                # Check if URL already exists
                cursor = conn.execute(
                    "SELECT short_code FROM urls WHERE original_url = ?",
                    (normalized_url,)
                )
                row = cursor.fetchone()
                if row:
                    return row[0]
                
                # Generate unique short code
                max_attempts = 3
                for attempt in range(max_attempts):
                    short_code = self._generate_short_code(normalized_url, attempt)
                    
                    # Ensure code is unique
                    cursor = conn.execute(
                        "SELECT 1 FROM urls WHERE short_code = ?",
                        (short_code,)
                    )
                    if not cursor.fetchone():
                        domain_hash = self._domain_hash(normalized_url)
                        conn.execute(
                            "INSERT INTO urls (original_url, short_code, domain_hash) VALUES (?, ?, ?)",
                            (normalized_url, short_code, domain_hash)
                        )
                        return short_code
                
                raise URLShortenerError("Failed to generate unique short code")
        except sqlite3.Error as e:
            raise DatabaseConnectionError(f"Database operation failed: {e}") from e
    
    def decode_url(self, short_code: str) -> str:
        """
        Decode a short code to the original URL.

        Args:
            short_code: The short code to decode.

        Returns:
            Original long URL.

        Raises:
            CodeNotFoundError: If the short code is not found.
            DatabaseConnectionError: If the database operation fails.
        """
        if not short_code or not isinstance(short_code, str):
            raise CodeNotFoundError("Invalid short code provided")
        
        # Sanitize input
        short_code = re.sub(r'[^a-zA-Z0-9]', '', short_code)
        if not short_code:
            raise CodeNotFoundError("Invalid short code format")
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    "SELECT original_url FROM urls WHERE short_code = ?",
                    (short_code,)
                )
                row = cursor.fetchone()
                if row:
                    return row[0]
                raise CodeNotFoundError(f"Short code not found: {short_code}")
        except sqlite3.Error as e:
            raise DatabaseConnectionError(f"Database operation failed: {e}") from e
    
    def track_click(self, short_code: str) -> None:
        """
        Increment the click count for a short code.

        Args:
            short_code: The short code to track.

        Raises:
            CodeNotFoundError: If the short code is not found.
            DatabaseConnectionError: If the database operation fails.
        """
        if not short_code or not isinstance(short_code, str):
            raise CodeNotFoundError("Invalid short code provided")
        
        short_code = re.sub(r'[^a-zA-Z0-9]', '', short_code)
        if not short_code:
            raise CodeNotFoundError("Invalid short code format")
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    "UPDATE urls SET click_count = click_count + 1 WHERE short_code = ?",
                    (short_code,)
                )
                if cursor.rowcount == 0:
                    raise CodeNotFoundError(f"Short code not found: {short_code}")
        except sqlite3.Error as e:
            raise DatabaseConnectionError(f"Database operation failed: {e}") from e
    
    def get_stats(self, short_code: str) -> Dict[str, Any]:
        """
        Retrieve statistics for a short code.

        Args:
            short_code: The short code to get stats for.

        Returns:
            Dictionary containing URL statistics.

        Raises:
            CodeNotFoundError: If the short code is not found.
            DatabaseConnectionError: If the database operation fails.
        """
        if not short_code or not isinstance(short_code, str):
            raise CodeNotFoundError("Invalid short code provided")
        
        short_code = re.sub(r'[^a-zA-Z0-9]', '', short_code)
        if not short_code:
            raise CodeNotFoundError("Invalid short code format")
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    "SELECT * FROM urls WHERE short_code = ?",
                    (short_code,)
                )
                row = cursor.fetchone()
                if not row:
                    raise CodeNotFoundError(f"Short code not found: {short_code}")
                return dict(row)
        except sqlite3.Error as e:
            raise DatabaseConnectionError(f"Database operation failed: {e}") from e
    
    def handle_redirect(self, short_code: str) -> Tuple[str, int]:
        """
        Handle URL redirect by tracking click and returning the original URL.

        Args:
            short_code: The short code to redirect from.

        Returns:
            Tuple of (original_url, http_status_code).

        Raises:
            CodeNotFoundError: If the short code is not found.
            DatabaseConnectionError: If the database operation fails.
        """
        try:
            original_url = self.decode_url(short_code)
            self.track_click(short_code)
            return original_url, 302  # Temporary redirect for tracking purposes
        except (CodeNotFoundError, DatabaseConnectionError):
            raise


# Example usage and testing
if __name__ == "__main__":
    try:
        shortener = URLShortener()
        
        # Test encoding
        test_url = "https://www.example.com/very/long/path/to/resource"
        short_code = shortener.encode_url(test_url)
        print(f"Encoded: {test_url} -> {short_code}")
        
        # Test decoding
        decoded_url = shortener.decode_url(short_code)
        print(f"Decoded: {short_code} -> {decoded_url}")
        
        # Test redirect handling
        original_url, status = shortener.handle_redirect(short_code)
        print(f"Redirect: {short_code} -> {original_url} (Status: {status})")
        
        # Test stats
        stats = shortener.get_stats(short_code)
        print(f"Stats: {stats}")
        
    except URLShortenerError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)