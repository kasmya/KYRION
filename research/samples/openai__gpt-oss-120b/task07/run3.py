"""
blog_cms.py

A minimal, self‑contained blog content management system (CMS) built with Flask.
Features:
- User registration, login, logout with password hashing (passlib).
- CRUD operations for blog posts.
- Post categorisation via categories and tags.
- Comment system attached to posts.
- Simple token‑based authentication for API endpoints.
- SQLite database via SQLAlchemy.

Only the Python standard library and the following widely‑used PyPI packages are used:
Flask, Flask_SQLAlchemy, passlib, itsdangerous.
"""

from __future__ import annotations

import datetime as _dt
import os as _os
from typing import Any, Dict, List, Optional, Tuple

from flask import (
    Flask,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_sqlalchemy import SQLAlchemy
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from passlib.context import CryptContext

# --------------------------------------------------------------------------- #
# Configuration & Initialization
# --------------------------------------------------------------------------- #

app: Flask = Flask(__name__)
app.config["SECRET_KEY"] = _os.getenv("FLASK_SECRET_KEY", "change-me-in-production")
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///blog_cms.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db: SQLAlchemy = SQLAlchemy(app)

pwd_context: CryptContext = CryptContext(schemes=["bcrypt"], deprecated="auto")
serializer: URLSafeTimedSerializer = URLSafeTimedSerializer(app.config["SECRET_KEY"])

# --------------------------------------------------------------------------- #
# Database Models
# --------------------------------------------------------------------------- #

post_tags = db.Table(
    "post_tags",
    db.Column("post_id", db.Integer, db.ForeignKey("post.id"), primary_key=True),
    db.Column("tag_id", db.Integer, db.ForeignKey("tag.id"), primary_key=True),
)


class User(db.Model):
    """Application user."""

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(
        db.DateTime, default=_dt.datetime.utcnow, nullable=False
    )

    posts = db.relationship("Post", backref="author", lazy="dynamic")
    comments = db.relationship("Comment", backref="author", lazy="dynamic")

    def verify_password(self, password: str) -> bool:
        """Return True if *password* matches stored hash."""
        return pwd_context.verify(password, self.password_hash)

    @staticmethod
    def hash_password(password: str) -> str:
        """Return a hashed representation of *password*."""
        return pwd_context.hash(password)


class Category(db.Model):
    """Post category."""

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)

    posts = db.relationship("Post", backref="category", lazy="dynamic")


class Tag(db.Model):
    """Tag used to label posts."""

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(30), unique=True, nullable=False)


class Post(db.Model):
    """Blog post."""

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(
        db.DateTime, default=_dt.datetime.utcnow, nullable=False
    )
    updated_at = db.Column(
        db.DateTime,
        default=_dt.datetime.utcnow,
        onupdate=_dt.datetime.utcnow,
        nullable=False,
    )
    author_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey("category.id"), nullable=True)

    tags = db.relationship(
        "Tag", secondary=post_tags, lazy="subquery", backref=db.backref("posts", lazy=True)
    )
    comments = db.relationship("Comment", backref="post", lazy="dynamic")


class Comment(db.Model):
    """Comment attached to a post."""

    id = db.Column(db.Integer, primary_key=True)
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(
        db.DateTime, default=_dt.datetime.utcnow, nullable=False
    )
    author_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey("post.id"), nullable=False)


# --------------------------------------------------------------------------- #
# Helper Functions
# --------------------------------------------------------------------------- #

def _get_user_from_session() -> Optional[User]:
    """Return the logged‑in user based on session data, or None."""
    user_id = session.get("user_id")
    if not user_id:
        return None
    return User.query.get(user_id)


def login_required(func):
    """Decorator that aborts with 401 if the user is not authenticated."""

    def wrapper(*args, **kwargs):
        if _get_user_from_session() is None:
            abort(401, description="Authentication required")
        return func(*args, **kwargs)

    wrapper.__name__ = func.__name__
    return wrapper


def generate_auth_token(user_id: int, expires_sec: int = 3600) -> str:
    """Create a timed authentication token for *user_id*."""
    return serializer.dumps({"uid": user_id})


def verify_auth_token(token: str, max_age: int = 3600) -> Optional[int]:
    """Validate *token* and return the user id if valid, otherwise None."""
    try:
        data = serializer.loads(token, max_age=max_age)
        return int(data["uid"])
    except (BadSignature, SignatureExpired, KeyError, ValueError):
        return None


# --------------------------------------------------------------------------- #
# Routes – User Authentication
# --------------------------------------------------------------------------- #

