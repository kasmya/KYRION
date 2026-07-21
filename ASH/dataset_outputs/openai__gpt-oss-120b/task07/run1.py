"""
blog_cms.py
A minimal blog content management system (CMS) implemented as a Flask web application.
Provides:
- User registration, login, logout with secure password hashing.
- CRUD operations for blog posts.
- Comment creation and retrieval.
- Post categories and tags management.
- JSON‑based API with proper error handling and security best practices.

Only standard library modules and widely‑used PyPI packages are used:
Flask, Flask‑SQLAlchemy, Flask‑Login, Werkzeug.
"""

from __future__ import annotations

import datetime as _dt
from typing import Any, Dict, List, Optional

from flask import (
    Flask,
    abort,
    jsonify,
    request,
    session,
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

# --------------------------------------------------------------------------- #
# Flask application and extensions configuration
# --------------------------------------------------------------------------- #

app: Flask = Flask(__name__)
app.config["SECRET_KEY"] = "replace-this-with-a-random-secret-key"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///blog_cms.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db: SQLAlchemy = SQLAlchemy(app)
login_manager: LoginManager = LoginManager(app)
login_manager.login_view = "login"


# --------------------------------------------------------------------------- #
# Database models
# --------------------------------------------------------------------------- #

post_tags = db.Table(
    "post_tags",
    db.Column("post_id", db.Integer, db.ForeignKey("post.id"), primary_key=True),
    db.Column("tag_id", db.Integer, db.ForeignKey("tag.id"), primary_key=True),
)


class User(UserMixin, db.Model):
    """Application user."""

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(128), nullable=False)

    posts = db.relationship("Post", backref="author", lazy="dynamic")
    comments = db.relationship("Comment", backref="author", lazy="dynamic")

    def set_password(self, password: str) -> None:
        """Hash and store a new password."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        """Validate a password against the stored hash."""
        return check_password_hash(self.password_hash, password)


class Category(db.Model):
    """Post category."""

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)

    posts = db.relationship("Post", backref="category", lazy="dynamic")


class Tag(db.Model):
    """Post tag."""

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(30), unique=True, nullable=False)

    posts = db.relationship(
        "Post", secondary=post_tags, back_populates="tags", lazy="dynamic"
    )


class Post(db.Model):
    """Blog post."""

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=_dt.datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime, default=_dt.datetime.utcnow, onupdate=_dt.datetime.utcnow
    )
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey("category.id"), nullable=True)

    tags = db.relationship(
        "Tag", secondary=post_tags, back_populates="posts", lazy="dynamic"
    )
    comments = db.relationship("Comment", backref="post", lazy="dynamic")


class Comment(db.Model):
    """Comment on a post."""

    id = db.Column(db.Integer, primary_key=True)
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=_dt.datetime.utcnow, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey("post.id"), nullable=False)


# --------------------------------------------------------------------------- #
# Flask‑Login user loader
# --------------------------------------------------------------------------- #


@login_manager.user_loader
def load_user(user_id: str) -> Optional[User]:
    """Load a user given the primary key."""
    return User.query.get(int(user_id))


# --------------------------------------------------------------------------- #
# Helper utilities
# --------------------------------------------------------------------------- #


def _json_error(message: str, status_code: int) -> Any:
    """Return a JSON error response with a given HTTP status code."""
    response = jsonify({"error": message})
    response.status_code = status_code
    return response


def _get_or_404(model: db.Model, object_id: int) -> db.Model:
    """Retrieve an object by ID or abort with 404."""
    instance = model.query.get(object_id)
    if instance is None:
        abort(404, description=f"{model.__name__} not found")
    return instance


def _parse_tags(tag_names: List[str]) -> List[Tag]:
    """Return Tag objects for a list of names, creating missing tags."""
    tags: List[Tag] = []
    for name in tag_names:
        name = name.strip().lower()
        if not name:
            continue
        tag = Tag.query.filter_by(name=name).first()
        if tag is None:
            tag = Tag(name=name)
            db.session.add(tag)
        tags.append(tag)
    return tags


# --------------------------------------------------------------------------- #
# Authentication routes
# --------------------------------------------------------------------------- #


@app.route("/api/register", methods=["POST"])
def register() -> Any:
    """
    Register a new user.

    Expected JSON payload:
    {
        "username": "<str>",
        "password": "<str>"
    }
    """
    data = request.get_json(silent=True) or {}
    username = data.get("username", "").strip()
    password = data.get("password", "")

    if not username or not password:
        return _json_error("Username and password are required", 400)

    if User.query.filter_by(username=username).first():
        return _json_error("Username already taken", 400)

    try:
        user = User(username=username)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        return jsonify({"message": "User registered"}), 201
    except Exception as exc:
        db.session.rollback()
        return _json_error(f"Registration failed: {exc}", 500)


@app.route("/api/login", methods=["POST"])
def login() -> Any:
    """
    Log a user in.

    Expected JSON payload:
    {
        "username": "<str>",
        "password": "<str>"
    }
    """
    data = request.get_json(silent=True) or {}
    username = data.get("username", "").strip()
    password = data.get("password", "")

    if not username or not password:
        return _json_error("Username and password are required", 400)

    user = User.query.filter_by(username=username).first()
    if user is None or not user.check_password(password):
        return _json_error("Invalid credentials", 401)

    login_user(user)
    return jsonify({"message": "Logged in"}), 200


@app.route("/api/logout", methods=["POST"])
@login_required
def logout() -> Any:
    """Log the current user out."""
    logout_user()
    return jsonify({"message": "Logged out"}), 200


# --------------------------------------------------------------------------- #
# Post CRUD routes
# --------------------------------------------------------------------------- #


@app.route("/api/posts", methods=["POST"])
@login_required
def create_post() -> Any:
    """
    Create a new post.

    Expected JSON payload:
    {
        "title": "<str>",
        "body": "<str>",
        "category": "<category name>",          # optional
        "tags": ["tag1", "tag2"]                # optional
    }
    """
    data = request.get_json(silent=True) or {}
    title = data.get("title", "").strip()
    body = data.get("body", "").strip()
    category_name = data.get("category", "").strip()
    tag_names = data.get("tags", [])

    if not title or not body:
        return _json_error("Title and body are required", 400)

    try:
        post = Post(title=title, body=body, author=current_user)

        if category_name:
            category = Category.query.filter_by(name=category_name).first()
            if category is None:
                category = Category(name=category_name)
                db.session.add(category)
            post.category = category

        if isinstance(tag_names, list):
            tags = _parse_tags(tag_names)
            post.tags.extend(tags)

        db.session.add(post)
        db.session.commit()
        return jsonify({"id": post.id, "message": "Post created"}), 201
    except Exception as exc:
        db.session.rollback()
        return _json_error(f"Failed to create post: {exc}", 500)


@app.route("/api/posts/<int:post_id>", methods=["GET"])
def get_post(post_id: int) -> Any:
    """Retrieve a post by its ID, including tags and comments."""
    post = _get_or_404(Post, post_id)
    post_data = {
        "id": post.id,
        "title": post.title,
        "body": post.body,
        "author": post.author.username,
        "created_at": post.created_at.isoformat(),
        "updated_at": post.updated_at.isoformat(),
        "category": post.category.name if post.category else None,
        "tags": [tag.name for tag in post.tags],
        "comments": [
            {
                "id": c.id,
                "author": c.author.username,
                "body": c.body,
                "created_at": c.created_at.isoformat(),
            }
            for c in post.comments.order_by(Comment.created_at.asc())
        ],
    }
    return jsonify(post_data), 200


@app.route("/api/posts/<int:post_id>", methods=["PUT"])
@login_required
def update_post(post_id: int) -> Any:
    """
    Update an existing post.

    Expected JSON payload (any of the fields may be omitted):
    {
        "title": "<str>",
        "body": "<str>",
        "category": "<category name>",
        "tags": ["tag1", "tag2"]
    }
    """
    post = _get_or_404(Post, post_id)

    if post.author != current_user:
        return _json_error("Permission denied", 403)

    data = request.get_json(silent=True) or {}
    title = data.get("title")
    body = data.get("body")
    category_name = data.get("category")
    tag_names = data.get("tags")

    try:
        if isinstance(title, str):
            post.title = title.strip()
        if isinstance(body, str):
            post.body = body.strip()
        if isinstance(category_name, str):
            category_name = category_name.strip()
            if category_name:
                category = Category.query.filter_by(name=category_name).first()
                if category is None:
                    category = Category(name=category_name)
                    db.session.add(category)
                post.category = category
            else:
                post.category = None
        if isinstance(tag_names, list):
            post.tags.clear()
            post.tags.extend(_parse_tags(tag_names))

        db.session.commit()
        return jsonify({"message": "Post updated"}), 200
    except Exception as exc:
        db.session.rollback()
        return _json_error(f"Failed to update post: {exc}", 500)


@app.route("/api/posts/<int:post_id>", methods=["DELETE"])
@login_required
def delete_post(post_id: int) -> Any:
    """Delete a post (and its comments)."""
    post = _get_or_404(Post, post_id)

    if post.author != current_user:
        return _json_error("Permission denied", 403)

    try:
        db.session.delete(post)
        db.session.commit()
        return jsonify({"message": "Post deleted"}), 200
    except Exception as exc:
        db.session.rollback()
        return _json_error(f"Failed to delete post: {exc}", 500)


# --------------------------------------------------------------------------- #
# Comment routes
# --------------------------------------------------------------------------- #


@app.route("/api/posts/<int:post_id>/comments", methods=["POST"])
@login_required
def add_comment(post_id: int) -> Any:
    """
    Add a comment to a post.

    Expected JSON payload:
    {
        "body": "<str>"
    }
    """
    post = _get_or_404(Post, post_id)
    data = request.get_json(silent=True) or {}
    body = data.get("body", "").strip()

    if not body:
        return _json_error("Comment body is required", 400)

    try:
        comment = Comment(body=body, author=current_user, post=post)
        db.session.add(comment)
        db.session.commit()
        return jsonify({"id": comment.id, "message": "Comment added"}), 201
    except Exception as exc:
        db.session.rollback()
        return _json_error(f"Failed to add comment: {exc}", 500)


@app.route("/api/comments/<int:comment_id>", methods=["DELETE"])
@login_required
def delete_comment(comment_id: int) -> Any:
    """Delete a comment (only by its author or post author)."""
    comment = _get_or_404(Comment, comment_id)

    if comment.author != current_user and comment.post.author != current_user:
        return _json_error("Permission denied", 403)

    try:
        db.session.delete(comment)
        db.session.commit()
        return jsonify({"message": "Comment deleted"}), 200
    except Exception as exc:
        db.session.rollback()
        return _json_error(f"Failed to delete comment: {exc}", 500)


# --------------------------------------------------------------------------- #
# Category and tag discovery routes
# --------------------------------------------------------------------------- #


@app.route("/api/categories", methods=["GET"])
def list_categories() -> Any:
    """Return a list of all categories."""
    categories = [{"id": c.id, "name": c.name} for c in Category.query.order_by(Category.name)]
    return jsonify(categories), 200


@app.route("/api/tags", methods=["GET"])
def list_tags() -> Any:
    """Return a list of all tags."""
    tags = [{"id": t.id, "name": t.name} for t in Tag.query.order_by(Tag.name)]
    return jsonify(tags), 200


# --------------------------------------------------------------------------- #
# Global error handlers
# --------------------------------------------------------------------------- #


@app.errorhandler(400)
def handle_400(error: Exception) -> Any:
    return _json_error(str(error), 400)


@app.errorhandler(401)
def handle_401(error: Exception) -> Any:
    return _json_error(str(error), 401)


@app.errorhandler(403)
def handle_403(error: Exception) -> Any:
    return _json_error(str(error), 403)


@app.errorhandler(404)
def handle_404(error: Exception) -> Any:
    return _json_error(str(error), 404)


@app.errorhandler(500)
def handle_500(error: Exception) -> Any:
    return _json_error("Internal server error", 500)


# --------------------------------------------------------------------------- #
# Command‑line utilities
# --------------------------------------------------------------------------- #


def init_db() -> None:
    """Create database tables."""
    with app.app_context():
        db.create_all()


def run_dev_server(host: str = "127.0.0.1", port: int = 5000) -> None:
    """Run the Flask development server."""
    app.run(host=host, port=port, debug=True)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Blog CMS management script")
    parser.add_argument(
        "command",
        choices=["initdb", "runserver"],
        help="Action to perform",
    )
    args = parser.parse_args()

    if args.command == "initdb":
        init_db()
        print("Database initialized.")
    elif args.command == "runserver":
        run_dev_server()