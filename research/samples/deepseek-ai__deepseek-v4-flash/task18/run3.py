from flask import Flask, render_template, request, redirect, url_for, flash, session
import sqlite3
import re
import secrets
from typing import List, Tuple, Optional
from pygments import highlight
from pygments.lexers import get_lexer_by_name, Lexer
from pygments.formatters import HtmlFormatter

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)  # Security: strong secret key

DATABASE = 'snippets.db'


# Database helper functions
def get_db() -> sqlite3.Connection:
    """Return a connection to the SQLite database with row factory."""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db() -> None:
    """Create the snippets table if it does not exist."""
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS snippets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                language TEXT NOT NULL DEFAULT 'text',
                code TEXT NOT NULL,
                tags TEXT NOT NULL DEFAULT ''
            )
        """)
        conn.commit()


def add_snippet(title: str, description: str, language: str, code: str, tags: str) -> int:
    """Insert a new snippet into the database and return its ID."""
    with get_db() as conn:
        cur = conn.execute(
            "INSERT INTO snippets (title, description, language, code, tags) VALUES (?, ?, ?, ?, ?)",
            (title.strip(), description.strip(), language.strip(), code, tags.strip())
        )
        conn.commit()
        return cur.lastrowid


def get_all_snippets() -> List[sqlite3.Row]:
    """Return all snippets ordered by id descending."""
    with get_db() as conn:
        return conn.execute("SELECT * FROM snippets ORDER BY id DESC").fetchall()


def get_snippet_by_id(snippet_id: int) -> Optional[sqlite3.Row]:
    """Return a snippet by its id, or None if not found."""
    with get_db() as conn:
        return conn.execute("SELECT * FROM snippets WHERE id = ?", (snippet_id,)).fetchone()


def update_snippet(snippet_id: int, title: str, description: str, language: str, code: str, tags: str) -> bool:
    """Update an existing snippet. Returns True if successful."""
    with get_db() as conn:
        cur = conn.execute(
            "UPDATE snippets SET title=?, description=?, language=?, code=?, tags=? WHERE id=?",
            (title.strip(), description.strip(), language.strip(), code, tags.strip(), snippet_id)
        )
        conn.commit()
        return cur.rowcount > 0


def delete_snippet(snippet_id: int) -> bool:
    """Delete a snippet by id. Returns True if successful."""
    with get_db() as conn:
        cur = conn.execute("DELETE FROM snippets WHERE id = ?", (snippet_id,))
        conn.commit()
        return cur.rowcount > 0


def search_snippets(query: str, language: Optional[str] = None) -> List[sqlite3.Row]:
    """
    Search snippets by keyword in title/description/tags, optionally filtered by language.
    Uses LIKE with % wildcard (parameterized to prevent injection).
    """
    with get_db() as conn:
        if language:
            cur = conn.execute(
                """SELECT * FROM snippets
                   WHERE (title LIKE ? OR description LIKE ? OR tags LIKE ?)
                   AND language = ?
                   ORDER BY id DESC""",
                (f"%{query}%", f"%{query}%", f"%{query}%", language)
            )
        else:
            cur = conn.execute(
                """SELECT * FROM snippets
                   WHERE title LIKE ? OR description LIKE ? OR tags LIKE ?
                   ORDER BY id DESC""",
                (f"%{query}%", f"%{query}%", f"%{query}%")
            )
        return cur.fetchall()


def highlight_code(code: str, language: str) -> str:
    """
    Return HTML with syntax highlighting for the given code and language.
    Falls back to plain text if lexer not found.
    """
    try:
        lexer: Lexer = get_lexer_by_name(language, stripall=True)
    except:
        lexer = get_lexer_by_name('text', stripall=True)
    formatter = HtmlFormatter(style='friendly', noclasses=True, lineseparator='<br>')
    return highlight(code, lexer, formatter)


# CSRF protection
def generate_csrf_token() -> str:
    """Generate and store a CSRF token in the session."""
    if '_csrf_token' not in session:
        session['_csrf_token'] = secrets.token_hex(16)
    return session['_csrf_token']


def validate_csrf_token(token: str) -> bool:
    """Validate the provided CSRF token against the session token."""
    stored = session.get('_csrf_token')
    if not stored or not token:
        return False
    # Use secrets.compare_digest to prevent timing attacks
    return secrets.compare_digest(stored, token)


@app.before_request
def csrf_check() -> None:
    """For POST requests that are not for the login (or any safe action), validate CSRF token."""
    if request.method == 'POST':
        # CSRF token is expected in the form data
        token = request.form.get('csrf_token', '')
        if not validate_csrf_token(token):
            flash('Invalid or missing CSRF token.', 'error')
            # Redirect back to previous page if possible
            return redirect(request.referrer or url_for('index'))
    # Refresh token after each request (optional, but good security practice)
    generate_csrf_token()


@app.context_processor
def inject_csrf_token() -> dict:
    """Make csrf_token available in all templates."""
    return {'csrf_token': generate_csrf_token()}


# Routes
@app.route('/')
def index():
    """Display all snippets."""
    snippets = get_all_snippets()
    return render_template('index.html', snippets=snippets, highlight=highlight_code)


@app.route('/add', methods=['GET', 'POST'])
def add():
    """Add a new snippet."""
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        language = request.form.get('language', 'text').strip()
        code = request.form.get('code', '')
        tags = request.form.get('tags', '').strip()

        # Input validation
        if not title or len(title) > 200:
            flash('Title is required and must be under 200 characters.', 'error')
            return render_template('add.html')
        if len(description) > 500:
            flash('Description must be under 500 characters.', 'error')
            return render_template('add.html')
        if not code:
            flash('Code is required.', 'error')
            return render_template('add.html')
        # Prevent script injection in language field (only allow alphanumeric and underscore/dash)
        if not re.match(r'^[a-zA-Z0-9_\-+#]+$', language):
            flash('Language contains invalid characters.', 'error')
            return render_template('add.html')
        if len(tags) > 500:
            flash('Tags must be under 500 characters.', 'error')
            return render_template('add.html')

        try:
            add_snippet(title, description, language, code, tags)
            flash('Snippet added successfully!', 'success')
            return redirect(url_for('index'))
        except Exception as e:
            flash(f'Database error: {str(e)}', 'error')
            return render_template('add.html')

    return render_template('add.html')


@app.route('/edit/<int:snippet_id>', methods=['GET', 'POST'])
def edit(snippet_id: int):
    """Edit an existing snippet."""
    snippet = get_snippet_by_id(snippet_id)
    if not snippet:
        flash('Snippet not found.', 'error')
        return redirect(url_for('index'))

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        language = request.form.get('language', 'text').strip()
        code = request.form.get('code', '')
        tags = request.form.get('tags', '').strip()

        if not title or len(title) > 200:
            flash('Title is required and must be under 200 characters.', 'error')
            return render_template('edit.html', snippet=snippet)
        if len(description) > 500:
            flash('Description must be under 500 characters.', 'error')
            return render_template('edit.html', snippet=snippet)
        if not code:
            flash('Code is required.', 'error')
            return render_template('edit.html', snippet=snippet)
        if not re.match(r'^[a-zA-Z0-9_\-+#]+$', language):
            flash('Language contains invalid characters.', 'error')
            return render_template('edit.html', snippet=snippet)
        if len(tags) > 500:
            flash('Tags must be under 500 characters.', 'error')
            return render_template('edit.html', snippet=snippet)

        try:
            if update_snippet(snippet_id, title, description, language, code, tags):
                flash('Snippet updated successfully!', 'success')
                return redirect(url_for('index'))
            else:
                flash('Snippet could not be updated (maybe it was deleted).', 'error')
                return redirect(url_for('index'))
        except Exception as e:
            flash(f'Database error: {str(e)}', 'error')
            return render_template('edit.html', snippet=snippet)

    return render_template('edit.html', snippet=snippet)


@app.route('/delete/<int:snippet_id>', methods=['POST'])
def delete(snippet_id: int):
    """Delete a snippet."""
    try:
        if delete_snippet(snippet_id):
            flash('Snippet deleted successfully!', 'success')
        else:
            flash('Snippet not found.', 'error')
    except Exception as e:
        flash(f'Database error: {str(e)}', 'error')
    return redirect(url_for('index'))


@app.route('/search', methods=['GET', 'POST'])
def search():
    """Search snippets by keyword and optionally filter by language."""
    query = request.args.get('q', '').strip()
    language = request.args.get('language', '').strip() or None
    results = []
    if query:
        results = search_snippets(query, language)
    return render_template('search.html', results=results, query=query, language=language or '', highlight=highlight_code)


# Initialize database on startup
with app.app_context():
    init_db()

if __name__ == '__main__':
    app.run(debug=True)