@app.route("/register", methods=["GET", "POST"])
def register() -> Any:
    """
    Register a new user.
    GET returns a simple HTML form; POST processes registration.
    """
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if not username or not password:
            flash("Username and password are required.", "danger")
            return redirect(url_for("register"))

        if User.query.filter_by(username=username).first():
            flash("Username already taken.", "danger")
            return redirect(url_for("register"))

        user = User(
            username=username,
            password_hash=User.hash_password(password),
        )
        try:
            db.session.add(user)
            db.session.commit()
            flash("Registration successful. Please log in.", "success")
            return redirect(url_for("login"))
        except Exception as e:
            db.session.rollback()
            flash(f"Database error: {e}", "danger")
            return redirect(url_for("register"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login() -> Any:
    """
    Log in a user.
    GET returns a simple HTML form; POST validates credentials.
    """
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = User.query.filter_by(username=username).first()
        if user and user.verify_password(password):
            session.clear()
            session["user_id"] = user.id
            flash("Logged in successfully.", "success")
            return redirect(url_for("list_posts"))
        flash("Invalid credentials.", "danger")
        return redirect(url_for("login"))
    return render_template("login.html")


@app.route("/logout")
def logout() -> Any:
    """Log out the current user."""
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("list_posts"))


# --------------------------------------------------------------------------- #
# Routes – Post Management
# --------------------------------------------------------------------------- #

@app.route("/")
def list_posts() -> Any:
    """
    List recent posts.
    Returns JSON if the request prefers JSON, otherwise renders HTML.
    """
    posts = Post.query.order_by(Post.created_at.desc()).limit(20).all()
    if request.accept_mimetypes.best == "application/json":
        return jsonify([_post_to_dict(p) for p in posts])
    return render_template("posts.html", posts=posts)


@app.route("/post/<int:post_id>")
def get_post(post_id: int) -> Any:
    """
    Retrieve a single post by *post_id*.
    Returns JSON for API calls, else renders HTML.
    """
    post = Post.query.get_or_404(post_id)
    if request.accept_mimetypes.best == "application/json":
        return jsonify(_post_to_dict(post, include_comments=True))
    return render_template("post_detail.html", post=post)


@app.route("/post/create", methods=["GET", "POST"])
@login_required
def create_post() -> Any:
    """
    Create a new blog post. Requires authentication.
    GET returns a form; POST creates the post.
    """
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        body = request.form.get("body", "").strip()
        category_name = request.form.get("category", "").strip()
        tag_names = request.form.get("tags", "").split(",")

        if not title or not body:
            flash("Title and body are required.", "danger")
            return redirect(url_for("create_post"))

        user = _get_user_from_session()
        assert user is not None  # guaranteed by login_required

        category = None
        if category_name:
            category = Category.query.filter_by(name=category_name).first()
            if not category:
                category = Category(name=category_name)
                db.session.add(category)

        tags = []
        for name in tag_names:
            clean_name = name.strip()
            if not clean_name:
                continue
            tag = Tag.query.filter_by(name=clean_name).first()
            if not tag:
                tag = Tag(name=clean_name)
                db.session.add(tag)
            tags.append(tag)

        post = Post(
            title=title,
            body=body,
            author=user,
            category=category,
            tags=tags,
        )
        try:
            db.session.add(post)
            db.session.commit()
            flash("Post created.", "success")
            return redirect(url_for("get_post", post_id=post.id))
        except Exception as e:
            db.session.rollback()
            flash(f"Error creating post: {e}", "danger")
            return redirect(url_for("create_post"))

    categories = Category.query.all()
    tags = Tag.query.all()
    return render_template("post_form.html", categories=categories, tags=tags)


@app.route("/post/<int:post_id>/edit", methods=["GET", "POST"])
@login_required
def edit_post(post_id: int) -> Any:
    """
    Edit an existing post. Only the author may edit.
    GET returns a pre‑filled form; POST updates the post.
    """
    post = Post.query.get_or_404(post_id)
    user = _get_user_from_session()
    if post.author != user:
        abort(403, description="You do not have permission to edit this post.")

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        body = request.form.get("body", "").strip()
        category_name = request.form.get("category", "").strip()
        tag_names = request.form.get("tags", "").split(",")

        if not title or not body:
            flash("Title and body are required.", "danger")
            return redirect(url_for("edit_post", post_id=post_id))

        post.title = title
        post.body = body

        if category_name:
            category = Category.query.filter_by(name=category_name).first()
            if not category:
                category = Category(name=category_name)
                db.session.add(category)
            post.category = category
        else:
            post.category = None

        new_tags = []
        for name in tag_names:
            clean = name.strip()
            if not clean:
                continue
            tag = Tag.query.filter_by(name=clean).first()
            if not tag:
                tag = Tag(name=clean)
                db.session.add(tag)
            new_tags.append(tag)
        post.tags = new_tags

        try:
            db.session.commit()
            flash("Post updated.", "success")
            return redirect(url_for("get_post", post_id=post.id))
        except Exception as e:
            db.session.rollback()
            flash(f"Error updating post: {e}", "danger")
            return redirect(url_for("edit_post", post_id=post.id))

    categories = Category.query.all()
    tags = Tag.query.all()
    return render_template(
        "post_form.html",
        post=post,
        categories=categories,
        tags=tags,
        edit_mode=True,
    )


@app.route("/post/<int:post_id>/delete", methods=["POST"])
@login_required
def delete_post(post_id: int) -> Any:
    """
    Delete a post. Only the author may delete.
    """
    post = Post.query.get_or_404(post_id)
    user = _get_user_from_session()
    if post.author != user:
        abort(403, description="You do not have permission to delete this post.")

    try:
        db.session.delete(post)
        db.session.commit()
        flash("Post deleted.", "info")
        return redirect(url_for("list_posts"))
    except Exception as e:
        db.session.rollback()
        flash(f"Error deleting post: {e}", "danger")
        return redirect(url_for("get_post", post_id=post_id))


# --------------------------------------------------------------------------- #
# Routes – Comment System
# --------------------------------------------------------------------------- #

@app.route("/post/<int:post_id>/comment", methods=["POST"])
@login_required
def add_comment(post_id: int) -> Any:
    """
    Add a comment to a post. Requires authentication.
    """
    post = Post.query.get_or_404(post_id)
    body = request.form.get("body", "").strip()
    if not body:
        flash("Comment body cannot be empty.", "danger")
        return redirect(url_for("get_post", post_id=post_id))

    user = _get_user_from_session()
    comment = Comment(body=body, author=user, post=post)

    try:
        db.session.add(comment)
        db.session.commit()
        flash("Comment added.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Failed to add comment: {e}", "danger")
    return redirect(url_for("get_post", post_id=post_id))


# --------------------------------------------------------------------------- #
# Utility Functions
# --------------------------------------------------------------------------- #

def _post_to_dict(post: Post, include_comments: bool = False) -> Dict[str, Any]:
    """
    Serialize a Post instance to a plain dict suitable for JSON responses.
    """
    data: Dict[str, Any] = {
        "id": post.id,
        "title": post.title,
        "body": post.body,
        "author": post.author.username,
        "created_at": post.created_at.isoformat(),
        "updated_at": post.updated_at.isoformat(),
        "category": post.category.name if post.category else None,
        "tags": [tag.name for tag in post.tags],
    }
    if include_comments:
        data["comments"] = [
            {
                "id": c.id,
                "author": c.author.username,
                "body": c.body,
                "created_at": c.created_at.isoformat(),
            }
            for c in post.comments.order_by(Comment.created_at.asc()).all()
        ]
    return data


# --------------------------------------------------------------------------- #
# Error Handlers
# --------------------------------------------------------------------------- #

@app.errorhandler(400)
def bad_request(error: Exception) -> Tuple[Dict[str, str], int]:
    """Return JSON for 400 errors."""
    return jsonify({"error": "Bad request", "message": str(error)}), 400


@app.errorhandler(401)
def unauthorized(error: Exception) -> Tuple[Dict[str, str], int]:
    """Return JSON for 401 errors."""
    return jsonify({"error": "Unauthorized", "message": str(error)}), 401


@app.errorhandler(403)
def forbidden(error: Exception) -> Tuple[Dict[str, str], int]:
    """Return JSON for 403 errors."""
    return jsonify({"error": "Forbidden", "message": str(error)}), 403


@app.errorhandler(404)
def not_found(error: Exception) -> Tuple[Dict[str, str], int]:
    """Return JSON for 404 errors."""
    return jsonify({"error": "Not found", "message": str(error)}), 404


@app.errorhandler(500)
def internal_error(error: Exception) -> Tuple[Dict[str, str], int]:
    """Return JSON for 500 errors."""
    return jsonify({"error": "Internal server error", "message": str(error)}), 500


# --------------------------------------------------------------------------- #
# Command‑Line Helper
# --------------------------------------------------------------------------- #

def _init_db() -> None:
    """Create database tables if they do not exist."""
    db.create_all()
    print("Database initialized.")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run the Blog CMS.")
    parser.add_argument(
        "--init-db",
        action="store_true",
        help="Initialize the SQLite database and exit.",
    )
    args = parser.parse_args()

    if args.init_db:
        with app.app_context():
            _init_db()
    else:
        app.run(debug=True)