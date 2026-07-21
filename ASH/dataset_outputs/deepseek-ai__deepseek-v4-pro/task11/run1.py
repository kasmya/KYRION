"""
URL Shortener Module

Provides functionality to encode long URLs into short codes, decode short codes
back to original URLs, handle HTTP redirects, and track click counts.
Security measures include URL validation, code sanitization, and protection
against open redirect vulnerabilities.
"""

import hashlib
import re
import string
import threading
from typing import Dict, Optional, Tuple
from urllib.parse import urlparse

import validators  # widely-used PyPI package for URL validation


class URLShortener:
    """
    A thread-safe URL shortener with click tracking and redirect handling.

    Attributes:
        url_map (Dict[str, str]): Mapping from short codes to original URLs.
        click_counts (Dict[str, int]): Click counts per short code.
        lock (threading.Lock): Mutex for thread-safe operations.
        base_url (str): Base URL for constructing full short URLs.
        code_length (int): Length of generated short codes.
    """

    # Allowed characters for short codes (alphanumeric, no ambiguous chars)
    _CODE_ALPHABET = string.ascii_letters + string.digits
    _CODE_ALPHABET = _CODE_ALPHABET.translate(
        str.maketrans("", "", "0OIl1")
    )  # Remove ambiguous characters

    # Maximum URL length to prevent abuse
    _MAX_URL_LENGTH = 2048

    # Allowed URL schemes
    _ALLOWED_SCHEMES = {"http", "https"}

    def __init__(
        self, base_url: str = "http://short.url", code_length: int = 8
    ) -> None:
        """
        Initialize the URL shortener.

        Args:
            base_url: The base URL for constructing full short URLs.
            code_length: Length of generated short codes (default 8).

        Raises:
            ValueError: If base_url is invalid or code_length is not positive.
        """
        if not isinstance(base_url, str) or not base_url.strip():
            raise ValueError("base_url must be a non-empty string")
        if not isinstance(code_length, int) or code_length < 4:
            raise ValueError("code_length must be an integer >= 4")

        # Validate and normalize base_url
        parsed = urlparse(base_url)
        if parsed.scheme not in self._ALLOWED_SCHEMES:
            raise ValueError(
                f"base_url must use one of {self._ALLOWED_SCHEMES} scheme"
            )
        if not parsed.netloc:
            raise ValueError("base_url must have a valid hostname")

        self.url_map: Dict[str, str] = {}
        self.click_counts: Dict[str, int] = {}
        self.lock = threading.Lock()
        self.base_url = base_url.rstrip("/")
        self.code_length = code_length

    def _generate_code(self, url: str) -> str:
        """
        Generate a unique short code for a given URL using SHA-256 hashing.

        Args:
            url: The URL to generate a code for.

        Returns:
            A short code string of specified length.
        """
        # Use SHA-256 for collision-resistant hashing
        hash_obj = hashlib.sha256(url.encode("utf-8"))
        hash_hex = hash_obj.hexdigest()

        # Convert hash to base-N using our alphabet
        base = len(self._CODE_ALPHABET)
        num = int(hash_hex, 16)

        code = []
        while len(code) < self.code_length:
            num, remainder = divmod(num, base)
            code.append(self._CODE_ALPHABET[remainder])

        return "".join(code)

    def _sanitize_code(self, code: str) -> str:
        """
        Sanitize a short code to prevent injection attacks.

        Args:
            code: The short code to sanitize.

        Returns:
            Sanitized code containing only valid characters.

        Raises:
            ValueError: If code is empty or contains invalid characters.
        """
        if not code or not isinstance(code, str):
            raise ValueError("Short code must be a non-empty string")

        # Only allow alphanumeric characters and hyphens
        sanitized = re.sub(r"[^a-zA-Z0-9\-_]", "", code)
        if not sanitized:
            raise ValueError("Short code contains no valid characters")
        if sanitized != code:
            raise ValueError("Short code contains invalid characters")
        return sanitized

    def _validate_url(self, url: str) -> str:
        """
        Validate and normalize a URL for security.

        Args:
            url: The URL to validate.

        Returns:
            Normalized URL string.

        Raises:
            ValueError: If URL is invalid, too long, or uses disallowed scheme.
        """
        if not isinstance(url, str) or not url.strip():
            raise ValueError("URL must be a non-empty string")

        if len(url) > self._MAX_URL_LENGTH:
            raise ValueError(
                f"URL exceeds maximum length of {self._MAX_URL_LENGTH}"
            )

        # Use validators library for comprehensive URL validation
        if not validators.url(url):
            raise ValueError("Invalid URL format")

        parsed = urlparse(url)
        if parsed.scheme not in self._ALLOWED_SCHEMES:
            raise ValueError(
                f"URL scheme must be one of {self._ALLOWED_SCHEMES}"
            )

        # Check for open redirect patterns (URLs that redirect to other domains)
        # Reject URLs with suspicious redirect parameters
        redirect_params = ["url", "redirect", "next", "target", "goto", "return"]
        query = parsed.query.lower()
        for param in redirect_params:
            if f"{param}=" in query:
                raise ValueError(
                    "URL contains potential open redirect parameter"
                )

        # Normalize: remove default ports, lowercase scheme and host
        normalized = parsed._replace(
            scheme=parsed.scheme.lower(),
            netloc=parsed.hostname.lower()
            + (f":{parsed.port}" if parsed.port else ""),
        ).geturl()

        return normalized

    def encode(self, long_url: str) -> str:
        """
        Encode a long URL into a short URL.

        Args:
            long_url: The original long URL to shorten.

        Returns:
            The full short URL (base_url + short code).

        Raises:
            ValueError: If the URL is invalid or cannot be encoded.
        """
        # Validate the URL
        normalized_url = self._validate_url(long_url)

        with self.lock:
            # Check if URL already has a code (reverse lookup)
            for existing_code, existing_url in self.url_map.items():
                if existing_url == normalized_url:
                    return f"{self.base_url}/{existing_code}"

            # Generate a new unique code
            max_attempts = 10
            for attempt in range(max_attempts):
                code = self._generate_code(
                    normalized_url + str(attempt) if attempt > 0 else normalized_url
                )
                if code not in self.url_map:
                    self.url_map[code] = normalized_url
                    self.click_counts[code] = 0
                    return f"{self.base_url}/{code}"

            raise RuntimeError(
                "Failed to generate unique short code after multiple attempts"
            )

    def decode(self, short_code: str) -> str:
        """
        Decode a short code back to the original URL.

        Args:
            short_code: The short code to decode.

        Returns:
            The original long URL.

        Raises:
            KeyError: If the short code does not exist.
            ValueError: If the short code format is invalid.
        """
        code = self._sanitize_code(short_code)

        with self.lock:
            if code not in self.url_map:
                raise KeyError(f"Short code '{code}' not found")
            return self.url_map[code]

    def get_redirect_url(self, short_code: str) -> str:
        """
        Get the redirect URL for a short code and increment click count.
        This is the main method to call when handling an incoming short URL request.

        Args:
            short_code: The short code from the request.

        Returns:
            The original URL to redirect to.

        Raises:
            KeyError: If the short code does not exist.
            ValueError: If the short code format is invalid.
        """
        code = self._sanitize_code(short_code)

        with self.lock:
            if code not in self.url_map:
                raise KeyError(f"Short code '{code}' not found")
            self.click_counts[code] += 1
            return self.url_map[code]

    def get_click_count(self, short_code: str) -> int:
        """
        Retrieve the click count for a given short code.

        Args:
            short_code: The short code to query.

        Returns:
            Number of times the short URL has been accessed.

        Raises:
            KeyError: If the short code does not exist.
            ValueError: If the short code format is invalid.
        """
        code = self._sanitize_code(short_code)

        with self.lock:
            if code not in self.click_counts:
                raise KeyError(f"Short code '{code}' not found")
            return self.click_counts[code]

    def remove(self, short_code: str) -> None:
        """
        Remove a short code and its associated data.

        Args:
            short_code: The short code to remove.

        Raises:
            KeyError: If the short code does not exist.
            ValueError: If the short code format is invalid.
        """
        code = self._sanitize_code(short_code)

        with self.lock:
            if code not in self.url_map:
                raise KeyError(f"Short code '{code}' not found")
            del self.url_map[code]
            del self.click_counts[code]

    def list_codes(self) -> Dict[str, Tuple[str, int]]:
        """
        List all short codes with their original URLs and click counts.

        Returns:
            Dictionary mapping short codes to (url, click_count) tuples.
        """
        with self.lock:
            return {
                code: (self.url_map[code], self.click_counts[code])
                for code in self.url_map
            }


# Example usage (can be removed for production)
if __name__ == "__main__":
    shortener = URLShortener(base_url="https://short.example.com", code_length=6)

    # Encode a URL
    short_url = shortener.encode("https://www.example.com/very/long/path")
    print(f"Short URL: {short_url}")

    # Extract code from short URL
    code = short_url.split("/")[-1]

    # Decode
    original = shortener.decode(code)
    print(f"Original: {original}")

    # Simulate redirects
    redirect_url = shortener.get_redirect_url(code)
    print(f"Redirect to: {redirect_url}")
    print(f"Click count: {shortener.get_click_count(code)}")