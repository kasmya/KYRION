"""
url_shortener.py
-----------------

A minimal URL shortening service built with Flask and SQLite.

Features
--------
* Encode a long URL into a short, opaque code.
* Decode a short code back to its original URL.
* HTTP redirect endpoint (`/<code>`) that tracks click counts.
* Statistics endpoint (`/stats/<code>`) returning click count and original URL.
* Simple error handling with JSON responses.
* Secure random code generation and basic URL validation.

Dependencies
------------
* Flask (pip install Flask)

The module can be run directly to start a development server:

    python -m url_shortener

Security considerations
------------------------
* Uses `secrets` for cryptographically‑secure random code generation.
* Validates that supplied URLs have an HTTP/HTTPS scheme.
* Stores data in a local SQLite file with parameterised queries to avoid SQL injection.
"""

from __future__ import annotations

import re
import sqlite3
import string
import secrets
from typing import Final, Optional, Tuple

from flask import Flask, jsonify, redirect, request, abort, Response

# --------------------------------------------------------------------------- #
# Configuration constants
# --------------------------------------------------------------------------- #

DB_PATH: Final[str] = "url_shortener.db"
CODE_LENGTH: Final[int] = 6
CODE_ALPHABET: Final[str] = string.ascii_letters + string.digits
URL_REGEX: Final[re.Pattern] = re.compile(
    r"^(?:http|https)://"
    r"(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+"  # domain...
    r"[A-Z]{2,6}\.?|"
    r"localhost|"
    r"\d{1,3}(?:\.\d{1,3}){3})"  # ...or IPv4
    r"(?::\d+)?"
    r"(?:/?|[/?]\S+)$",
    re.IGNORECASE,
)

# --------------------------------------------------------------------------- #
# Flask application
# --------------------------------------------------------------------------- #

app = Flask(__name__)

# --------------------------------------------------------------------------- #
# Custom exceptions
# --------------------------------------------------------------------------- #


class URLShortenerError(Exception):
    """Base class for all URL shortener related errors."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class URLValidationError(URLShortenerError):
    """Raised when a supplied URL fails validation."""


class CodeNotFoundError(URLShortenerError):
    """Raised when a short code does not exist in the database."""


# --------------------------------------------------------------------------- #
# Database helpers
# --------------------------------------------------------------------------- #


def _get_connection() -> sqlite3.Connection:
    """Return a new SQLite connection with row factory set to dict.

    Returns
    -------
    sqlite3.Connection
        A connection object to the SQLite database.
    """
    conn = sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Initialise the SQLite database schema if it does not already exist."""
    sql = """
    CREATE TABLE IF NOT EXISTS urls (
        code TEXT PRIMARY KEY,
        long_url TEXT NOT NULL,
        click_count INTEGER NOT NULL DEFAULT 0
    );
    """
    with _get_connection() as conn:
        conn.executescript(sql)


# --------------------------------------------------------------------------- #
# Core functionality
# --------------------------------------------------------------------------- #


def _is_valid_url(url: str) -> bool:
    """Return ``True`` if *url* appears to be a well‑formed HTTP/HTTPS URL.

    Parameters
    ----------
    url: str
        The URL to validate.

    Returns
    -------
    bool
        ``True`` if the URL matches a permissive regex, ``False`` otherwise.
    """
    return bool(URL_REGEX.match(url))


def _generate_unique_code(conn: sqlite3.Connection) -> str:
    """Generate a random, unique short code.

    This function retries until a non‑existing code is produced.

    Parameters
    ----------
    conn: sqlite3.Connection
        An open SQLite connection used to check for collisions.

    Returns
    -------
    str
        A unique short code of length :data:`CODE_LENGTH`.
    """
    while True:
        code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))
        cur = conn.execute("SELECT 1 FROM urls WHERE code = ?", (code,))
        if not cur.fetchone():
            return code


def encode_url(long_url: str) -> str:
    """Encode *long_url* into a short code and store the mapping.

    Parameters
    ----------
    long_url: str
        The original URL to shorten.

    Returns
    -------
    str
        The generated short code.

    Raises
    ------
    URLValidationError
        If *long_url* is not a valid HTTP/HTTPS URL.
    URLShortenerError
        For unexpected database errors.
    """
    if not _is_valid_url(long_url):
        raise URLValidationError("Provided URL is not a valid HTTP/HTTPS URL.", 400)

    try:
        with _get_connection() as conn:
            code = _generate_unique_code(conn)
            conn.execute(
                "INSERT INTO urls (code, long_url) VALUES (?, ?)", (code, long_url)
            )
            conn.commit()
            return code
    except sqlite3.DatabaseError as exc:
        raise URLShortenerError(f"Database error: {exc}", 500) from exc


