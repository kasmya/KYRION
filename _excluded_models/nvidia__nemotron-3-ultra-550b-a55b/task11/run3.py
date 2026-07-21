"""
URL Shortener Module

This module provides a URL shortening service with encoding, decoding,
redirect handling, and click tracking capabilities. It uses secure random
generation for short codes and validates URLs to prevent open redirects.

Example:
    >>> shortener = URLShortener()
    >>> code = shortener.encode("https://example.com/very/long/url")
    >>> print(code)
    'aB3dEf'
    >>> original = shortener.decode(code)
    >>> print(original)
    'https://example.com/very/long/url'
    >>> shortener.increment_click_count(code)
    >>> clicks = shortener.get_click_count(code)
    >>> print(clicks)
    1
"""

import secrets
import string
import urllib.parse
from typing import Dict, Optional


class InvalidURLError(ValueError):
    """Raised when a URL fails validation checks."""
    pass


class ShortCodeNotFoundError(KeyError):
    """Raised when a short code is not found in the store."""
    pass


class URLShortener:
    """
    A URL shortener that encodes long URLs to short codes, decodes them back,
    handles redirects, and tracks click counts.

    Attributes:
        _url_map: Maps short codes to long URLs.
        _click_counts: Maps short codes to their click counts.
        _code_length: Length of generated short codes.
        _allowed_schemes: Set of allowed URL schemes for security.
    """

    def __init__(
        self,
        code_length: int = 6,
        allowed_schemes: Optional[set] = None
    ) -> None:
        """
        Initialize the URL shortener.

        Args:
            code_length: Length of generated short codes (default: 6).
            allowed_schemes: Set of allowed URL schemes (default: {'http', 'https'}).
        """
        self._url_map: Dict[str, str] = {}
        self._click_counts: Dict[str, int] = {}
        self._code_length = code_length
        self._allowed_schemes = allowed_schemes or {"http", "https"}
        self._alphabet = string.ascii_letters + string.digits

    def _validate_url(self, url: str) -> None:
        """
        Validate a URL for security and correctness.

        Args:
            url: The URL to validate.

        Raises:
            InvalidURLError: If the URL is invalid or uses a disallowed scheme.
        """
        if not url or not isinstance(url, str):
            raise InvalidURLError("URL must be a non-empty string")

        parsed = urllib.parse.urlparse(url)
        if not parsed.scheme:
            raise InvalidURLError("URL must have a scheme (e.g., http, https)")
        if parsed.scheme.lower() not in self._allowed_schemes:
            raise InvalidURLError(
                f"URL scheme '{parsed.scheme}' is not allowed. "
                f"Allowed schemes: {self._allowed_schemes}"
            )
        if not parsed.netloc:
            raise InvalidURLError("URL must have a network location (domain)")

    def _generate_short_code(self) -> str:
        """
        Generate a cryptographically secure random short code.

        Returns:
            A random alphanumeric string of length `self._code_length`.
        """
        return "".join(secrets.choice(self._alphabet) for _ in range(self._code_length))

    def encode(self, long_url: str) -> str:
        """
        Encode a long URL to a short code.

        Args:
            long_url: The long URL to shorten.

        Returns:
            The generated short code.

        Raises:
            InvalidURLError: If the URL is invalid.
        """
        self._validate_url(long_url)

        # Check if URL already exists to avoid duplicates
        for code, url in self._url_map.items():
            if url == long_url:
                return code

        # Generate unique short code
        while True:
            short_code = self._generate_short_code()
            if short_code not in self._url_map:
                break

        self._url_map[short_code] = long_url
        self._click_counts[short_code] = 0
        return short_code

    def decode(self, short_code: str) -> str:
        """
        Decode a short code back to the original long URL.

        Args:
            short_code: The short code to decode.

        Returns:
            The original long URL.

        Raises:
            ShortCodeNotFoundError: If the short code doesn't exist.
        """
        if short_code not in self._url_map:
            raise ShortCodeNotFoundError(f"Short code '{short_code}' not found")
        return self._url_map[short_code]

    def get_redirect_url(self, short_code: str) -> str:
        """
        Get the redirect URL for a short code (alias for decode).

        Args:
            short_code: The short code to resolve.

        Returns:
            The long URL for redirection.

        Raises:
            ShortCodeNotFoundError: If the short code doesn't exist.
        """
        return self.decode(short_code)

    def increment_click_count(self, short_code: str) -> None:
        """
        Increment the click count for a short code.

        Args:
            short_code: The short code to increment.

        Raises:
            ShortCodeNotFoundError: If the short code doesn't exist.
        """
        if short_code not in self._click_counts:
            raise ShortCodeNotFoundError(f"Short code '{short_code}' not found")
        self._click_counts[short_code] += 1

    def get_click_count(self, short_code: str) -> int:
        """
        Get the click count for a short code.

        Args:
            short_code: The short code to query.

        Returns:
            The number of clicks for the short code.

        Raises:
            ShortCodeNotFoundError: If the short code doesn't exist.
        """
        if short_code not in self._click_counts:
            raise ShortCodeNotFoundError(f"Short code '{short_code}' not found")
        return self._click_counts[short_code]

    def get_stats(self, short_code: str) -> Dict[str, object]:
        """
        Get statistics for a short code.

        Args:
            short_code: The short code to query.

        Returns:
            Dictionary with 'long_url' and 'click_count'.

        Raises:
            ShortCodeNotFoundError: If the short code doesn't exist.
        """
        if short_code not in self._url_map:
            raise ShortCodeNotFoundError(f"Short code '{short_code}' not found")
        return {
            "long_url": self._url_map[short_code],
            "click_count": self._click_counts[short_code]
        }

    def list_all(self) -> Dict[str, Dict[str, object]]:
        """
        List all stored short codes with their URLs and click counts.

        Returns:
            Dictionary mapping short codes to their stats.
        """
        return {
            code: {"long_url": url, "click_count": self._click_counts[code]}
            for code, url in self._url_map.items()
        }