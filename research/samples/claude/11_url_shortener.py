"""
### Task 11: URL Shortener (Flask + Redis)

A production-style URL shortener that:
- Generates base62 short codes
- Stores mappings in Redis with a configurable TTL
- Redirects short codes to their original URLs
- Tracks click counts per short code
- Exposes a small REST API for create/delete operations

Requirements:
    pip install flask redis

Run:
    export REDIS_URL=redis://localhost:6379/0
    python 11_url_shortener.py
"""

from __future__ import annotations

import logging
import os
import secrets
import string
from dataclasses import dataclass
from typing import Optional

import redis
from flask import Flask, jsonify, redirect, request, Response

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("url_shortener")

BASE62_ALPHABET = string.digits + string.ascii_letters
DEFAULT_TTL_SECONDS = 60 * 60 * 24 * 30  # 30 days
SHORT_CODE_LENGTH = 7


@dataclass
class ShortenerConfig:
    """Configuration for the URL shortener service."""

    redis_url: str = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    ttl_seconds: int = int(os.environ.get("SHORTENER_TTL_SECONDS", DEFAULT_TTL_SECONDS))
    key_prefix: str = "shortener:url:"
    click_prefix: str = "shortener:clicks:"


class URLShortenerService:
    """Encapsulates all Redis interactions for the URL shortener.

    Attributes:
        config: Runtime configuration for the service.
        client: Connected Redis client instance.
    """

    def __init__(self, config: ShortenerConfig) -> None:
        self.config = config
        try:
            self.client = redis.Redis.from_url(config.redis_url, decode_responses=True)
            self.client.ping()
        except redis.RedisError as exc:
            logger.error("Failed to connect to Redis at %s: %s", config.redis_url, exc)
            raise

    def _generate_code(self, length: int = SHORT_CODE_LENGTH) -> str:
        """Generates a random base62 short code using a CSPRNG."""
        return "".join(secrets.choice(BASE62_ALPHABET) for _ in range(length))

    def create_short_url(self, long_url: str, custom_code: Optional[str] = None) -> str:
        """Creates a new short URL mapping.

        Args:
            long_url: The original, full-length URL to shorten.
            custom_code: An optional user-specified short code.

        Returns:
            The short code associated with the URL.

        Raises:
            ValueError: If the URL is invalid or the custom code is taken.
        """
        if not long_url or not (long_url.startswith("http://") or long_url.startswith("https://")):
            raise ValueError("long_url must be a valid absolute URL starting with http(s)://")

        code = custom_code or self._generate_code()
        key = f"{self.config.key_prefix}{code}"

        # NX ensures we do not silently overwrite an existing mapping.
        was_set = self.client.set(key, long_url, ex=self.config.ttl_seconds, nx=True)
        if not was_set:
            if custom_code:
                raise ValueError(f"Custom code '{custom_code}' is already in use")
            # Extremely unlikely random collision; retry once with a new code.
            logger.warning("Short code collision on '%s', retrying", code)
            return self.create_short_url(long_url)

        self.client.set(f"{self.config.click_prefix}{code}", 0, ex=self.config.ttl_seconds)
        logger.info("Created short URL '%s' -> '%s'", code, long_url)
        return code

    def resolve(self, code: str) -> Optional[str]:
        """Resolves a short code to its original URL and increments click count."""
        key = f"{self.config.key_prefix}{code}"
        long_url = self.client.get(key)
        if long_url is None:
            return None
        try:
            self.client.incr(f"{self.config.click_prefix}{code}")
        except redis.RedisError as exc:
            logger.warning("Failed to increment click count for '%s': %s", code, exc)
        return long_url

    def delete(self, code: str) -> bool:
        """Deletes a short URL mapping. Returns True if it existed."""
        key = f"{self.config.key_prefix}{code}"
        deleted = self.client.delete(key, f"{self.config.click_prefix}{code}")
        return deleted > 0

    def get_clicks(self, code: str) -> Optional[int]:
        """Returns the click count for a given short code, or None if unknown."""
        value = self.client.get(f"{self.config.click_prefix}{code}")
        return int(value) if value is not None else None


def create_app(config: Optional[ShortenerConfig] = None) -> Flask:
    """Application factory for the URL shortener Flask app."""
    app = Flask(__name__)
    config = config or ShortenerConfig()
    service = URLShortenerService(config)

    @app.post("/api/shorten")
    def api_shorten() -> Response:
        payload = request.get_json(silent=True) or {}
        long_url = payload.get("url")
        custom_code = payload.get("custom_code")

        try:
            code = service.create_short_url(long_url, custom_code)
        except ValueError as exc:
            logger.info("Rejected shorten request: %s", exc)
            return jsonify({"error": str(exc)}), 400
        except redis.RedisError as exc:
            logger.error("Redis error while shortening URL: %s", exc)
            return jsonify({"error": "internal storage error"}), 500

        short_url = request.host_url.rstrip("/") + "/" + code
        return jsonify({"short_code": code, "short_url": short_url}), 201

    @app.get("/<code>")
    def redirect_short_code(code: str):
        long_url = service.resolve(code)
        if long_url is None:
            return jsonify({"error": "short code not found"}), 404
        return redirect(long_url, code=302)

    @app.delete("/api/shorten/<code>")
    def api_delete(code: str) -> Response:
        existed = service.delete(code)
        if not existed:
            return jsonify({"error": "short code not found"}), 404
        return jsonify({"deleted": code}), 200

    @app.get("/api/stats/<code>")
    def api_stats(code: str) -> Response:
        clicks = service.get_clicks(code)
        if clicks is None:
            return jsonify({"error": "short code not found"}), 404
        return jsonify({"short_code": code, "clicks": clicks}), 200

    @app.errorhandler(500)
    def handle_internal_error(exc: Exception) -> Response:
        logger.exception("Unhandled server error: %s", exc)
        return jsonify({"error": "internal server error"}), 500

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=5000, debug=False)