def decode_url(code: str) -> str:
    """Return the original URL associated with *code*.

    Parameters
    ----------
    code: str
        The short code to look up.

    Returns
    -------
    str
        The original long URL.

    Raises
    ------
    CodeNotFoundError
        If *code* does not exist.
    URLShortenerError
        For unexpected database errors.
    """
    try:
        with _get_connection() as conn:
            cur = conn.execute(
                "SELECT long_url FROM urls WHERE code = ?", (code,)
            )
            row = cur.fetchone()
            if row is None:
                raise CodeNotFoundError(f"Code '{code}' not found.", 404)
            return row["long_url"]
    except sqlite3.DatabaseError as exc:
        raise URLShortenerError(f"Database error: {exc}", 500) from exc


def increment_click(code: str) -> None:
    """Atomically increment the click counter for *code*.

    Parameters
    ----------
    code: str
        Short code whose click count should be increased.

    Raises
    ------
    CodeNotFoundError
        If *code* does not exist.
    URLShortenerError
        For unexpected database errors.
    """
    try:
        with _get_connection() as conn:
            cur = conn.execute(
                "UPDATE urls SET click_count = click_count + 1 WHERE code = ?",
                (code,),
            )
            if cur.rowcount == 0:
                raise CodeNotFoundError(f"Code '{code}' not found.", 404)
            conn.commit()
    except sqlite3.DatabaseError as exc:
        raise URLShortenerError(f"Database error: {exc}", 500) from exc


def get_click_count(code: str) -> Tuple[int, str]:
    """Retrieve click count and original URL for *code*.

    Parameters
    ----------
    code: str
        The short code to query.

    Returns
    -------
    Tuple[int, str]
        A tuple ``(click_count, long_url)``.

    Raises
    ------
    CodeNotFoundError
        If *code* does not exist.
    URLShortenerError
        For unexpected database errors.
    """
    try:
        with _get_connection() as conn:
            cur = conn.execute(
                "SELECT click_count, long_url FROM urls WHERE code = ?", (code,)
            )
            row = cur.fetchone()
            if row is None:
                raise CodeNotFoundError(f"Code '{code}' not found.", 404)
            return row["click_count"], row["long_url"]
    except sqlite3.DatabaseError as exc:
        raise URLShortenerError(f"Database error: {exc}", 500) from exc


# --------------------------------------------------------------------------- #
# Flask route implementations
# --------------------------------------------------------------------------- #


@app.errorhandler(URLShortenerError)
def handle_url_shortener_error(error: URLShortenerError) -> Response:
    """Convert custom exceptions into JSON error responses."""
    response = jsonify({"error": error.message})
    response.status_code = error.status_code
    return response


@app.errorhandler(404)
def handle_404(_: Exception) -> Response:
    """Return a JSON 404 for unknown routes."""
    response = jsonify({"error": "Resource not found"})
    response.status_code = 404
    return response


@app.route("/encode", methods=["POST"])
def encode_endpoint() -> Response:
    """Encode endpoint: expects JSON ``{'url': '<long_url>'}``.

    Returns
    -------
    Response
        JSON ``{'code': '<short_code>'}`` on success.
    """
    if not request.is_json:
        raise URLShortenerError("Request body must be JSON.", 415)

    data = request.get_json()
    if not isinstance(data, dict) or "url" not in data:
        raise URLShortenerError("JSON must contain a 'url' field.", 400)

    long_url = data["url"]
    if not isinstance(long_url, str):
        raise URLShortenerError("'url' field must be a string.", 400)

    code = encode_url(long_url)
    return jsonify({"code": code}), 201


@app.route("/<code>", methods=["GET"])
def redirect_endpoint(code: str) -> Response:
    """Redirect endpoint that forwards the client to the original URL.

    Also increments the click counter.

    Parameters
    ----------
    code: str
        The short code extracted from the URL path.

    Returns
    -------
    Response
        A Flask redirect response.
    """
    long_url = decode_url(code)
    increment_click(code)
    return redirect(long_url, code=302)


@app.route("/stats/<code>", methods=["GET"])
def stats_endpoint(code: str) -> Response:
    """Statistics endpoint returning click count and original URL.

    Parameters
    ----------
    code: str
        The short code to query.

    Returns
    -------
    Response
        JSON ``{'url': '<long_url>', 'clicks': <int>}``.
    """
    clicks, long_url = get_click_count(code)
    return jsonify({"url": long_url, "clicks": clicks})


# --------------------------------------------------------------------------- #
# Module entry point
# --------------------------------------------------------------------------- #


def _run_dev_server(host: str = "127.0.0.1", port: int = 5000) -> None:
    """Start Flask's built‑in development server.

    Parameters
    ----------
    host: str, optional
        Host address to bind to (default ``127.0.0.1``).
    port: int, optional
        Port number (default ``5000``).
    """
    init_db()
    app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    _run_dev_server()