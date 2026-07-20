"""
Snippet Manager Flask Application
--------------------------------

Features:
- Store code snippets with title, description, language, and tags.
- Search snippets by keyword (title/description/tags) or programming language.
- Create, edit, delete snippets (CRUD).
- Display snippets with syntax highlighting using Pygments.
- Type hints, docstrings, error handling, and security best practices.

Dependencies (install via pip):
    pip install Flask Flask_SQLAlchemy Flask_WTF WTForms Pygments
"""

from __future__ import annotations

import os
import re
from datetime import datetime
from typing import List, Optional

from flask import (
    Flask,
    abort,
    flash,
    redirect,
    render_template_string,
    request,
    url_for,
)
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import FlaskForm, CSRFProtect
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_by_name, TextLexer
from wtforms import (
    HiddenField,
    SelectField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.validators import DataRequired, Length, Regexp

# --------------------------------------------------------------------------- #
# Application and Extensions Setup
# --------------------------------------------------------------------------- #

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATABASE_PATH = os.path.join(BASE_DIR, "snippets.db")

app = Flask(__name__)
app.config["SECRET_KEY"] = os.urandom(24)  # Use a strong random secret key
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{DATABASE_PATH}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)
csrf = CSRFProtect(app)

# --------------------------------------------------------------------------- #
# Database Model
# --------------------------------------------------------------------------- #


class Snippet(db.Model):
    """SQLAlchemy model representing a code snippet."""

    __tablename__ = "snippets"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(120), nullable=False, unique=True)
    description = db.Column(db.String(500), nullable=True)
    code = db.Column(db.Text, nullable=False)
    language = db.Column(db.String(30), nullable=False)
    tags = db.Column(db.String(250), nullable=True)  # comma‑separated tags
    created_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow
    )
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    @property
    def tag_list(self) -> List[str]:
        """Return tags as a cleaned list of strings."""
        if not self.tags:
            return []
        return [t.strip() for t in self.tags.split(",") if t.strip()]

    def __repr__(self) -> str:
        return f"<Snippet {self.id} – {self.title!r}>"


# --------------------------------------------------------------------------- #
# Forms
# --------------------------------------------------------------------------- #


def _validate_tags(form, field):
    """Validate that tags are a comma‑separated list of word characters."""
    if not field.data:
        return
    for tag in field.data.split(","):
        tag = tag.strip()
        if not re.fullmatch(r"\w+", tag):
            raise ValueError(
                f"Invalid tag '{tag}'. Tags must contain only letters, digits, or underscore."
            )


class SnippetForm(FlaskForm):
    """Form for creating or editing a snippet."""

    title = StringField(
        "Title",
        validators=[
            DataRequired(),
            Length(max=120, message="Title must be at most 120 characters."),
        ],
    )
    description = StringField(
        "Description",
        validators=[Length(max=500, message="Description must be at most 500 characters.")],
    )
    language = SelectField(
        "Language",
        choices=[
            ("python", "Python"),
            ("javascript", "JavaScript"),
            ("java", "Java"),
            ("c", "C"),
            ("cpp", "C++"),
            ("go", "Go"),
            ("ruby", "Ruby"),
            ("bash", "Bash"),
            ("html", "HTML"),
            ("css", "CSS"),
            ("sql", "SQL"),
            ("text", "Plain Text"),
        ],
        validators=[DataRequired()],
    )
    tags = StringField(
        "Tags (comma separated)",
        validators=[_validate_tags],
        description="Enter tags separated by commas. Only letters, digits, and underscores are allowed.",
    )
    code = TextAreaField(
        "Code",
        validators=[
            DataRequired(),
            Length(min=1, message="Code cannot be empty."),
        ],
    )
    snippet_id = HiddenField()  # used for editing
    submit = SubmitField("Save")


# --------------------------------------------------------------------------- #
# Helper Functions
# --------------------------------------------------------------------------- #


def highlight_code(code: str, language: str) -> str:
    """
    Return HTML with syntax‑highlighted code using Pygments.

    Args:
        code: Raw source code.
        language: Language identifier accepted by Pygments.

    Returns:
        HTML string with highlighted code.
    """
    try:
        lexer = get_lexer_by_name(language, stripall=True)
    except Exception:
        lexer = TextLexer(stripall=True)
    formatter = HtmlFormatter(linenos=True, cssclass="codehilite")
    return highlight(code, lexer, formatter)


def init_db() -> None:
    """Initialize the SQLite database if it does not exist."""
    if not os.path.exists(DATABASE_PATH):
        db.create_all()
        # Optionally, add a few sample snippets
        sample = Snippet(
            title="Hello World in Python",
            description="Simple hello world example.",
            code='print("Hello, World!")',
            language="python",
            tags="example,hello",
        )
        db.session.add(sample)
        db.session.commit()


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #


@app.route("/", methods=["GET"])
def index() -> str:
    """
    Home page – list snippets with optional search filters.
    """
    keyword = request.args.get("q", "").strip()
    language = request.args.get("lang", "").strip()

    query = Snippet.query
    if keyword:
        like_pattern = f"%{keyword}%"
        query = query.filter(
            db.or_(
                Snippet.title.ilike(like_pattern),
                Snippet.description.ilike(like_pattern),
                Snippet.tags.ilike(like_pattern),
            )
        )
    if language:
        query = query.filter(Snippet.language == language)

    snippets = query.order_by(Snippet.updated_at.desc()).all()

    template = """
    <!doctype html>
    <title>Snippet Manager</title>
    <link rel="stylesheet" href="{{ url_for('static', filename='style.css') }}">
    <h1>Snippet Manager</h1>

    <form method="get" action="{{ url_for('index') }}">
        <input type="text" name="q" placeholder="Search..." value="{{ request.args.get('q','') }}">
        <select name="lang">
            <option value="">All Languages</option>
            {% for code, name in language_choices %}
            <option value="{{ code }}" {% if request.args.get('lang') == code %}selected{% endif %}>{{ name }}</option>
            {% endfor %}
        </select>
        <button type="submit">Search</button>
        <a href="{{ url_for('create') }}">Create New Snippet</a>
    </form>

    {% for snippet in snippets %}
        <div class="snippet-summary">
            <h2><a href="{{ url_for('view_snippet', snippet_id=snippet.id) }}">{{ snippet.title }}</a></h2>
            <p>{{ snippet.description or '' }}</p>
            <p><strong>Language:</strong> {{ snippet.language }} | <strong>Tags:</strong> {{