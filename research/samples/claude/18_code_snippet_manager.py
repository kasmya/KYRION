"""
### Task 18: Code Snippet Manager (Flask + Markdown)

A Flask application for creating, editing, deleting, and searching code
snippets, with syntax highlighting via Pygments and export to Markdown or
HTML.

Requirements:
    pip install flask flask-sqlalchemy pygments markdown

Run:
    python 18_code_snippet_manager.py
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Optional

from flask import Flask, Response, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_by_name
from pygments.util import ClassNotFound

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("code_snippet_manager")

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///snippets.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)


class Snippet(db.Model):
    """Represents a single stored code snippet."""

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    code = db.Column(db.Text, nullable=False)
    language = db.Column(db.String(50), nullable=False, default="text")
    tags = db.Column(db.String(300), nullable=True)  # comma-separated
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def tag_list(self) -> List[str]:
        return [t.strip() for t in (self.tags or "").split(",") if t.strip()]

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "code": self.code,
            "language": self.language,
            "tags": self.tag_list(),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


@app.post("/api/snippets")
def create_snippet():
    """Creates a new code snippet."""
    payload = request.get_json(silent=True) or {}
    title = payload.get("title", "").strip()
    code = payload.get("code", "")
    language = payload.get("language", "text").strip() or "text"
    tags = payload.get("tags", [])

    if not title:
        return jsonify({"error": "title is required"}), 400
    if not code:
        return jsonify({"error": "code is required"}), 400

    snippet = Snippet(title=title, code=code, language=language, tags=",".join(tags))
    db.session.add(snippet)
    db.session.commit()
    logger.info("Created snippet '%s' (id=%s)", title, snippet.id)
    return jsonify(snippet.to_dict()), 201


@app.get("/api/snippets/<int:snippet_id>")
def get_snippet(snippet_id: int):
    """Fetches a single snippet by id, with highlighted HTML included."""
    snippet = Snippet.query.get(snippet_id)
    if not snippet:
        return jsonify({"error": "snippet not found"}), 404

    highlighted = _highlight_code(snippet.code, snippet.language)
    data = snippet.to_dict()
    data["highlighted_html"] = highlighted
    return jsonify(data), 200


@app.put("/api/snippets/<int:snippet_id>")
def update_snippet(snippet_id: int):
    """Updates an existing snippet's fields."""
    snippet = Snippet.query.get(snippet_id)
    if not snippet:
        return jsonify({"error": "snippet not found"}), 404

    payload = request.get_json(silent=True) or {}
    if "title" in payload:
        snippet.title = payload["title"].strip() or snippet.title
    if "code" in payload:
        snippet.code = payload["code"]
    if "language" in payload:
        snippet.language = payload["language"].strip() or snippet.language
    if "tags" in payload:
        snippet.tags = ",".join(payload["tags"])

    db.session.commit()
    return jsonify(snippet.to_dict()), 200


@app.delete("/api/snippets/<int:snippet_id>")
def delete_snippet(snippet_id: int):
    """Deletes a snippet by id."""
    snippet = Snippet.query.get(snippet_id)
    if not snippet:
        return jsonify({"error": "snippet not found"}), 404
    db.session.delete(snippet)
    db.session.commit()
    return jsonify({"deleted": snippet_id}), 200


@app.get("/api/snippets")
def search_snippets():
    """Searches snippets by tag and/or free-text content match."""
    tag = request.args.get("tag")
    query_text = request.args.get("q")

    query = Snippet.query
    if tag:
        query = query.filter(Snippet.tags.ilike(f"%{tag}%"))
    if query_text:
        like_pattern = f"%{query_text}%"
        query = query.filter(
            db.or_(Snippet.title.ilike(like_pattern), Snippet.code.ilike(like_pattern))
        )

    snippets = query.order_by(Snippet.updated_at.desc()).all()
    return jsonify([s.to_dict() for s in snippets]), 200


def _highlight_code(code: str, language: str) -> str:
    """Renders syntax-highlighted HTML for a code snippet via Pygments."""
    try:
        lexer = get_lexer_by_name(language)
    except ClassNotFound:
        logger.warning("Unknown language '%s', falling back to plain text", language)
        lexer = get_lexer_by_name("text")
    formatter = HtmlFormatter(noclasses=True)
    return highlight(code, lexer, formatter)


@app.get("/api/snippets/<int:snippet_id>/export")
def export_snippet(snippet_id: int):
    """Exports a snippet as either Markdown or HTML, via ?format=markdown|html."""
    snippet = Snippet.query.get(snippet_id)
    if not snippet:
        return jsonify({"error": "snippet not found"}), 404

    export_format = request.args.get("format", "markdown").lower()

    if export_format == "markdown":
        content = f"# {snippet.title}\n\n```{snippet.language}\n{snippet.code}\n```\n"
        return Response(content, mimetype="text/markdown")

    if export_format == "html":
        import markdown as md_lib

        highlighted = _highlight_code(snippet.code, snippet.language)
        html_content = (
            f"<html><head><title>{snippet.title}</title></head>"
            f"<body><h1>{snippet.title}</h1>{highlighted}</body></html>"
        )
        return Response(html_content, mimetype="text/html")

    return jsonify({"error": "format must be 'markdown' or 'html'"}), 400


@app.errorhandler(500)
def handle_internal_error(exc):
    logger.exception("Unhandled server error: %s", exc)
    return jsonify({"error": "internal server error"}), 500


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(host="0.0.0.0", port=5002, debug=False)
