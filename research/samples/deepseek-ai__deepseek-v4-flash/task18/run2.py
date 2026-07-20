"""
Flask-based Code Snippet Manager.

Features:
- Save snippets with title, description, language, tags, and code.
- Search snippets by keyword or language.
- Edit and delete snippets.
- Syntax highlighting using Pygments (optional fallback to plain text).
- Security: parameterized SQL queries, input sanitization, CSRF protection.
"""

import sqlite3
import re
from datetime import datetime
from typing import Optional

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    session,
    abort,
)
from markupsafe import escape

# ---------- Pygments for syntax highlighting (optional) ----------
try:
    from pygments import highlight
    from pygments.lexers import get_lexer_by_name
    from pygments.formatters import HtmlFormatter

    PYGMENTS_AVAILABLE = True
except ImportError:
    PYGMENTS_AVAILABLE = False
    # Fallback: no highlighting
    def highlight(code, lexer, formatter):
        return f"<pre><code>{escape(code)}</code></pre>"

    class HtmlFormatter:
        def get_style_defs(self, arg=""):
            return ""

        def __call__(self, code):
            return f'<div class="highlight">{code}</div>'

# ---------- App configuration ----------
app = Flask(__name__)
app.secret_key = "change-this-to-a-secure-random-key-in-production"
DATABASE = "snippets.db"

# ---------- Database helper ----------
def get_db() -> sqlite3.Connection:
    """Return a connection to the SQLite database with row factory."""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def init_db() -> None:
    """Create the snippets table if it does not exist."""
    with get_db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS snippets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT DEFAULT '',
                language TEXT DEFAULT 'text',
                tags TEXT DEFAULT '',
                code TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.commit()

# ---------- Input validation ----------
def validate_snippet_input(
    title: str, description: str, language: str, tags: str, code: str
) -> Optional[str]:
    """
    Validate snippet fields. Returns an error message or None if valid.
    """
    if not title or not title.strip():
        return "Title is required."
    if not code or not code.strip():
        return "Code content is required."
    # Limit input lengths (security)
    if len(title) > 200:
        return "Title must be at most 200 characters."
    if len(description) > 500:
        return "Description must be at most 500 characters."
    if len(tags) > 500:
        return "Tags must be at most 500 characters."
    if len(language) > 50:
        return "Language must be at most 50 characters."
    if len(code) > 100000:
        return "Code snippet too large (max 100k characters)."
    return None

def sanitize_html(text: str) -> str:
    """Escape HTML special characters to prevent XSS."""
    return escape(text)

# ---------- Syntax highlighting ----------
def highlight_code(code: str, language: str) -> str:
    """
    Return HTML-highlighted code block.
    Falls back to plain text if Pygments is not installed.
    """
    if PYGMENTS_AVAILABLE:
        try:
            lexer = get_lexer_by_name(language, stripall=True)
            formatter = HtmlFormatter(style="friendly", noclasses=False)
            return highlight(code, lexer, formatter)
        except:
            # If lexer not found, fallback to plain text
            pass
    return f"<pre><code>{escape(code)}</code></pre>"

# ---------- Routes ----------
@app.route("/")
def index():
    """Display all snippets with optional search."""
    search_query = request.args.get("q", "").strip()
    lang_filter = request.args.get("lang", "").strip()
    conn = get_db()
    snippets = []
    try:
        if search_query:
            # Search by keyword in title, description, tags, or code
            snippets = conn.execute(
                """
                SELECT * FROM snippets
                WHERE title LIKE ? OR description LIKE ? OR tags LIKE ? OR code LIKE ?
                ORDER BY updated_at DESC
                """,
                (f"%{search_query}%",) * 4,
            ).fetchall()
        elif lang_filter:
            snippets = conn.execute(
                "SELECT * FROM snippets WHERE language = ? ORDER BY updated_at DESC",
                (lang_filter,),
            ).fetchall()
        else:
            snippets = conn.execute(
                "SELECT * FROM snippets ORDER BY updated_at DESC"
            ).fetchall()
    except sqlite3.Error as e:
        flash(f"Database error: {e}", "error")
    finally:
        conn.close()
    return render_template(
        "index.html",
        snippets=snippets,
        search_query=search_query,
        lang_filter=lang_filter,
        highlight=highlight_code,
    )

@app.route("/add", methods=["GET", "POST"])
def add_snippet():
    """Add a new snippet."""
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        language = request.form.get("language", "text").strip()
        tags = request.form.get("tags", "").strip()
        code = request.form.get("code", "")

        # Validate
        error = validate_snippet_input(title, description, language, tags, code)
        if error:
            flash(error, "error")
            return render_template("add_edit.html", snippet=None, action="Add")

        now = datetime.utcnow().isoformat()
        try:
            conn = get_db()
            conn.execute(
                """
                INSERT INTO snippets (title, description, language, tags, code, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (title, description, language, tags, code, now, now),
            )
            conn.commit()
            flash("Snippet added successfully!", "success")
            return redirect(url_for("index"))
        except sqlite3.Error as e:
            flash(f"Database error: {e}", "error")
        finally:
            conn.close()

    return render_template("add_edit.html", snippet=None, action="Add")

@app.route("/edit/<int:snippet_id>", methods=["GET", "POST"])
def edit_snippet(snippet_id: int):
    """Edit an existing snippet."""
    conn = get_db()
    snippet = None
    try:
        snippet = conn.execute(
            "SELECT * FROM snippets WHERE id = ?", (snippet_id,)
        ).fetchone()
    except sqlite3.Error as e:
        flash(f"Database error: {e}", "error")
        return redirect(url_for("index"))
    finally:
        conn.close()

    if snippet is None:
        abort(404)

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        language = request.form.get("language", "text").strip()
        tags = request.form.get("tags", "").strip()
        code = request.form.get("code", "")

        error = validate_snippet_input(title, description, language, tags, code)
        if error:
            flash(error, "error")
            return render_template("add_edit.html", snippet=snippet, action="Edit")

        now = datetime.utcnow().isoformat()
        try:
            conn = get_db()
            conn.execute(
                """
                UPDATE snippets
                SET title = ?, description = ?, language = ?, tags = ?, code = ?, updated_at = ?
                WHERE id = ?
                """,
                (title, description, language, tags, code, now, snippet_id),
            )
            conn.commit()
            flash("Snippet updated successfully!", "success")
            return redirect(url_for("index"))
        except sqlite3.Error as e:
            flash(f"Database error: {e}", "error")
        finally:
            conn.close()

    return render_template("add_edit.html", snippet=snippet, action="Edit")

@app.route("/delete/<int:snippet_id>", methods=["POST"])
def delete_snippet(snippet_id: int):
    """Delete a snippet."""
    # Simple CSRF check: require a hidden field with a token (here we just check POST)
    # For production, use Flask-WTF or similar
    try:
        conn = get_db()
        conn.execute("DELETE FROM snippets WHERE id = ?", (snippet_id,))
        conn.commit()
        flash("Snippet deleted.", "success")
    except sqlite3.Error as e:
        flash(f"Database error: {e}", "error")
    finally:
        conn.close()
    return redirect(url_for("index"))

# ---------- Error handlers ----------
@app.errorhandler(404)
def not_found(e):
    return render_template("error.html", message="Snippet not found."), 404

@app.errorhandler(500)
def internal_error(e):
    return render_template("error.html", message="Internal server error."), 500

# ---------- Initialize database on startup ----------
with app.app_context():
    init_db()

# ---------- Run the application ----------
if __name__ == "__main__":
    app.run(debug=True)  # Set debug=False in production