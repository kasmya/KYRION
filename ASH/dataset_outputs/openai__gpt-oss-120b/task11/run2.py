"""
url_shortener.py

A simple, self‑contained URL shortener service.

Features
--------
* Encode long URLs into short, random alphanumeric codes.
* Decode short codes back to the original URLs.
* HTTP endpoints for shortening, redirection, and click‑statistics.
* Click‑count tracking for each short URL.
* Input validation and explicit error handling.
* Uses only the Python standard library and Flask (a widely‑used PyPI package).

Security considerations
-----------------------
* Random codes are generated with ``secrets`` for cryptographic strength.
* Only ``http`` and ``https`` schemes are accepted.
* All database interactions use parameterised queries to avoid SQL injection.
* Errors are not leaked to the client; generic messages are returned.
"""

from __future__ import annotations

import re
import secrets
import string
import sqlite3
import threading
import urllib.parse
from typing import Final, Optional

from flask import Flask, jsonify, redirect, request, abort

# --------------------------------------------------------------------------- #
# Constants and helpers
# --------------------------------------------------------------------------- #

ALPHABET: Final[str] = string.ascii_letters + string.digits
CODE_LENGTH: Final[int] = 6
URL_REGEX: Final[re.Pattern] = re.compile(
    r"^(?:http|https)://"
    r"(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+"  # domain...
    r"[A-Z]{2,6}\.?|"  # ...including TLD
    r"localhost|"  # localhost
    r"\d{1,3}(?:\.\d{1,3}){3})"  # ...or IPv4
    r"(?::\d+)?(?:/?|[/?]\S+)$",
    re.IGNORECASE,
)


def _generate_code() -> str:
    """
    Generate a cryptographically strong random alphanumeric code.

    Returns
    -------
    str
        A random string of length :data:`CODE_LENGTH`.
    """
    return "".join(secrets.choice(ALPHABET) for _ in range(CODE_LENGTH))


def _is_valid_url(url: str) -> bool:
    """
    Validate that *url* is a well‑formed HTTP/HTTPS URL.

    Parameters
    ----------
    url: str
        The URL to validate.

    Returns
    -------
    bool
        ``True`` if the URL matches the allowed pattern, ``False`` otherwise.
    """
    return bool(URL_REGEX.match(url))


# --------------------------------------------------------------------------- #
# Core URL shortener logic
# --------------------------------------------------------------------------- #

