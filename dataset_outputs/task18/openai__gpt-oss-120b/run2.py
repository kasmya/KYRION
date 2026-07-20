"""
Snippet Manager - Flask Application

Features:
- Save code snippets with title, description, language, tags, and source code.
- Search snippets by keyword (in title/description/tags) and/or programming language.
- Retrieve a single snippet with syntax‑highlighted source code.
- Edit and delete snippets.
- Input validation, error handling and basic security best practices.

Dependencies (install via pip):
    Flask>=2.2
    Flask_SQLAlchemy>=3.0
    Pygments>=2.15
"""

from __future__ import annotations

import html
import os
import re
from typing import List, Optional

from flask import (
    Flask,
    jsonify,
    request,
    abort,
    make_response,
)
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import validates
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_by_name, guess_lexer
from pygments.util import ClassNotFound

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, "snippets.db")

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{DB_PATH}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["JSON_SORT_KEYS"] = False

db = SQLAlchemy(app)

# --------------------------------------------------------------------------- #
# Model
# --------------------------------------------------------------------------- #


class Snippet(db.Model):
    """Database model for a code snippet."""

    __tablename__ = "snippets"

    id: int = db.Column(db.Integer, primary_key=True)
    title: str = db.Column(db.String(150), nullable=False)
    description: str = db.Column(db.Text, nullable=True)
    language: str = db.Column(db.String(50), nullable=False)
    code: str = db.Column(db.Text, nullable=False)
    tags: str = db.Column(db.String(250), nullable=True)  # comma‑separated list

    @validates("title", "language", "code")
    def _validate_non_empty(self, key: str, value: str) -> str:
        """Ensure required string fields are not empty or just whitespace."""
        if not value or not value.strip():
            raise ValueError(f"The field '{key}' cannot be empty.")
        return value.strip()

    @validates("tags")
    def _validate_tags(self, key: str, value: Optional[str]) -> Optional[str]:
        """Normalize tags: strip whitespace, collapse commas."""
        if value:
            # Remove duplicate tags & extra spaces
            tags = {t.strip() for t in value.split(",") if t.strip()}
            return ",".join(sorted(tags))
        return None

    def as_dict(self) -> dict:
        """Return a serializable dict representation (without raw code)."""
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "language": self.language,
            "tags": self.tags.split(",") if self.tags else [],
        }

    def highlighted_code(self) -> str:
        """Return HTML with syntax‑highlighted source code."""
        try:
            lexer = get_lexer_by_name(self.language.lower())
        except ClassNotFound:
            # Fallback to guessing the lexer from source
            try:
                lexer = guess_lexer(self.code)
            except ClassNotFound:
                lexer = get_lexer_by_name("text")
        formatter = HtmlFormatter(linenos=True, cssclass="codehilite")
        highlighted = highlight(self.code, lexer, formatter)
        # Include CSS styles in the response for ease of use
        style = f"<style>{formatter.get_style_defs('.codehilite')}</style>"
        return style + highlighted


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def parse_tags(tag_str: Optional[str]) -> List[str]:
    """Convert a comma‑separated tag string to a list."""
    if not tag_str:
        return []
    return [t.strip() for t in tag_str.split(",") if t.strip()]


def validate_snippet_payload(payload: dict, require_code: bool = True) -> dict:
    """
    Validate and sanitize incoming JSON payload for creating/updating a snippet.

    Raises:
        abort(400): If required fields are missing or malformed.
    """
    required_fields = {"title", "language"}
    if require_code:
        required_fields.add("code")

    missing = required_fields - payload.keys()
    if missing:
        abort(make_response(jsonify(error=f"Missing fields: {', '.join(missing)}"), 400))

    title = payload.get("title", "")
    language = payload.get("language", "")
    code = payload.get("code", "")
    description = payload.get("description", "")
    tags = payload.get("tags", "")

    # Simple sanitisation – escape HTML to prevent injection when rendered.
    title = html.escape(str(title)).strip()
    language = html.escape(str(language)).strip()
    description = html.escape(str(description)).strip()
    code = str(code)  # code is shown as pre‑formatted; escaping is done by Pygments.
    tags = html.escape(str(tags)).strip()

    if not title:
        abort(make_response(jsonify(error="Title cannot be empty."), 400))
    if not language:
        abort(make_response(jsonify(error="Language cannot be empty."), 400))
    if require_code and not code:
        abort(make_response(jsonify(error="Code cannot be empty."), 400))

    return {
        "title": title,
        "description": description or None,
        "language": language,
        "code": code,
        "tags": tags or None,
    }


def apply_search_filters(query, keyword: Optional[str], language: Optional[str]):
    """Apply search filters to a SQLAlchemy query."""
    if keyword:
        like_pattern = f"%{keyword.strip().lower()}%"
        query = query.filter(
            db.or_(
                db.func.lower(Snippet.title).like(like_pattern),
                db.func.lower(Snippet.description).like(like_pattern),
                db.func.lower(Snippet.tags).like(like_pattern),
            )
        )
    if language:
        query = query.filter(db.func.lower(Snippet.language) == language.strip().lower())
    return query


# --------------------------------------------------------------------------- #
# API Endpoints
# --------------------------------------------------------------------------- #


@app.route("/snippets", methods=["POST"])
def create_snippet() -> tuple:
    """Create a new snippet."""
    if not request.is_json:
        abort(make_response(jsonify(error="Request payload must be JSON."), 415))

    payload = request.get_json()
    data = validate_snippet_payload(payload)

    snippet = Snippet(**data)
    try:
        db.session.add(snippet)
        db.session.commit()
    except (SQLAlchemyError, ValueError) as exc:
        db.session.rollback()
        abort(make_response(jsonify(error=str(exc)), 400))

    return jsonify(snippet.as_dict()), 201


@app.route("/snippets", methods=["GET"])
def search_snippets() -> tuple:
    """
    Search snippets.

    Query parameters:
        keyword – text to search in title/description/tags (case‑insensitive)
        language – exact language name to filter by (case‑insensitive)
    """
    keyword = request.args.get("keyword")
    language = request.args.get("language")
    page = request.args.get("page", default=1, type=int)
    per_page = request.args.get("per_page", default=10, type=int)

    query = Snippet.query
    query = apply_search_filters(query, keyword, language)
    pagination = query.order_by(Snippet.id.desc()).paginate(page, per_page, error_out=False)

    results = [snip.as_dict() for snip in pagination.items]
    response = {
        "page": pagination.page,
        "per_page": pagination.per_page,
        "total": pagination.total,
        "pages": pagination.pages,
        "snippets": results,
    }
    return jsonify(response), 200


@app.route("/snippets/<int:snippet_id>", methods=["GET"])
def get_snippet(snippet_id: int) -> tuple:
    """Retrieve a snippet with syntax‑highlighted source code."""
    snippet: Snippet | None = Snippet.query