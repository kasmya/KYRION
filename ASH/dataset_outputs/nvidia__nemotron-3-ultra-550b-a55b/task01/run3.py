"""
User Authentication Module

This module provides a complete user authentication system including registration,
login, logout, and session management using Flask and bcrypt for password hashing.
It follows security best practices such as secure password hashing, session
management with secure cookies, CSRF protection, and input validation.

Dependencies:
    - flask: Web framework for handling HTTP requests and sessions
    - bcrypt: Password hashing library
    - typing: Standard library for type hints
    - secrets: Standard library for generating secure tokens
    - functools: Standard library for decorators
    - dataclasses: Standard library for data containers
    - threading: Standard library for thread-safe operations
"""

from __future__ import annotations

import secrets
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from functools import wraps
from typing import Any, Callable, Dict, Optional, Tuple

import bcrypt
from flask import (
    Flask,
    Request,
    Response,
    jsonify,
    make_response,
    request,
    session,
)

# Configuration constants
SESSION_COOKIE_NAME = "auth_session"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = False  # Set to True in production with HTTPS
SESSION_COOKIE_SAMESITE = "Lax"
PERMANENT_SESSION_LIFETIME = timedelta(hours=24)
BCRYPT_ROUNDS = 12
CSRF_TOKEN_LENGTH = 32
MAX_USERNAME_LENGTH = 50
MAX_PASSWORD_LENGTH = 128
MIN_PASSWORD_LENGTH = 8

app = Flask(__name__)
app.config.update(
    SECRET_KEY=secrets.token_hex(32),
    SESSION_COOKIE_NAME=SESSION_COOKIE_NAME,
    SESSION_COOKIE_HTTPONLY=SESSION_COOKIE_HTTPONLY,
    SESSION_COOKIE_SECURE=SESSION_COOKIE_SECURE,
    SESSION_COOKIE_SAMESITE=SESSION_COOKIE_SAMESITE,
    PERMANENT_SESSION_LIFETIME=PERMANENT_SESSION_LIFETIME,
)


@dataclass
class User:
    """Represents a user account with securely hashed password."""

    username: str
    password_hash: bytes
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_login: Optional[datetime] = None
    is_active: bool = True

    def verify_password(self, password: str) -> bool:
        """
        Verify a plaintext password against the stored hash.

        Args:
            password: Plaintext password to verify.

        Returns:
            True if password matches, False otherwise.
        """
        try:
            return bcrypt.checkpw(password.encode("utf-8"), self.password_hash)
        except (ValueError, TypeError):
            return False


class UserStore:
    """Thread-safe in-memory user storage with basic operations."""

    def __init__(self) -> None:
        self._users: Dict[str, User] = {}
        self._lock = threading.RLock()

    def add_user(self, username: str, password_hash: bytes) -> Tuple[bool, str]:
        """
        Add a new user to the store.

        Args:
            username: Unique username.
            password_hash: Bcrypt hashed password.

        Returns:
            Tuple of (success: bool, message: str).
        """
        with self._lock:
            if username in self._users:
                return False, "Username already exists"
            if not username or len(username) > MAX_USERNAME_LENGTH:
                return False, "Invalid username length"
            self._users[username] = User(username=username, password_hash=password_hash)
            return True, "User registered successfully"

    def get_user(self, username: str) -> Optional[User]:
        """
        Retrieve a user by username.

        Args:
            username: Username to look up.

        Returns:
            User object if found, None otherwise.
        """
        with self._lock:
            return self._users.get(username)

    def update_last_login(self, username: str) -> bool:
        """
        Update the last_login timestamp for a user.

        Args:
            username: Username to update.

        Returns:
            True if user exists and updated, False otherwise.
        """
        with self._lock:
            user = self._users.get(username)
            if user:
                user.last_login = datetime.utcnow()
                return True
            return False


user_store = UserStore()


def hash_password(password: str) -> bytes:
    """
    Hash a plaintext password using bcrypt.

    Args:
        password: Plaintext password to hash.

    Returns:
        Bcrypt hash as bytes.

    Raises:
        ValueError: If password is empty or too long.
    """
    if not password or len(password) > MAX_PASSWORD_LENGTH:
        raise ValueError("Password length must be between 1 and 128 characters")
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=BCRYPT_ROUNDS))


def validate_registration_data(username: str, password: str) -> Tuple[bool, str]:
    """
    Validate registration input data.

    Args:
        username: Proposed username.
        password: Proposed password.

    Returns:
        Tuple of (is_valid: bool, error_message: str).
    """
    if not username or not username.strip():
        return False, "Username cannot be empty"
    if len(username) > MAX_USERNAME_LENGTH:
        return False, f"Username exceeds maximum length of {MAX_USERNAME_LENGTH}"
    if not password:
        return False, "Password cannot be empty"
    if len(password) < MIN_PASSWORD_LENGTH:
        return False, f"Password must be at least {MIN_PASSWORD_LENGTH} characters"
    if len(password) > MAX_PASSWORD_LENGTH:
        return False, f"Password exceeds maximum length of {MAX_PASSWORD_LENGTH}"
    # Additional password complexity checks could be added here
    return True, ""


def generate_csrf_token() -> str:
    """
    Generate a secure CSRF token.

    Returns:
        URL-safe random token string.
    """
    return secrets.token_urlsafe(CSRF_TOKEN_LENGTH)


