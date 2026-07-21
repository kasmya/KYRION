"""
Snippet Manager
----------------
A Flask based web application for storing, searching, editing and deleting code
snippets. Supports syntax highlighting using Pygments.

Dependencies (install via pip):
    Flask==2.3.*
    Flask_SQLAlchemy==3.0.*
    Flask_WTF==1.1.*
    WTForms==3.1.*
    Pygments==2.16.*

Run:
    $ export FLASK_APP=snippet_manager.py
    $ export FLASK_ENV=development
    $ flask run
"""

import os
import re
import sys
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
from pygments.lexers import get_lexer_by_name, guess_lexer
from wtforms import (
    StringField,
    TextAreaField,
    SelectField,
    SubmitField,
)
from wtforms.validators import DataRequired, Length, Regexp

# --------------------------------------------------------------------------- #
# Application and extensions setup
# --------------------------------------------------------------------------- #

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY", os.urandom(24).hex())
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///snippets.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)
csrf = CSRFProtect(app)

# --------------------------------------------------------------------------- #
# Database model
# --------------------------------------------------------------------------- #


class Snippet(db.Model):
    """Database model representing a code snippet."""

    __tablename__ = "snippets"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    title = db.Column(db.String(120), nullable=False, unique=True)
    description = db.Column(db.String(500), nullable=True)
    language = db.Column(db.String(30), nullable=False)
    tags = db.Column(db.String(200), nullable=True)  # comma‑separated tags
    code = db.Column(db.Text, nullable=False)

    def tag_list(self) -> List[str]:
        """Return tags as a list of stripped strings."""
        if not self.tags:
            return []
        return [t.strip() for t in self.tags.split(",") if t.strip()]

    def matches_keyword(self, keyword: str) -> bool:
        """Return True if keyword appears in title, description or tags."""
        lowered = keyword.lower()
        return (
            lowered in self.title.lower()
            or (self.description and lowered in self.description.lower())
            or any(lowered in tag.lower() for tag in self.tag_list())
        )


# --------------------------------------------------------------------------- #
# Forms
# --------------------------------------------------------------------------- #


def _language_choices() -> List[tuple]:
    """Return a list of (language_slug, display_name) tuples for the form."""
    # Very common languages; add more as needed.
    common = [
        ("python", "Python"),
        ("javascript", "JavaScript"),
        ("java", "Java"),
        ("c", "C"),
        ("cpp", "C++"),
        ("go", "Go"),
        ("ruby", "Ruby"),
        ("php", "PHP"),
        ("html", "HTML"),
        ("css", "CSS"),
        ("bash", "Bash"),
        ("sql", "SQL"),
        ("plaintext", "Plain Text"),
    ]
    return common


class SnippetForm(FlaskForm):
    """Form for creating and editing snippets."""

    title = StringField(
        "Title",
        validators=[
            DataRequired(),
            Length(max=120),
            Regexp(r"^[^<>#%]+$", message="Invalid characters in title."),
        ],
    )
    description = StringField(
        "Description", validators=[Length(max=500)], render_kw={"placeholder": "Optional"}
    )
    language = SelectField(
        "Language", choices=_language_choices(), validators=[DataRequired()]
    )
    tags = StringField(
        "Tags",
        validators=[Length(max=200)],
        render_kw={"placeholder": "Comma‑separated, e.g. python, utils"},
    )
    code = TextAreaField("Code", validators=[DataRequired()], render_kw={"rows": 15})
    submit = SubmitField("Save")


class SearchForm(FlaskForm):
    """Form for searching snippets."""

    keyword = StringField("Keyword", validators=[Length(max=100)], render_kw={"placeholder": "Search term"})
    language = SelectField("Language", choices=[("", "Any")] + _language_choices())
    submit = SubmitField("Search")


# --------------------------------------------------------------------------- #
# Utility functions
# --------------------------------------------------------------------------- #


def highlight_code(code: str, language: str) -> str:
    """
    Return HTML with syntax‑highlighted code using Pygments.

    Args:
        code: The raw source code.
        language: Language identifier used by Pygments.

    Returns:
        Safe HTML string containing highlighted code.
    """
    try:
        lexer = get_lexer_by_name(language, stripall=True)
    except Exception:
        lexer = guess_lexer(code)
    formatter = HtmlFormatter(linenos=True, cssclass="codehilite")
    return highlight(code, lexer, formatter)


def sanitize_input(text: Optional[str]) -> str:
    """Trim whitespace and replace dangerous sequences; used before DB storage."""
    if not text:
        return ""
    # Remove leading/trailing whitespace and collapse internal whitespace
    cleaned = re.sub(r"\s+", " ", text).strip()
    # Simple blacklist check – can be expanded.
    if re.search(r"[<>]", cleaned):
        raise ValueError("Input contains forbidden characters.")
    return cleaned


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #


@app.route("/", methods=["GET", "POST"])
def index() -> str:
    """
    Home page showing a list of snippets and a search form.
    Supports keyword and language filtering.
    """
    form = SearchForm()
    query = Snippet.query

    if form.validate_on_submit():
        keyword = form.keyword.data.strip()
        language = form.language.data

        if keyword:
            query = query.filter(
                db.or_(
                    Snippet.title.ilike(f"%{keyword}%"),
                    Snippet.description.ilike(f"%{keyword}%"),
                    Snippet.tags.ilike(f"%{keyword}%"),
                )
            )
        if language:
            query = query.filter_by(language=language)

    snippets = query.order_by(Snippet.id.desc()).all()

    template = """
    {% extends "base.html" %}
    {% block content %}
        <h1>Snippet Manager</h1>
        <a class="btn btn-primary" href="{{ url_for('create') }}">Add New Snippet</a>
        <hr>
        <form method="post" class="form-inline mb-3">
            {{ form.hidden_tag() }}
            <div class="form-group mr-2">{{ form.keyword(class_="form-control", placeholder="Keyword") }}</div>
            <div class="form-group mr-2">{{ form.language(class_="form-control") }}</div>
            {{ form.submit(class_="btn btn-success") }}
        </form>
        {% if snippets %}
            <ul class="list-group">
            {% for snip in snippets %}
                <li class="list-group-item">
                    <h5><a href="{{ url_for('view', snippet_id=snip.id) }}">{{ snip.title }}</a></h5>
                    <p class="mb-1"><small>{{ snip.description or '' }}</small></p>
                    <span class="badge badge-info">{{ snip.language }}</span>
                    {% for tag in snip.tag_list() %}
                        <span class="badge badge-secondary">{{ tag }}</span>
                    {% endfor %}
                    <div class="float-right">
                        <a href="{{ url_for('edit', snippet_id=snip.id) }}" class="btn btn-sm btn-outline-primary">Edit</a>