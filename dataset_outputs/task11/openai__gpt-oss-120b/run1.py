"""
A simple URL shortener service built with Flask and SQLite.

Features:
- Encode long URLs to short codes.
- Decode short codes to original URLs via HTTP redirects.
- Track click count (analytics) for each short URL.
- Input validation, error handling, and basic security measures.

Usage:
    export FLASK_APP=app.py
    flask run
"""

import re
import string
import sqlite3
import threading
from datetime import datetime
from typing import Optional

from flask import Flask, jsonify, request, abort, redirect, g, url_for

# ---------------------------------------------------------------------------#
# Configuration
# ---------------------------------------------------------------------------#
BASE_URL = "http://localhost:5000"  # Change to your public domain when deploying

# ---------------------------------------------------------------------------#
# Flask app and DB utilities
# ---------------------------------------------------------------------------#
app = Flask(__name__)

def get_db() -> sqlite3.Connection:
    """Get a thread‑local SQLite connection."""
    if "db" not in g:
        conn = sqlite3.connect("url_shortener.db", detect_types=sqlite3.PARSE_DECLTYPES)
        conn.row_factory = sqlite3.Row
        g.db = conn
    return g.db

@app.teardown_appcontext
def close_db(exc: Optional[BaseException]) -> None:
    """Close the SQLite connection on request teardown."""
    db = g.pop("db", None)
    if db is not None:
        db.close()

_db_lock = threading.Lock()

def init_db() -> None:
    """Create tables if they don't exist."""
    with _db_lock, app.app_context():
        db = get_db()
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS urls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                long_url TEXT NOT NULL,
                click_count INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        db.commit()

# ---------------------------------------------------------------------------#
# Helper functions
# ---------------------------------------------------------------------------#
BASE62_ALPHABET = string.digits + string.ascii_uppercase + string.ascii_lowercase

def base62_encode(num: int) -> str:
    """Encode a positive integer to a Base62 string."""
    if num == 0:
        return BASE62_ALPHABET[0]
    chars = []
    base = len(BASE62_ALPHABET)
    while num:
        num, rem = divmod(num, base)
        chars.append(BASE62_ALPHABET[rem])
    return "".join(reversed(chars))

def is_valid_url(url: str) -> bool:
    """Very basic URL validation to guard against malformed input."""
    # Regex from Django URLValidator (simplified)
    regex = re.compile(
        r"^(?:http|https)://"                     # scheme
        r"(?:\S+(?::\S*)?@)?"                     # user:pass authentication
        r"(?:[A-Za-z0-9.-]+|\[[A-F0-9:]+\])"      # hostname or IPv6
        r"(?::\d{2,5})?"                          # optional port
        r"(?:[/?#][^\s]*)?$", re.IGNORECASE)
    return bool(regex.match(url))

def get_url_by_code(code: str) -> Optional[sqlite3.Row]:
    """Retrieve the database row for a given short code."""
    try:
        url_id = decode_base62(code)
    except ValueError:
        return None
    db = get_db()
    cur = db.execute("SELECT * FROM urls WHERE id = ?", (url_id,))
    return cur.fetchone()

def decode_base62(text: str) -> int:
    """Decode a Base62 string back to an integer."""
    base = len(BASE62_ALPHABET)
    num = 0
    for char in text:
        try:
            value = BASE62_ALPHABET.index(char)
        except ValueError as exc:
            raise ValueError(f"Invalid character '{char}' in base62 string") from exc
        num = num * base + value
    return num

# ---------------------------------------------------------------------------#
# Routes
# ---------------------------------------------------------------------------#
@app.route("/shorten", methods=["POST"])
def shorten_url() -> tuple[dict, int]:
    """
    Accept a JSON payload `{"url": "<long_url>"}` and return a short URL.

    Returns:
        201 Created with JSON {"short_url": "<full_short_url>"} on success.
        400 Bad Request if URL is missing or invalid.
    """
    data = request.get_json(silent=True)
    if not data or "url" not in data:
        abort(400, description="JSON body must contain 'url' field.")
    long_url: str = data["url"].strip()
    if not is_valid_url(long_url):
        abort(400, description="Provided URL is not valid or uses an unsupported scheme.")

    with _db_lock:
        db = get_db()
        cur = db.execute("INSERT INTO urls (long_url) VALUES (?)", (long_url,))
        url_id = cur.lastrowid
        db.commit()

    short_code = base62_encode(url_id)
    short_url = f"{BASE_URL}/{short_code}"
    return jsonify({"short_url": short_url}), 201

@app.route("/<code>", methods=["GET"])
def redirect_short_url(code: str):
    """
    Redirect to the original long URL and increment the click counter.

    Returns:
        302 Found redirect to the long URL.
        404 Not Found if the code does not exist.
    """
    row = get_url_by_code(code)
    if row is None:
        abort(404, description="Short URL not found.")

    with _db_lock:
        db = get_db()
        db.execute(
            "UPDATE urls SET click_count = click_count + 1 WHERE id = ?",
            (row["id"],)
        )
        db.commit()

    return redirect(row["long_url"], code=302)

@app.route("/analytics/<code>", methods=["GET"])
def analytics(code: str):
    """
    Return click count statistics for a given short code.

    Returns:
        200 OK with JSON {"click_count": <int>, "created_at": "<ISO8601>"}
        404 Not Found if the code does not exist.
    """
    row = get_url_by_code(code)
    if row is None:
        abort(404, description="Short URL not found.")

    return jsonify(
        {
            "click_count": row["click_count"],
            "created_at": datetime.fromisoformat(row["created_at"]).isoformat(),
        }
    )

@app.errorhandler(400)
def bad_request(error):
    return jsonify({"error": "Bad Request", "message": error.description}), 400

@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Not Found", "message": error.description}), 404

@app.errorhandler(500)
def server_error(error):
    return jsonify({"error": "Internal Server Error"}), 500

# ---------------------------------------------------------------------------#
# Application entry point
# ---------------------------------------------------------------------------#
if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=False)