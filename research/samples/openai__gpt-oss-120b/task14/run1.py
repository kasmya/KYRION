"""
forum_app.py - A minimal Flask forum / discussion board.

Features:
- User registration & login (password hashing, CSRF protection)
- Create / edit / delete posts
- Comment on posts
- Upvote / downvote posts
- Full‑text search on posts
- Error handling & security best practices
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any, List, Optional

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
from sqlalchemy import func
from werkzeug.security import check_password_hash, generate_password_hash
from wtforms import (
    BooleanField,
    PasswordField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.validators import DataRequired, Length, ValidationError

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #

class Config:
    """Flask application configuration."""
    SECRET_KEY: str = os.getenv("FLASK_SECRET_KEY", "change-me-in-production")
    SQLALCHEMY_DATABASE_URI: str = os.getenv(
        "DATABASE_URL", "sqlite:///forum.db"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS: bool = False
    # Flask‑WTF will use this for CSRF token
    WTF_CSRF_ENABLED: bool = True


# --------------------------------------------------------------------------- #
# Application factory
# --------------------------------------------------------------------------- #

def create_app() -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__)
    app.config.from_object(Config)

    # Extensions
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)

    # Register CLI command to initialise the DB
    @app.cli.command("init-db")
    def init_db() -> None:
        """Create database tables."""
        with app.app_context():
            db.drop_all()
            db.create_all()
            click.echo("Initialized the database.")

    # Context processor to expose current_user in templates
    @app.context_processor
    def inject_user():
        return dict(current_user=current_user)

    # Register routes
    register_routes(app)

    # Error handlers
    @app.errorhandler(404)
    def not_found(error: Any):
        return render_template("404.html"), 404

    @app.errorhandler(403)
    def forbidden(error: Any):
        return render_template("403.html"), 403

    @app.errorhandler(500)
    def internal_error(error: Any):
        return render_template("500.html"), 500

    return app


# --------------------------------------------------------------------------- #
# Extensions (initialized later)
# --------------------------------------------------------------------------- #

db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = "login"
csrf = CSRFProtect()


# --------------------------------------------------------------------------- #
# Database models
# --------------------------------------------------------------------------- #

class User(UserMixin, db.Model):
    """User model."""

    __tablename__ = "users"

    id: int = db.Column(db.Integer, primary_key=True)
    username: str = db.Column(db.String(80), unique=True, nullable=False)
    password_hash: str = db.Column(db.String(128), nullable=False)
    created_at: datetime = db.Column(
        db.DateTime, default=datetime.utcnow, nullable=False
    )
    posts: List["Post"] = db.relationship(
        "Post", backref="author", cascade="all, delete-orphan", lazy="dynamic"
    )
    comments: List["Comment"] = db.relationship(
        "Comment", backref="author", cascade="all, delete-orphan", lazy="dynamic"
    )
    votes: List["Vote"] = db.relationship(
        "Vote", backref="voter", cascade="all, delete-orphan", lazy="dynamic"
    )

    def set_password(self, password: str) -> None:
        """Hash and store a password."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        """Check a hashed password."""
        return check_password_hash(self.password_hash, password)

    def __repr__(self) -> str:
        return f"<User {self.username}>"


class Post(db.Model):
    """Forum post."""

    __tablename__ = "posts"

    id: int = db.Column(db.Integer, primary_key=True)
    title: str = db.Column(db.String(200), nullable=False)
    body: str = db.Column(db.Text, nullable=False)
    created_at: datetime = db.Column(
        db.DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: datetime = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
    user_id: int = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    comments: List["Comment"] = db.relationship(
        "Comment", backref="post", cascade="all, delete-orphan", lazy="dynamic"
    )
    votes: List["Vote"] = db.relationship(
        "Vote", backref="post", cascade="all, delete-orphan", lazy="dynamic"
    )

    @property
    def score(self) -> int:
        """Calculate net upvotes - downvotes."""
        up = sum(v.value for v in self.votes if v.value == 1)
        down = sum(v.value for v in self.votes if v.value == -1)
        return up + down

    def __repr__(self) -> str:
        return f"<Post {self.title!r}>"


class Comment(db.Model):
    """Comment on a post."""

    __tablename__ = "comments"

    id: int = db.Column(db.Integer, primary_key=True)
    body: str = db.Column(db.Text, nullable=False)
    created_at: datetime = db.Column(
        db.DateTime, default=datetime.utcnow, nullable=False
    )
    user_id: int = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    post_id: int = db.Column(db.Integer, db.ForeignKey("posts.id"), nullable=False)

    def __repr__(self) -> str:
        return f"<Comment {self.id} on Post {self.post_id}>"


class Vote(db.Model):
    """Upvote / downvote on a post."""

    __tablename__ = "votes"

    id: int = db.Column(db.Integer, primary_key=True)
    value: int = db.Column(db.Integer, nullable=False)  # 1 for upvote, -1 for downvote
    user_id: int = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    post_id: int = db.Column(db.Integer, db.ForeignKey("posts.id"), nullable=False)

    __table_args__ = (
        db.UniqueConstraint("user_id", "post_id", name="uq_user_post_vote"),
    )

    def __repr__(self) -> str:
        direction = "up" if self.value == 1 else "down"
        return f"<Vote {direction} by User {self.user_id} on Post {self.post_id}>"


# --------------------------------------------------------------------------- #
# Login manager user loader
# --------------------------------------------------------------------------- #

@login_manager.user_loader
def load_user(user_id: str) -> Optional[User]:
    return User.query.get(int(user_id))


# --------------------------------------------------------------------------- #
# Forms
# --------------------------------------------------------------------------- #

class RegistrationForm(FlaskForm):
    """User registration form."""

    username = StringField(
        "Username",
        validators=[DataRequired(), Length(min=3, max=25)],
        render_kw={"autofocus": True},
    )
    password = PasswordField(
        "Password", validators=[DataRequired(), Length(min=6, max=128)]
    )
    submit = SubmitField("Register")

    def validate_username(self, field: StringField) -> None:
        if User.query.filter_by(username=field.data).first():
            raise ValidationError("Username already taken.")


class LoginForm(FlaskForm):
    """User login