#!/usr/bin/env python3
"""
Flask based authentication system with:
- User registration
- Password hashing using bcrypt
- Session management via Flask secure cookies
- Login / logout endpoints
- Type hints, docstrings and error handling
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

from flask import (
    Flask,
    jsonify,
    request,
    session,
    abort,
    g,
)
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import safe_str_cmp
import bcrypt

# --------------------------------------------------------------------------- #
# Application setup
# --------------------------------------------------------------------------- #

app = Flask(__name__)
# In production load this from a secure source / environment variable
app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY", "change-me-please")
# SQLite for demo; replace with proper DB in production
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///users.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Session cookie security (assumes HTTPS in production)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = False  # Set True when served over HTTPS

db = SQLAlchemy(app)


# --------------------------------------------------------------------------- #
# Database model
# --------------------------------------------------------------------------- #

class User(db.Model):
    """SQLAlchemy model for a registered user."""

    __tablename__ = "users"

    id: int = db.Column(db.Integer, primary_key=True)
    username: str = db.Column(db.String(150), unique=True, nullable=False)
    password_hash: str = db.Column(db.LargeBinary(60), nullable=False)

    def verify_password(self, password: str) -> bool:
        """Check if the provided password matches the stored hash."""
        return bcrypt.checkpw(password.encode("utf-8"), self.password_hash)

    @staticmethod
    def hash_password(password: str) -> bytes:
        """Generate a bcrypt hash for the given password."""
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password.encode("utf-8"), salt)


# --------------------------------------------------------------------------- #
# Helper utilities
# --------------------------------------------------------------------------- #

def get_user_by_username(username: str) -> Optional[User]:
    """Return a user by username or None."""
    return User.query.filter_by(username=username).first()


def login_user(user: User) -> None:
    """Store minimal user info in the session."""
    session.clear()
    session["user_id"] = user.id
    session["username"] = user.username


def logout_user() -> None:
    """Remove user information from the session."""
    session.clear()


def current_user() -> Optional[User]:
    """Retrieve the currently logged‑in user from the session."""
    uid = session.get("user_id")
    if uid is None:
        return None
    return User.query.get(uid)


def login_required(func):
    """View decorator that aborts with 401 when the user is not authenticated."""

    def wrapper(*args: Any, **kwargs: Any):
        if not current_user():
            abort(401, description="Authentication required")
        return func(*args, **kwargs)

    wrapper.__name__ = getattr(func, "__name__", "wrapped")
    return wrapper


# --------------------------------------------------------------------------- #
# Request hooks
# --------------------------------------------------------------------------- #

@app.before_request
def load_current_user() -> None:
    """Make `g.user` available in request context."""
    g.user = current_user()


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #

@app.route("/register", methods=["POST"])
def register() -> Any:
    """
    Register a new user.

    Expected JSON payload:
    {
        "username": "desired_name",
        "password": "plain_text_password"
    }
    """
    data: Dict[str, str] = request.get_json(silent=True) or {}
    username = data.get("username", "").strip()
    password = data.get("password", "")

    # Basic validation
    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400
    if get_user_by_username(username):
        return jsonify({"error": "Username already exists"}), 400
    if len(password) < 8:
        return jsonify({"error": "Password must be at least 8 characters"}), 400

    # Create user
    password_hash = User.hash_password(password)
    new_user = User(username=username, password_hash=password_hash)

    db.session.add(new_user)
    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return jsonify({"error": "Database error"}), 500

    return jsonify({"message": "User registered successfully"}), 201


@app.route("/login", methods=["POST"])
def login() -> Any:
    """
    Authenticate a user.

    Expected JSON payload:
    {
        "username": "existing_name",
        "password": "plain_text_password"
    }
    """
    data: Dict[str, str] = request.get_json(silent=True) or {}
    username = data.get("username", "").strip()
    password = data.get("password", "")

    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400

    user = get_user_by_username(username)
    if not user or not user.verify_password(password):
        # Generic error to avoid username enumeration
        return jsonify({"error": "Invalid credentials"}), 401

    login_user(user)
    return jsonify({"message": f"Welcome, {user.username}!"}), 200


@app.route("/logout", methods=["POST"])
@login_required
def logout() -> Any:
    """Terminate the current session."""
    logout_user()
    return jsonify({"message": "Logged out successfully"}), 200


@app.route("/profile", methods=["GET"])
@login_required
def profile() -> Any:
    """Example protected endpoint."""
    user = g.user
    return jsonify({"id": user.id, "username": user.username}), 200


# --------------------------------------------------------------------------- #
# Error handlers
# --------------------------------------------------------------------------- #

@app.errorhandler(400)
def handle_400(error) -> Any:
    return jsonify({"error": error.description or "Bad request"}), 400


@app.errorhandler(401)
def handle_401(error) -> Any:
    return jsonify({"error": error.description or "Unauthorized"}), 401


@app.errorhandler(404)
def handle_404(error) -> Any:
    return jsonify({"error": "Not found"}), 404


@app.errorhandler(500)
def handle_500(error) -> Any:
    return jsonify({"error": "Internal server error"}), 500


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    # Create DB tables if they don't exist
    with app.app_context():
        db.create_all()
    # In production use a proper WSGI server (Gunicorn / uWSGI) and enable HTTPS
    app.run(host="0.0.0.0", port=5000, debug=False)