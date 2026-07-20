#!/usr/bin/env python3
"""
A simple URL shortener service built with Flask and SQLAlchemy.

Features:
- Encode long URLs to short codes.
- Decode short codes to original URLs.
- HTTP redirect handling.
- Click‑through analytics (click count).
- Input validation, error handling, and basic security checks.
"""

from __future__ import annotations

import re
import string
import urllib.parse
from datetime import datetime
from typing import Optional

from flask import Flask, jsonify, redirect, request, abort, url_for
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import IntegrityError

# -------------------- Configuration --------------------
BASE62_ALPHABET = string.digits + string.ascii_uppercase + string.ascii_lowercase
SHORT_CODE_LENGTH = 6  # fallback length for random codes

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///shortener.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SECRET_KEY"] = "replace-this-with-a-secure-random-value"

db = SQLAlchemy(app)


# -------------------- Models --------------------
class URLMap(db.Model):
    """Database model that maps a short code to a long URL and tracks clicks."""

    __tablename__ = "url_map"

    id = db.Column(db.Integer, primary_key=True)
    long_url = db.Column(db.String(2048), nullable=False, unique=True)
    short_code = db.Column(db.String(10), nullable=False, unique=True, index=True)
    click_count = db.Column(db.Integer, default=0, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self) -> str:
        return f"<URLMap {self.short_code} → {self.long_url}>"


# -------------------- Utilities --------------------
def is_valid_url(url: str) -> bool:
    """
    Validate a URL to ensure it is absolute, uses http/https,
    and does not point to a private network address.
    """
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return False
    if not parsed.netloc:
        return False

    # Prevent URLs that resolve to private IP ranges.
    # This is a simple regex check; for production consider more robust validation.
    private_net_regex = re.compile(
        r"(^127\.)|(^10\.)|(^172\.(1[6-9]|2[0-9]|3[0-1])\.)|(^192\.168\.)"
    )
    host = parsed.hostname or ""
    if private_net_regex.match(host):
        return False
    return True


def base62_encode(num: int) -> str:
    """Encode an integer to a base62 string."""
    if num == 0:
        return BASE62_ALPHABET[0]
    digits = []
    base = len(BASE62_ALPHABET)
    while num:
        num, rem = divmod(num, base)
        digits.append(BASE62_ALPHABET[rem])
    return "".join(reversed(digits))


def generate_short_code(map_id: int) -> str:
    """
    Generate a deterministic short code from the database primary key.
    Pad to a minimum length if needed.
    """
    code = base62_encode(map_id)
    if len(code) < SHORT_CODE_LENGTH:
        code = code.rjust(SHORT_CODE_LENGTH, BASE62_ALPHABET[0])
    return code


# -------------------- Routes --------------------
@app.route("/shorten", methods=["POST"])
def shorten_url() -> tuple[dict, int]:
    """
    Create a short URL for a given long URL.
    Expected JSON payload: {"url": "https://example.com"}
    Returns JSON with the short URL.
    """
    data = request.get_json(silent=True)
    if not data or "url" not in data:
        return jsonify(error="Missing 'url' in request body."), 400

    long_url = data["url"].strip()
    if not is_valid_url(long_url):
        return jsonify(error="Invalid URL provided."), 400

    # Check if URL already exists
    existing = URLMap.query.filter_by(long_url=long_url).first()
    if existing:
        short_url = url_for("redirect_short", short_code=existing.short_code, _external=True)
        return jsonify(short_url=short_url), 200

    # Create a new mapping; short_code is generated after commit (to get ID)
    new_map = URLMap(long_url=long_url, short_code="")  # placeholder
    db.session.add(new_map)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify(error="Database error while storing the URL."), 500

    # Generate deterministic short code from ID
    new_map.short_code = generate_short_code(new_map.id)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify(error="Collision occurred while generating short code."), 500

    short_url = url_for("redirect_short", short_code=new_map.short_code, _external=True)
    return jsonify(short_url=short_url), 201


@app.route("/<string:short_code>", methods=["GET"])
def redirect_short(short_code: str):
    """
    Redirect a short code to its original long URL.
    Increments the click counter atomically.
    """
    mapping: Optional[URLMap] = URLMap.query.filter_by(short_code=short_code).first()
    if not mapping:
        abort(404, description="Short URL not found.")

    # Increment click count in a safe way
    mapping.click_count += 1
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        # Non‑critical failure; continue with redirect

    return redirect(mapping.long_url, code=302)


@app.route("/analytics/<string:short_code>", methods=["GET"])
def analytics(short_code: str):
    """
    Retrieve click analytics for a given short code.
    Returns JSON with click count and creation timestamp.
    """
    mapping: Optional[URLMap] = URLMap.query.filter_by(short_code=short_code).first()
    if not mapping:
        abort(404, description="Short URL not found.")

    return jsonify(
        short_code=mapping.short_code,
        long_url=mapping.long_url,
        click_count=mapping.click_count,
        created_at=mapping.created_at.isoformat(),
    ), 200


# -------------------- Error Handlers --------------------
@app.errorhandler(400)
def bad_request(error):
    return jsonify(error=str(error)), 400


@app.errorhandler(404)
def not_found(error):
    return jsonify(error=str(error)), 404


@app.errorhandler(500)
def internal_error(error):
    return jsonify(error="Internal server error."), 500


# -------------------- CLI Utilities --------------------
@app.cli.command("init-db")
def init_db() -> None:
    """
    Flask CLI command to initialize the SQLite database.
    Usage: flask init-db
    """
    db.create_all()
    print("Database initialized.")


# -------------------- Main --------------------
if __name__ == "__main__":
    # Ensure DB tables exist before first request
    with app.app_context():
        db.create_all()
    # In production, use a proper WSGI server (e.g., gunicorn) and disable debug mode.
    app.run(host="0.0.0.0", port=5000, debug=False)