def get_csrf_token() -> str:
    """
    Get or create a CSRF token for the current session.

    Returns:
        Current session's CSRF token.
    """
    if "csrf_token" not in session:
        session["csrf_token"] = generate_csrf_token()
    return session["csrf_token"]


def validate_csrf_token(submitted_token: str) -> bool:
    """
    Validate a submitted CSRF token against the session token.

    Args:
        submitted_token: Token from form or header.

    Returns:
        True if tokens match, False otherwise.
    """
    session_token = session.get("csrf_token")
    if not session_token or not submitted_token:
        return False
    return secrets.compare_digest(session_token, submitted_token)


def require_csrf(f: Callable[..., Any]) -> Callable[..., Any]:
    """
    Decorator to enforce CSRF validation on state-changing routes.

    Args:
        f: View function to wrap.

    Returns:
        Wrapped function that validates CSRF token.
    """

    @wraps(f)
    def decorated(*args: Any, **kwargs: Any) -> Response:
        if request.method in ("POST", "PUT", "DELETE", "PATCH"):
            token = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token")
            if not validate_csrf_token(token or ""):
                return jsonify({"error": "Invalid or missing CSRF token"}), 400
        return f(*args, **kwargs)

    return decorated


def login_required(f: Callable[..., Any]) -> Callable[..., Any]:
    """
    Decorator to require an authenticated session.

    Args:
        f: View function to wrap.

    Returns:
        Wrapped function that checks for active user session.
    """

    @wraps(f)
    def decorated(*args: Any, **kwargs: Any) -> Response:
        if "user_id" not in session:
            return jsonify({"error": "Authentication required"}), 401
        return f(*args, **kwargs)

    return decorated


@app.route("/register", methods=["POST"])
@require_csrf
def register() -> Response:
    """
    Register a new user account.

    Expected JSON payload:
        {
            "username": "string",
            "password": "string"
        }

    Returns:
        JSON response with success status and message.
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid JSON payload"}), 400

        username = data.get("username", "").strip()
        password = data.get("password", "")

        valid, msg = validate_registration_data(username, password)
        if not valid:
            return jsonify({"error": msg}), 400

        password_hash = hash_password(password)
        success, message = user_store.add_user(username, password_hash)
        if not success:
            return jsonify({"error": message}), 409

        return jsonify({"message": message}), 201

    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        app.logger.error(f"Registration error: {e}")
        return jsonify({"error": "Internal server error"}), 500


@app.route("/login", methods=["POST"])
@require_csrf
def login() -> Response:
    """
    Authenticate a user and create a session.

    Expected JSON payload:
        {
            "username": "string",
            "password": "string"
        }

    Returns:
        JSON response with success status, message, and CSRF token.
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid JSON payload"}), 400

        username = data.get("username", "").strip()
        password = data.get("password", "")

        if not username or not password:
            return jsonify({"error": "Username and password are required"}), 400

        user = user_store.get_user(username)
        if not user or not user.is_active:
            return jsonify({"error": "Invalid credentials"}), 401

        if not user.verify_password(password):
            return jsonify({"error": "Invalid credentials"}), 401

        # Create session
        session.permanent = True
        session["user_id"] = username
        session["csrf_token"] = generate_csrf_token()

        user_store.update_last_login(username)

        return jsonify(
            {
                "message": "Login successful",
                "csrf_token": session["csrf_token"],
                "username": username,
            }
        ), 200

    except Exception as e:
        app.logger.error(f"Login error: {e}")
        return jsonify({"error": "Internal server error"}), 500


@app.route("/logout", methods=["POST"])
@require_csrf
@login_required
def logout() -> Response:
    """
    Terminate the current user session.

    Returns:
        JSON response confirming logout.
    """
    try:
        session.clear()
        response = jsonify({"message": "Logged out successfully"})
        response.delete_cookie(SESSION_COOKIE_NAME)
        return response, 200
    except Exception as e:
        app.logger.error(f"Logout error: {e}")
        return jsonify({"error": "Internal server error"}), 500


@app.route("/profile", methods=["GET"])
@login_required
def profile() -> Response:
    """
    Retrieve the authenticated user's profile information.

    Returns:
        JSON response with user profile data.
    """
    try:
        username = session["user_id"]
        user = user_store.get_user(username)
        if not user:
            return jsonify({"error": "User not found"}), 404

        return jsonify(
            {
                "username": user.username,
                "created_at": user.created_at.isoformat(),
                "last_login": user.last_login.isoformat() if user.last_login else None,
            }
        ), 200
    except Exception as e:
        app.logger.error(f"Profile error: {e}")
        return jsonify({"error": "Internal server error"}), 500


@app.route("/csrf-token", methods=["GET"])
def csrf_token() -> Response:
    """
    Provide a CSRF token for the current session.

    Returns:
        JSON response with CSRF token.
    """
    token = get_csrf_token()
    return jsonify({"csrf_token": token}), 200


@app.route("/health", methods=["GET"])
def health_check() -> Response:
    """
    Health check endpoint for monitoring.

    Returns:
        JSON response indicating service status.
    """
    return jsonify({"status": "healthy", "timestamp": datetime.utcnow().isoformat()}), 200


if __name__ == "__main__":
    # For development only; use a production WSGI server in production
    app.run(host="0.0.0.0", port=5000, debug=False)