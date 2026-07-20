"""
Flask based URL shortener service.

Features:
- Encode long URLs to short codes.
- Decode short codes to original URLs.
- HTTP redirect handling with click count tracking.
- Simple analytics endpoint.
- Input validation and basic security considerations.

Run with:
    python url_shortener.py
"""

import string
import random
import sqlite3
import urllib.parse
from datetime import datetime
from typing import Optional, Tuple

from flask import Flask, request, jsonify, redirect, abort, g

# --------------------------- Configuration ---------------------------

DATABASE = "url_shortener.db"
SHORT_CODE_LENGTH = 6
ALLOWED_SCHEMES = {"http", "https"}

app = Flask(__name__)
app.config["JSONIFY_PRETTYPRINT_REGULAR"] = False
app.config["JSON_SORT_KEYS"] = False


# --------------------------- Database Helpers ---------------------------

def get_db() -> sqlite3.Connection:
    """Get a thread‑local SQLite connection."""
    if "db" not in g:
        conn = sqlite3.connect(DATABASE, detect_types=sqlite3.PARSE_DECLTYPES)
        conn.row_factory = sqlite3.Row
        g.db = conn
    return g.db


@app.teardown_appcontext
def close_db(exception: Optional[BaseException] = None) -> None:
    """Close the SQLite connection on request teardown."""
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db() -> None:
    """Create tables if they do not exist."""
    conn = get_db()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS urls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            long_url TEXT NOT NULL,
            short_code TEXT UNIQUE NOT NULL,
            click_count INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP NOT NULL
        )
        """
    )
    conn.commit()


# --------------------------- Utility Functions ---------------------------

def _is_valid_url(url: str) -> bool:
    """Return True if the URL is syntactically valid and uses an allowed scheme."""
    try:
        result = urllib.parse.urlparse(url)
        return result.scheme.lower() in ALLOWED_SCHEMES and bool(result.netloc)
    except Exception:
        return False


def _generate_short_code(length: int = SHORT_CODE_LENGTH) -> str:
    """Generate a random alphanumeric short code."""
    alphabet = string.ascii_letters + string.digits
    return "".join(random.choices(alphabet, k=length))


def _store_url(long_url: str) -> str:
    """
    Store a new URL and return its short code.
    Handles possible collisions by retrying a limited number of times.
    """
    conn = get_db()
    for _ in range(5):
        code = _generate_short_code()
        try:
            conn.execute(
                """
                INSERT INTO urls (long_url, short_code, created_at)
                VALUES (?, ?, ?)
                """,
                (long_url, code, datetime.utcnow()),
            )
            conn.commit()
            return code
        except sqlite3.IntegrityError:
            # Collision on short_code, generate a new one
            continue
    raise RuntimeError("Failed to generate a unique short code.")


def _fetch_url(short_code: str) -> Optional[sqlite3.Row]:
    """Retrieve a URL row by its short code."""
    conn = get_db()
    cur = conn.execute(
        "SELECT * FROM urls WHERE short_code = ?", (short_code,)
    )
    return cur.fetchone()


def _increment_click_count(short_code: str) -> None:
    """Atomically increase the click count for a given short code."""
    conn = get_db()
    conn.execute(
        "UPDATE urls SET click_count = click_count + 1 WHERE short_code = ?",
        (short_code,),
    )
    conn.commit()


# --------------------------- Flask Routes ---------------------------

@app.route("/shorten", methods=["POST"])
def shorten_url() -> Tuple[Response, int]:
    """
    Create a short URL for a supplied long URL.

    Expected JSON payload: {"url": "<long_url>"}
    Returns JSON: {"short_url": "<service_url>/<code>"}
    """
    data = request.get_json(silent=True) or {}
    long_url = data.get("url", "").strip()

    if not long_url:
        return jsonify(error="Missing 'url' in request body."), 400
    if not _is_valid_url(long_url):
        return jsonify(error="Invalid URL provided."), 400

    try:
        short_code = _store_url(long_url)
    except RuntimeError as exc:
        return jsonify(error=str(exc)), 500

    short_url = request.host_url.rstrip("/") + "/" + short_code
    return jsonify(short_url=short_url), 201


@app.route("/<string:short_code>")
def redirect_short_url(short_code: str):
    """
    Redirect a short code to its original URL.
    The click count is incremented atomically.
    """
    row = _fetch_url(short_code)
    if row is None:
        abort(404, description="Short URL not found.")

    # Increment click count before redirect
    _increment_click_count(short_code)

    # Use Flask's safe redirect (it just returns a response, no extra check needed)
    return redirect(row["long_url"], code=302)


@app.route("/analytics/<string:short_code>", methods=["GET"])
def analytics(short_code: str):
    """
    Return analytics for a given short code.

    Response JSON: {"short_code": "...", "click_count": <int>, "created_at": "..."}
    """
    row = _fetch_url(short_code)
    if row is None:
        abort(404, description="Short URL not found.")

    return jsonify(
        short_code=short_code,
        click_count=row["click_count"],
        created_at=row["created_at"].isoformat() + "Z",
    ), 200


# --------------------------- Error Handlers ---------------------------

@app.errorhandler(400)
def handle_bad_request(e):
    return jsonify(error=str(e)), 400


@app.errorhandler(404)
def handle_not_found(e):
    return jsonify(error=str(e)), 404


@app.errorhandler(500)
def handle_internal_error(e):
    return jsonify(error="Internal server error."), 500


# --------------------------- Application Entry Point ---------------------------

if __name__ == "__main__":
    # Initialize DB before first request
    with app.app_context():
        init_db()
    # Run with built‑in server (use a production WSGI server for real deployments)
    app.run(host="0.0.0.0", port=5000, debug=False)