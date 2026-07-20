#!/usr/bin/env python3
"""
A minimal Flask-based forum/discussion board.

Features:
- User registration and login with password hashing
- Create, edit, delete posts
- Comment on posts
- Upvote / downvote posts
- Full‑text search on post titles and bodies
- CSRF protection, input validation, and security‑focused defaults
"""

import os
import datetime as dt
from typing import Optional, List, Tuple

from flask import (
    Flask,
    render_template,
    redirect,
    url_for,
    flash,
    request,
    abort,
    Markup,
)
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager,
    login_user,
    logout_user,
    login_required,
    current_user,
    UserMixin,
)
from flask_wtf import FlaskForm
from wtforms import (
    StringField,
    PasswordField,
    TextAreaField,
    SubmitField,
    HiddenField,
    IntegerField,
)
from wtforms.validators import DataRequired, Length, Email, EqualTo, ValidationError
from flask_bcrypt import Bcrypt

# --------------------------------------------------------------------------- #
# Application setup
# --------------------------------------------------------------------------- #
app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY", "change-me-in-production")
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///forum.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"
bcrypt = Bcrypt(app)


# --------------------------------------------------------------------------- #
# Database models
# --------------------------------------------------------------------------- #
class User(db.Model, UserMixin):
    """Registered user."""

    id: int = db.Column(db.Integer, primary_key=True)
    username: str = db.Column(db.String(30), unique=True, nullable=False, index=True)
    email: str = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash: str = db.Column(db.String(128), nullable=False)
    posts: List["Post"] = db.relationship("Post", backref="author", lazy="dynamic")
    comments: List["Comment"] = db.relationship(
        "Comment", backref="author", lazy="dynamic"
    )
    votes: List["Vote"] = db.relationship("Vote", backref="voter", lazy="dynamic")

    def set_password(self, password: str) -> None:
        """Hash and store a password."""
        self.password_hash = bcrypt.generate_password_hash(password).decode("utf-8")

    def check_password(self, password: str) -> bool:
        """Verify password against stored hash."""
        return bcrypt.check_password_hash(self.password_hash, password)

    def __repr__(self) -> str:
        return f"<User {self.username}>"


class Post(db.Model):
    """A discussion post."""

    id: int = db.Column(db.Integer, primary_key=True)
    title: str = db.Column(db.String(140), nullable=False, index=True)
    body: str = db.Column(db.Text, nullable=False)
    timestamp: dt.datetime = db.Column(
        db.DateTime, nullable=False, default=dt.datetime.utcnow, index=True
    )
    user_id: int = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    comments: List["Comment"] = db.relationship(
        "Comment", backref="post", cascade="all, delete-orphan", lazy="dynamic"
    )
    votes: List["Vote"] = db.relationship(
        "Vote", backref="post", cascade="all, delete-orphan", lazy="dynamic"
    )

    @property
    def score(self) -> int:
        """Current vote score (upvotes - downvotes)."""
        return sum(vote.value for vote in self.votes)

    def __repr__(self) -> str:
        return f"<Post {self.title[:20]}…>"


class Comment(db.Model):
    """Comment on a post."""

    id: int = db.Column(db.Integer, primary_key=True)
    body: str = db.Column(db.Text, nullable=False)
    timestamp: dt.datetime = db.Column(
        db.DateTime, nullable=False, default=dt.datetime.utcnow, index=True
    )
    user_id: int = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    post_id: int = db.Column(db.Integer, db.ForeignKey("post.id"), nullable=False)

    def __repr__(self) -> str:
        return f"<Comment {self.id} on Post {self.post_id}>"


class Vote(db.Model):
    """Upvote (+1) or downvote (-1) on a post."""

    id: int = db.Column(db.Integer, primary_key=True)
    value: int = db.Column(db.Integer, nullable=False)  # +1 or -1
    user_id: int = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    post_id: int = db.Column(db.Integer, db.ForeignKey("post.id"), nullable=False)

    __table_args__ = (
        db.UniqueConstraint("user_id", "post_id", name="unique_user_post_vote"),
    )

    def __repr__(self) -> str:
        return f"<Vote {self.value} by User {self.user_id} on Post {self.post_id}>"


# --------------------------------------------------------------------------- #
# Login manager
# --------------------------------------------------------------------------- #
@login_manager.user_loader
def load_user(user_id: str) -> Optional[User]:
    return User.query.get(int(user_id))


# --------------------------------------------------------------------------- #
# Form definitions
# --------------------------------------------------------------------------- #
class RegistrationForm(FlaskForm):
    username = StringField(
        "Username",
        validators=[DataRequired(), Length(min=3, max=30)],
        render_kw={"autocomplete": "username"},
    )
    email = StringField(
        "Email",
        validators=[DataRequired(), Email()],
        render_kw={"autocomplete": "email"},
    )
    password = PasswordField(
        "Password",
        validators=[DataRequired(), Length(min=8)],
        render_kw={"autocomplete": "new-password"},
    )
    confirm_password = PasswordField(
        "Confirm Password",
        validators=[
            DataRequired(),
            EqualTo("password", message="Passwords must match."),
        ],
        render_kw={"autocomplete": "new-password"},
    )
    submit = SubmitField("Register")

    def validate_username(self, username: StringField) -> None:
        if User.query.filter_by(username=username.data).first():
            raise ValidationError("Username already taken.")

    def validate_email(self, email: StringField) -> None:
        if User.query.filter_by(email=email.data).first():
            raise ValidationError("Email already registered.")


class LoginForm(FlaskForm):
    email = StringField(
        "Email",
        validators=[DataRequired(), Email()],
        render_kw={"autocomplete": "username"},
    )
    password = PasswordField(
        "Password",
        validators=[DataRequired()],
        render_kw={"autocomplete": "current-password"},
    )
    submit = SubmitField("Login")


class PostForm(FlaskForm):
    title = StringField(
        "Title",
        validators=[DataRequired(), Length(max=140)],
        render_kw={"autocomplete": "off"},
    )
    body = TextAreaField("Content", validators=[DataRequired()], render_kw={"rows": 8})
    submit = SubmitField("Publish")


class CommentForm(FlaskForm):
    body = TextAreaField(
        "Comment", validators=[DataRequired()], render_kw={"rows": 4}
    )
    submit = SubmitField("Post