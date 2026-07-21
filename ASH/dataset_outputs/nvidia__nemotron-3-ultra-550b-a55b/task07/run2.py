"""
Blog CMS Module

A self-contained blog content management system with user authentication,
post management, comments, categories, and tags. Built with Flask and
standard extensions following security best practices.
"""

from __future__ import annotations

import os
import secrets
from datetime import datetime
from functools import wraps
from typing import Any, Callable, List, Optional, Tuple, TypeVar, Union

from flask import (
    Flask,
    abort,
    flash,
    redirect,
    render_template_string,
    request,
    session,
    url_for,
)
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager,
    UserMixin,
    current_user,
    login_required,
    login_user,
    logout_user,
)
from werkzeug.security import check_password_hash, generate_password_hash
from wtforms import (
    BooleanField,
    HiddenField,
    PasswordField,
    SelectMultipleField,
    StringField,
    SubmitField,
    TextAreaField,
    ValidationError,
)
from wtforms.validators import DataRequired, Email, EqualTo, Length, Optional as OptionalValidator
from flask_wtf import FlaskForm
from flask_wtf.csrf import CSRFProtect, generate_csrf

# Type aliases
T = TypeVar("T", bound=Callable[..., Any])
RouteResponse = Union[str, Tuple[str, int]]

# Configuration
class Config:
    """Application configuration with security-focused defaults."""
    SECRET_KEY: str = os.environ.get("SECRET_KEY", secrets.token_hex(32))
    SQLALCHEMY_DATABASE_URI: str = os.environ.get("DATABASE_URL", "sqlite:///blog.db")
    SQLALCHEMY_TRACK_MODIFICATIONS: bool = False
    WTF_CSRF_ENABLED: bool = True
    SESSION_COOKIE_HTTPONLY: bool = True
    SESSION_COOKIE_SECURE: bool = os.environ.get("FLASK_ENV") == "production"
    SESSION_COOKIE_SAMESITE: str = "Lax"
    PERMANENT_SESSION_LIFETIME: int = 3600  # 1 hour

# Initialize extensions
app = Flask(__name__)
app.config.from_object(Config)
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message_category = "warning"
csrf = CSRFProtect(app)

# =============================================================================
# Database Models
# =============================================================================

class User(UserMixin, db.Model):
    """User model with secure password handling."""
    __tablename__ = "users"
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    posts = db.relationship("Post", backref="author", lazy="dynamic")
    comments = db.relationship("Comment", backref="author", lazy="dynamic")

    def set_password(self, password: str) -> None:
        """Hash and set password using PBKDF2 with SHA-256."""
        self.password_hash = generate_password_hash(password, method="pbkdf2:sha256:260000", salt_length=16)

    def check_password(self, password: str) -> bool:
        """Verify password against stored hash."""
        return check_password_hash(self.password_hash, password)

    def __repr__(self) -> str:
        return f"<User {self.username}>"


class Category(db.Model):
    """Post category model."""
    __tablename__ = "categories"
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False, index=True)
    slug = db.Column(db.String(50), unique=True, nullable=False, index=True)
    description = db.Column(db.Text, nullable=True)
    posts = db.relationship("Post", backref="category", lazy="dynamic")

    def __repr__(self) -> str:
        return f"<Category {self.name}>"


class Tag(db.Model):
    """Post tag model."""
    __tablename__ = "tags"
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False, index=True)
    slug = db.Column(db.String(50), unique=True, nullable=False, index=True)
    posts = db.relationship("Post", secondary="post_tags", backref="tags", lazy="dynamic")

    def __repr__(self) -> str:
        return f"<Tag {self.name}>"


post_tags = db.Table(
    "post_tags",
    db.Column("post_id", db.Integer, db.ForeignKey("posts.id"), primary_key=True),
    db.Column("tag_id", db.Integer, db.ForeignKey("tags.id"), primary_key=True),
)


class Post(db.Model):
    """Blog post model with content, metadata, and relationships."""
    __tablename__ = "posts"
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False, index=True)
    slug = db.Column(db.String(200), unique=True, nullable=False, index=True)
    content = db.Column(db.Text, nullable=False)
    excerpt = db.Column(db.Text, nullable=True)
    is_published = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"), nullable=True)
    comments = db.relationship("Comment", backref="post", lazy="dynamic", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Post {self.title}>"


class Comment(db.Model):
    """Comment model for post discussions."""
    __tablename__ = "comments"
    
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    is_approved = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey("posts.id"), nullable=False)

    def __repr__(self) -> str:
        return f"<Comment {self.id} on Post {self.post_id}>"

# =============================================================================
# Forms
# =============================================================================