class URLShortener:
    """
    Service class that stores URL mappings and click statistics.

    The data is persisted in a SQLite database (in‑memory by default). All
    operations are thread‑safe.
    """

    _CREATE_TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS urls (
        code TEXT PRIMARY KEY,
        long_url TEXT NOT NULL,
        clicks INTEGER NOT NULL DEFAULT 0
    );
    """

    def __init__(self, db_path: str = ":memory:") -> None:
        """
        Initialise the shortener with a SQLite database.

        Parameters
        ----------
        db_path: str, optional
            Path to the SQLite file. ``":memory:"`` creates a transient DB.
        """
        self._db_path = db_path
        self._lock = threading.RLock()
        self._init_db()

    def _init_db(self) -> None:
        """Create the required table if it does not exist."""
        with self._get_conn() as conn:
            conn.execute(self._CREATE_TABLE_SQL)

    def _get_conn(self) -> sqlite3.Connection:
        """Return a new SQLite connection with row factory set."""
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def shorten(self, long_url: str) -> str:
        """
        Create (or retrieve) a short code for *long_url*.

        Parameters
        ----------
        long_url: str
            The original URL to shorten.

        Returns
        -------
        str
            The short code representing *long_url*.

        Raises
        ------
        ValueError
            If *long_url* is not a valid HTTP/HTTPS URL.
        RuntimeError
            If a unique code cannot be generated after many attempts.
        """
        if not _is_valid_url(long_url):
            raise ValueError("Invalid URL: only http:// and https:// URLs are allowed.")

        with self._lock, self._get_conn() as conn:
            # Return existing code if the URL was already shortened.
            row = conn.execute(
                "SELECT code FROM urls WHERE long_url = ?",
                (long_url,),
            ).fetchone()
            if row:
                return row["code"]

            # Generate a unique code.
            for _ in range(10_000):
                code = _generate_code()
                if not conn.execute(
                    "SELECT 1 FROM urls WHERE code = ?",
                    (code,),
                ).fetchone():
                    conn.execute(
                        "INSERT INTO urls (code, long_url) VALUES (?, ?)",
                        (code, long_url),
                    )
                    conn.commit()
                    return code
            raise RuntimeError("Failed to generate a unique short code.")

    def expand(self, code: str) -> str:
        """
        Resolve *code* to its original long URL.

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
        KeyError
            If *code* does not exist in the database.
        """
        with self._lock, self._get_conn() as conn:
            row = conn.execute(
                "SELECT long_url FROM urls WHERE code = ?",
                (code,),
            ).fetchone()
            if row:
                return row["long_url"]
            raise KeyError(f"Short code '{code}' not found.")

    def increment_click(self, code: str) -> None:
        """
        Increment the click counter for *code*.

        Parameters
        ----------
        code: str
            The short code whose click count should be increased.

        Raises
        ------
        KeyError
            If *code* does not exist.
        """
        with self._lock, self._get_conn() as conn:
            cur = conn.execute(
                "UPDATE urls SET clicks = clicks + 1 WHERE code = ?",
                (code,),
            )
            if cur.rowcount == 0:
                raise KeyError(f"Short code '{code}' not found.")
            conn.commit()

    def get_clicks(self, code: str) -> int:
        """
        Retrieve the total click count for *code*.

        Parameters
        ----------
        code: str
            The short code to query.

        Returns
        -------
        int
            Number of times the short URL has been accessed.

        Raises
        ------
        KeyError
            If *code* does not exist.
        """
        with self._lock, self._get_conn() as conn:
            row = conn.execute(
                "SELECT clicks FROM urls WHERE code = ?",
                (code,),
            ).fetchone()
            if row:
                return row["clicks"]
            raise KeyError(f"Short code '{code}' not found.")


# --------------------------------------------------------------------------- #
# Flask web application
# --------------------------------------------------------------------------- #

def create_app(shortener: URLShortener) -> Flask:
    """
    Build and configure a Flask application for the URL shortener service.

    Parameters
    ----------
    shortener: URLShortener
        An instance of :class:`URLShortener` handling storage and logic.

    Returns
    -------
    Flask
        A ready‑to‑run Flask application.
    """
    app = Flask(__name__)

    @app.errorhandler(400)
    @app.errorhandler(404)
    @app.errorhandler(500)
    def _handle_error(error):
        """Return JSON error responses."""
        response = jsonify({"error": error.description if hasattr(error, "description") else str(error)})
        response.status_code = error.code if hasattr(error, "code") else 500
        return response

    @app.route("/shorten", methods=["POST"])
    def shorten_endpoint():
        """
        JSON endpoint to create a short URL.

        Expects JSON payload: {"url": "<long_url>"}.
        Returns JSON: {"code": "<code>", "short_url": "<full_short_url>"}.
        """
        if not request.is_json:
            abort(400, description="Request body must be JSON.")
        data = request.get_json(silent=True) or {}
        long_url = data.get("url")
        if not isinstance(long_url, str):
            abort(400, description="Missing or invalid 'url' field.")
        try:
            code = shortener.shorten(long_url)
        except ValueError as exc:
            abort(400, description=str(exc))
        except RuntimeError as exc:
            abort(500, description=str(exc))
        short_url = urllib.parse.urljoin(request.host_url, code)
        return jsonify({"code": code, "short_url": short_url})

    @app.route("/<code>", methods=["GET"])
    def redirect_endpoint(code: str):
        """
        Redirect short code to its original URL and record a click.

        Parameters
        ----------
        code: str
            The short code extracted from the path.
        """
        try:
            long_url = shortener.expand(code)
            shortener.increment_click(code)
        except KeyError:
            abort(404, description="Short URL not found.")
        return redirect(long_url, code=302)

    @app.route("/stats/<code>", methods=["GET"])
    def stats_endpoint(code: str):
        """
        Return JSON statistics for a given short code.

        Returns
        -------
        JSON: {"url": "<long_url>", "clicks": <int>}
        """
        try:
            long_url = shortener.expand(code)
            clicks = shortener.get_clicks(code)
        except KeyError:
            abort(404, description="Short URL not found.")
        return jsonify({"url": long_url, "clicks": clicks})

    return app


# --------------------------------------------------------------------------- #
# Module entry‑point for quick testing
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    # Simple run configuration; in production use a WSGI server.
    db_file = "url_shortener.db"
    shortener_instance = URLShortener(db_path=db_file)
    flask_app = create_app(shortener_instance)
    flask_app.run(host="127.0.0.1", port=5000, debug=False)