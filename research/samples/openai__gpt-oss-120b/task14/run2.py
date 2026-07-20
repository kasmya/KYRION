"""
Simple forum application using Flask, Flask-Login and Flask-SQLAlchemy.

Features:
- User registration & login with password hashing (bcrypt)
- Create / edit / delete posts
- Comment on posts
- Upvote / downvote posts (one vote per user)
- Search posts by title/content
- CSRF protection, input validation, error handling
"""

from __future__ import annotations

import os
from typing import Any, Optional

from flask import (
    Flask,
    abort,
    flash,
    g,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import (
    LoginManager,
    UserMixin,
    current_user,
    login_required,
    login_user,
    logout_user,
)
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import FlaskForm, CSRFProtect
from passlib.hash import bcrypt
from sqlalchemy import CheckConstraint, func, select
from sqlalchemy.exc import IntegrityError
from wtforms import (
    BooleanField,
    IntegerField,
    PasswordField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.validators import DataRequired, Length, ValidationError

# --------------------------------------------------------------------------- #
# Flask application setup
# --------------------------------------------------------------------------- #
app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY", "change-me-in-production")
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///forum.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"
csrf = CSRFProtect(app)


# --------------------------------------------------------------------------- #
# Database models
# --------------------------------------------------------------------------- #
class User(UserMixin, db.Model):
    """User model representing a forum participant."""

    __tablename__ = "users"

    id: Any = db.Column(db.Integer, primary_key=True)
    username: Any = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash: Any = db.Column(db.String(128), nullable=False)

    posts = db.relationship("Post", back_populates="author", cascade="all, delete-orphan")
    comments = db.relationship(
        "Comment", back_populates="author", cascade="all, delete-orphan"
    )
    votes = db.relationship("Vote", back_populates="user", cascade="all, delete-orphan")

    def set_password(self, password: str) -> None:
        """Hash and store a password."""
        self.password_hash = bcrypt.hash(password)

    def check_password(self, password: str) -> bool:
        """Check password against stored hash."""
        return bcrypt.verify(password, self.password_hash)


class Post(db.Model):
    """Forum post."""

    __tablename__ = "posts"

    id: Any = db.Column(db.Integer, primary_key=True)
    title: Any = db.Column(db.String(200), nullable=False, index=True)
    body: Any = db.Column(db.Text, nullable=False)
    created_at: Any = db.Column(
        db.DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Any = db.Column(
        db.DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    author_id: Any = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    author = db.relationship("User", back_populates="posts")
    comments = db.relationship(
        "Comment", back_populates="post", cascade="all, delete-orphan"
    )
    votes = db.relationship("Vote", back_populates="post", cascade="all, delete-orphan")

    @property
    def score(self) -> int:
        """Calculate net score from votes."""
        return sum(vote.value for vote in self.votes)


class Comment(db.Model):
    """Comment on a post."""

    __tablename__ = "comments"

    id: Any = db.Column(db.Integer, primary_key=True)
    body: Any = db.Column(db.Text, nullable=False)
    created_at: Any = db.Column(
        db.DateTime, server_default=func.now(), nullable=False
    )
    author_id: Any = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    post_id: Any = db.Column(
        db.Integer, db.ForeignKey("posts.id", ondelete="CASCADE"), nullable=False
    )

    author = db.relationship("User", back_populates="comments")
    post = db.relationship("Post", back_populates="comments")


class Vote(db.Model):
    """Upvote / downvote on a post (value = 1 or -1)."""

    __tablename__ = "votes"
    __table_args__ = (CheckConstraint("value IN (1, -1)", name="ck_vote_value"),)

    id: Any = db.Column(db.Integer, primary_key=True)
    value: Any = db.Column(db.Integer, nullable=False)  # 1 for upvote, -1 for downvote
    user_id: Any = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    post_id: Any = db.Column(
        db.Integer, db.ForeignKey("posts.id", ondelete="CASCADE"), nullable=False
    )

    user = db.relationship("User", back_populates="votes")
    post = db.relationship("Post", back_populates="votes")

    __table_args__ = (
        db.UniqueConstraint("user_id", "post_id", name="uq_user_post_vote"),
        CheckConstraint("value IN (1, -1)", name="ck_vote_value"),
    )


# --------------------------------------------------------------------------- #
# User loader
# --------------------------------------------------------------------------- #
@login_manager.user_loader
def load_user(user_id: str) -> Optional[User]:
    return User.query.get(int(user_id))


# --------------------------------------------------------------------------- #
# Forms
# --------------------------------------------------------------------------- #
class RegistrationForm(FlaskForm):
    """Form for user registration."""

    username = StringField(
        "Username", validators=[DataRequired(), Length(min=3, max=80)]
    )
    password = PasswordField(
        "Password", validators=[DataRequired(), Length(min=6, max=128)]
    )
    submit = SubmitField("Register")

    def validate_username(self, field: StringField) -> None:
        if User.query.filter_by(username=field.data).first():
            raise ValidationError("Username already taken.")


class LoginForm(FlaskForm):
    """Form for user login."""

    username = StringField("Username", validators=[DataRequired(), Length(max=80)])
    password = PasswordField("Password", validators=[DataRequired()])
    remember = BooleanField("Remember me")
    submit = SubmitField("Login")


class PostForm(FlaskForm):
    """Form for creating or editing a post."""

    title = StringField(
        "Title", validators=[DataRequired(), Length(min=3, max=200)]
    )
    body = TextAreaField("Content", validators=[DataRequired(), Length(min=5)])
    submit = SubmitField("Submit")


class CommentForm(FlaskForm):
    """Form for posting a comment."""

    body = TextAreaField("Comment", validators=[DataRequired(), Length(min=1, max=1000)])
    submit = SubmitField("Post Comment")


class SearchForm(FlaskForm):
    """Form for searching posts."""

    query = StringField("Search", validators=[DataRequired(), Length(min=1, max=200)])
    submit = SubmitField("Search")


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #
@app.before_request
def load_global_search_form() -> None:
    """Make the search form available in all templates."""
    g.search_form = SearchForm()


@app.route("/")
def index() -> str:
    """Display a list of posts."""
    page = request.args.get("page", 1, type=int)
    posts = (
        Post.query.order_by(Post.created_at.desc())
        .paginate(page=page, per_page=10, error_out=False)
    )
    return render_template("index.html", posts=posts)


@app.route("/register", methods=["GET", "POST"])
def register() -> str |