class RegistrationForm(FlaskForm):
    """User registration form with validation."""
    username = StringField(
        "Username",
        validators=[DataRequired(), Length(min=3, max=80)],
        render_kw={"autocomplete": "username"}
    )
    email = StringField(
        "Email",
        validators=[DataRequired(), Email(), Length(max=120)],
        render_kw={"autocomplete": "email"}
    )
    password = PasswordField(
        "Password",
        validators=[DataRequired(), Length(min=12, max=128)],
        render_kw={"autocomplete": "new-password"}
    )
    confirm_password = PasswordField(
        "Confirm Password",
        validators=[DataRequired(), EqualTo("password")],
        render_kw={"autocomplete": "new-password"}
    )
    submit = SubmitField("Register")

    def validate_username(self, field: StringField) -> None:
        """Ensure username is unique."""
        if User.query.filter_by(username=field.data).first():
            raise ValidationError("Username already taken.")

    def validate_email(self, field: StringField) -> None:
        """Ensure email is unique."""
        if User.query.filter_by(email=field.data).first():
            raise ValidationError("Email already registered.")


class LoginForm(FlaskForm):
    """User login form."""
    username = StringField(
        "Username",
        validators=[DataRequired(), Length(max=80)],
        render_kw={"autocomplete": "username"}
    )
    password = PasswordField(
        "Password",
        validators=[DataRequired()],
        render_kw={"autocomplete": "current-password"}
    )
    remember = BooleanField("Remember Me")
    submit = SubmitField("Login")


class PostForm(FlaskForm):
    """Post creation/editing form."""
    title = StringField("Title", validators=[DataRequired(), Length(max=200)])
    content = TextAreaField("Content", validators=[DataRequired()])
    excerpt = TextAreaField("Excerpt", validators=[OptionalValidator(), Length(max=500)])
    is_published = BooleanField("Published")
    category_id = SelectMultipleField("Category", coerce=int, validators=[OptionalValidator()])
    tags = StringField("Tags (comma-separated)", validators=[OptionalValidator(), Length(max=500)])
    submit = SubmitField("Save Post")


class CommentForm(FlaskForm):
    """Comment submission form."""
    content = TextAreaField("Comment", validators=[DataRequired(), Length(max=5000)])
    post_id = HiddenField("Post ID", validators=[DataRequired()])
    submit = SubmitField("Post Comment")


class DeleteForm(FlaskForm):
    """Generic deletion confirmation form."""
    submit = SubmitField("Delete")

# =============================================================================
# Helper Functions & Decorators
# =============================================================================

def admin_required(func: T) -> T:
    """Decorator to restrict access to admin users."""
    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> RouteResponse:
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403, description="Admin privileges required.")
        return func(*args, **kwargs)
    return wrapper  # type: ignore


def author_or_admin_required(model: db.Model, id_param: str = "id") -> Callable[[T], T]:
    """Decorator to restrict access to resource author or admin."""
    def decorator(func: T) -> T:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> RouteResponse:
            resource_id = kwargs.get(id_param)
            if not resource_id:
                abort(400, description="Resource ID missing.")
            resource = model.query.get_or_404(resource_id)
            if not current_user.is_authenticated or (
                resource.author_id != current_user.id and not current_user.is_admin
            ):
                abort(403, description="You do not have permission to modify this resource.")
            return func(*args, **kwargs)
        return wrapper  # type: ignore
    return decorator


def slugify(text: str) -> str:
    """Generate URL-friendly slug from text."""
    import re
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text[:200]


def get_or_create_tags(tag_names: List[str]) -> List[Tag]:
    """Retrieve existing tags or create new ones."""
    tags = []
    for name in tag_names:
        name = name.strip()
        if not name:
            continue
        slug = slugify(name)
        tag = Tag.query.filter_by(slug=slug).first()
        if not tag:
            tag = Tag(name=name, slug=slug)
            db.session.add(tag)
        tags.append(tag)
    return tags


@login_manager.user_loader
def load_user(user_id: str) -> Optional[User]:
    """Load user by ID for Flask-Login."""
    return User.query.get(int(user_id))

# =============================================================================
# Template Strings (Inline for Self-Containment)
# =============================================================================

BASE_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}Blog CMS{% endblock %}</title>
    <style>
        body { font-family: system-ui, sans-serif; max-width: 800px; margin: 0 auto; padding: 1rem; }
        .flash { padding: 1rem; margin: 1rem 0; border-radius: 4px; }
        .flash.success { background: #d4edda; color: #155724; }
        .flash.error { background: #f8d7da; color: #721c24; }
        .flash.warning { background: #fff3cd; color: #856404; }
        form { display: flex; flex-direction: column; gap: 1rem; max-width: 600px; }
        label { font-weight: bold; }
        input, textarea, select { padding: 0.5rem; font-size: 1rem; }
        button, .btn { padding: 0.75rem 1.5rem; background: #007bff; color: white; border: none; border-radius: 4px; cursor: pointer; text-decoration: none; display: inline-block; }
        button:hover, .btn:hover { background: #0056b3; }
        .btn-danger { background: #dc3545; }
        .btn-danger:hover { background: #c82333; }
        .post { border: 1px solid #ddd; border-radius: 4px; padding: 1.5rem; margin: 1rem 0; }
        .post h2 { margin-top: 0; }
        .meta { color: #666; font-size: 0.9rem; margin-bottom: 1rem; }
        .comment { border-left: 3px solid #007bff; padding-left: 1rem; margin: 1rem 0; }
        nav { margin-bottom: 2rem; padding-bottom: 1rem; border-bottom: 1px solid #eee; }
        nav a { margin-right: 1rem; }
    </style>
</head>
<body>