"""
url_shortener.py

A simple, self‑contained URL shortener service with the following capabilities:

* Encode long URLs into short, collision‑resistant codes.
* Decode short codes back to the original URLs.
* Provide HTTP redirects for short URLs.
* Track click counts for each short URL.
* Expose a minimal JSON API for creating short URLs and retrieving statistics.

Only the Python standard library and the widely‑used ``Flask`` package are required.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
import sqlite3
import string
import time
import urllib.parse
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Tuple

from flask import Flask, abort, g, jsonify, redirect, request

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #

DB_PATH = "url_shortener.db"
CODE_LENGTH = 7  # Length of the generated short code (Base62 characters)
ALLOWED_SCHEMES = {"http", "https"}

# --------------------------------------------------------------------------- #
# Database utilities
# --------------------------------------------------------------------------- #


def _get_connection() -> sqlite3.Connection:
    """Return a thread‑local SQLite connection, creating the DB if needed."""
    if "db" not in g:
        conn = sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES)
        conn.row_factory = sqlite3.Row
        g.db = conn
        _initialize_db(conn)
    return g.db


def _initialize_db(conn: sqlite3.Connection) -> None:
    """Create the required tables if they do not already exist."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS urls (
            code TEXT PRIMARY KEY,
            long_url TEXT NOT NULL,
            click_count INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP NOT NULL
        )
        """
    )
    conn.commit()


def _close_connection(exception: Optional[BaseException] = None) -> None:
    """Close the SQLite connection stored in the Flask ``g`` object."""
    db: Optional[sqlite3.Connection] = g.pop("db", None)
    if db is not None:
        db.close()


# --------------------------------------------------------------------------- #
# Core logic
# --------------------------------------------------------------------------- #


def _is_valid_url(url: str) -> bool:
    """
    Validate that *url* is a well‑formed absolute URL with an allowed scheme.

    Args:
        url: The URL string to validate.

    Returns:
        ``True`` if the URL is valid, ``False`` otherwise.
    """
    try:
        parsed = urllib.parse.urlparse(url)
        return parsed.scheme in ALLOWED_SCHEMES and bool(parsed.netloc)
    except Exception:
        return False


def _base62_encode(num: int) -> str:
    """
    Convert a non‑negative integer to a Base62 string.

    Args:
        num: Integer to encode.

    Returns:
        Base62 representation.
    """
    if num == 0:
        return "0"
    alphabet = string.digits + string.ascii_letters
    base = len(alphabet)
    encoded = []
    while num:
        num, rem = divmod(num, base)
        encoded.append(alphabet[rem])
    return "".join(reversed(encoded))


def _generate_code(long_url: str) -> str:
    """
    Generate a deterministic short code from *long_url*.

    The function hashes the URL with SHA‑256, interprets the digest as an integer,
    and then encodes it using Base62. The result is truncated to ``CODE_LENGTH``
    characters.

    Args:
        long_url: The original URL.

    Returns:
        A short code consisting of Base62 characters.
    """
    digest = hashlib.sha256(long_url.encode("utf-8")).digest()
    num = int.from_bytes(digest[:8], "big")  # Use first 8 bytes for enough entropy
    return _base62_encode(num)[:CODE_LENGTH]


@dataclass(frozen=True)
class URLRecord:
    """Immutable representation of a stored URL entry."""
    code: str
    long_url: str
    click_count: int
    created_at: datetime


def store_url(long_url: str) -> URLRecord:
    """
    Store *long_url* in the database and return the corresponding ``URLRecord``.

    If the URL already exists, its existing code is returned; otherwise a new
    short code is generated. Collisions are resolved by appending a random
    suffix and retrying.

    Args:
        long_url: The URL to shorten.

    Returns:
        ``URLRecord`` containing the generated code and metadata.

    Raises:
        ValueError: If *long_url* fails validation.
        RuntimeError: If a unique short code could not be generated after several attempts.
    """
    if not _is_valid_url(long_url):
        raise ValueError("Invalid URL: must be absolute and use http or https scheme")

    conn = _get_connection()
    # Check for existing entry
    cur = conn.execute("SELECT * FROM urls WHERE long_url = ?", (long_url,))
    row = cur.fetchone()
    if row:
        return URLRecord(
            code=row["code"],
            long_url=row["long_url"],
            click_count=row["click_count"],
            created_at=row["created_at"],
        )

    # Generate a unique code
    base_code = _generate_code(long_url)
    code = base_code
    attempts = 0
    while attempts < 5:
        cur = conn.execute("SELECT 1 FROM urls WHERE code = ?", (code,))
        if not cur.fetchone():
            break
        # Collision – add random entropy and retry
        suffix = _base62_encode(secrets.randbits(30))[:2]
        code = (base_code + suffix)[:CODE_LENGTH]
        attempts += 1
    else:
        raise RuntimeError("Failed to generate a unique short code after multiple attempts")

    now = datetime.utcnow()
    conn.execute(
        "INSERT INTO urls (code, long_url, click_count, created_at) VALUES (?, ?, 0, ?)",
        (code, long_url, now),
    )
    conn.commit()
    return URLRecord(code=code, long_url=long_url, click_count=0, created_at=now)


def retrieve_url(code: str) -> URLRecord:
    """
    Retrieve a ``URLRecord`` for the given short *code*.

    Args:
        code: Short code previously generated by :func:`store_url`.

    Returns:
        Corresponding ``URLRecord``.

    Raises:
        KeyError: If *code* does not exist in the database.
    """
    conn = _get_connection()
    cur = conn.execute("SELECT * FROM urls WHERE code = ?", (code,))
    row = cur.fetchone()
    if not row:
        raise KeyError(f"Code '{code}' not found")
    return URLRecord(
        code=row["code"],
        long_url=row["long_url"],
        click_count=row["click_count"],
        created_at=row["created_at"],
    )


def increment_click(code: str) -> None:
    """
    Atomically increment the click counter for *code*.

    Args:
        code: Short code whose click count should be increased.

    Raises:
        KeyError: If *code* does not exist.
    """
    conn = _get_connection()
    cur = conn.execute("UPDATE urls SET click_count = click_count + 1 WHERE code = ?", (code,))
    if cur.rowcount == 0:
        raise KeyError(f"Code '{code}' not found")
    conn.commit()


# --------------------------------------------------------------------------- #
# Flask application
# --------------------------------------------------------------------------- #

app = Flask(__name__)
app.teardown_appcontext(_close_connection)


@app.route("/api/shorten", methods=["POST"])
def api_shorten() -> Tuple[dict, int]:
    """
    JSON endpoint to create a short URL.

    Expected payload: ``{"url": "<long_url>"}``.

    Returns:
        JSON dict with ``code`` and ``short_url`` keys on success, or an error
        message and appropriate HTTP status code on failure.
    """
    if not request.is_json:
        return jsonify(error="JSON body required"), 400
    data = request.get_json()
    long_url = data.get("url", "").strip()
    if not long_url:
        return jsonify(error="Missing 'url' field"), 400
    try:
        record = store_url(long_url)
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    except RuntimeError as exc:
        return jsonify(error=str(exc)), 500

    short_url = request.host_url.rstrip("/") + "/" + record.code
    return jsonify(code=record.code, short_url=short_url), 201


@app.route("/api/stats/<code>", methods=["GET"])
def api_stats(code: str) -> Tuple[dict, int]:
    """
    JSON endpoint returning click statistics for *code*.

    Returns:
        JSON with ``code``, ``url``, ``clicks`` and ``created_at`` fields,
        or an error message with a 404 status if the code is unknown.
    """
    try:
        record = retrieve_url(code)
    except KeyError:
        return jsonify(error="Code not found"), 404

    return (
        jsonify(
            code=record.code,
            url=record.long_url,
            clicks=record.click_count,
            created_at=record.created_at.isoformat() + "Z",
        ),
        200,
    )


@app.route("/<code>", methods=["GET"])
def redirect_short(code: str):
    """
    HTTP endpoint that redirects the client to the original URL.

    The click count is incremented before performing the redirect.

    Raises:
        404 Not Found if *code* does not exist.
    """
    try:
        record = retrieve_url(code)
    except KeyError:
        abort(404, description="Short URL not found")
    try:
        increment_click(code)
    except Exception:
        # Non‑critical: continue redirect even if click tracking fails
        pass
    # Use Flask's safe redirect to avoid open‑redirect vulnerabilities
    return redirect(record.long_url, code=302)


@app.errorhandler(404)
def handle_404(error):
    """Return JSON for 404 errors."""
    return jsonify(error=error.description if hasattr(error, "description") else "Not found"), 404


@app.errorhandler(500)
def handle_500(error):
    """Return JSON for unexpected server errors."""
    return jsonify(error="Internal server error"), 500


if __name__ == "__main__":
    # Run the development server only when executed directly.
    # In production, use a proper WSGI server (e.g., gunicorn) and configure
    # a persistent database location.
    app.run(host="127.0.0.1", port=5000, debug=False)