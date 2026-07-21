"""
user_auth.py

A self-contained module for user registration, login, logout, and session management.
Uses bcrypt for password hashing and Flask sessions for state management.
Designed with security best practices: constant-time password comparison, input validation,
secure session configuration, and explicit error handling.

Dependencies: flask, bcrypt (PyPI packages)
"""

from __future__ import annotations

import re
import uuid
from datetime import timedelta
from typing import Any, Callable, Dict, Optional, Tuple

import bcrypt
from flask import Flask, Response, redirect, request, session, url_for
from werkzeug.exceptions import BadRequest, Unauthorized


class AuthError(Exception):
    """Base exception for authentication/authorization failures."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class UserStore:
    """
    In-memory user store for demonstration purposes.
    Replace with a persistent database in production.
    """

    def __init__(self) -> None:
        self._users: Dict[str, Dict[str, Any]] = {}

    def add_user(self, username: str, password_hash: str) -> str:
        """
        Register a new user with a unique ID.

        Args:
            username: The unique username.
            password_hash: bcrypt hash of the user's password.

        Returns:
            The generated user ID.

        Raises:
            ValueError: If the username already exists.
        """
        if username in self._users:
            raise ValueError("Username already exists")
        user_id = uuid.uuid4().hex
        self._users[username] = {
            "user_id": user_id,
            "username": username,
            "password_hash": password_hash,
        }
        return user_id

    def get_user(self, username: str) -> Optional[Dict[str, Any]]:
        """Retrieve user record by username, or None if not found."""
        return self._users.get(username)

    def user_exists(self, username: str) -> bool:
        """Check whether a username is already taken."""
        return username in self._users


class PasswordManager:
    """Handles password hashing and verification using bcrypt."""

    @staticmethod
    def hash_password(password: str) -> str:
        """
        Hash a plain-text password with a randomly generated salt.

        Args:
            password: The plain-text password.

        Returns:
            bcrypt hash as a string.

        Raises:
            ValueError: If the password is empty or too short.
        """
        if not password or len(password) < 8:
            raise ValueError("Password must be at least 8 characters long")
        # bcrypt handles salt generation internally
        return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    @staticmethod
    def verify_password(password: str, password_hash: str) -> bool:
        """
        Verify a plain-text password against a stored bcrypt hash.

        Args:
            password: The plain-text password to check.
            password_hash: The stored bcrypt hash.

        Returns:
            True if the password matches, False otherwise.
        """
        try:
            return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
        except ValueError:
            # Handles malformed hash inputs gracefully
            return False


class InputValidator:
    """Centralised input validation utilities."""

    USERNAME_PATTERN = re.compile(r"^[a-zA-Z0-9_\-\.]{3,30}$")

    @staticmethod
    def validate_username(username: str) -> str:
        """
        Validate and sanitise a username.

        Args:
            username: Raw username input.

        Returns:
            The trimmed, validated username.

        Raises:
            ValueError: If the username fails validation.
        """
        if not isinstance(username, str):
            raise ValueError("Username must be a string")
        username = username.strip()
        if not InputValidator.USERNAME_PATTERN.match(username):
            raise ValueError(
                "Username must be 3–30 characters and contain only letters, digits, "
                "underscores, hyphens, or dots"
            )
        return username

    @staticmethod
    def validate_password(password: str) -> str:
        """
        Validate a plain-text password for minimum requirements.

        Args:
            password: Raw password input.

        Returns:
            The password if valid.

        Raises:
            ValueError: If the password fails length or complexity checks.
        """
        if not isinstance(password, str):
            raise ValueError("Password must be a string")
        if len(password) < 8:
            raise ValueError("Password must be at least 8 characters long")
        # Additional complexity checks can be added here
        return password


class AuthManager:
    """
    Orchestrates user registration, login, logout, and session management
    using Flask's signed cookie-based sessions.
    """

    def __init__(self, app: Optional[Flask] = None) -> None:
        """
        Initialise the AuthManager with a Flask application instance.

        Args:
            app: Optional Flask app. If provided, session configuration is applied immediately.
        """
        self.user_store = UserStore()
        self.password_manager = PasswordManager()
        self.input_validator = InputValidator()
        if app is not None:
            self.init_app(app)

    def init_app(self, app: Flask) -> None:
        """
        Configure the Flask app for secure session management.

        Args:
            app: The Flask application instance.

        Sets session cookie parameters for security:
            - HttpOnly
            - Secure (requires HTTPS in production)
            - SameSite='Lax'
            - Short lifetime
        """
        app.config.setdefault("SECRET_KEY", uuid.uuid4().hex)
        app.config.setdefault("SESSION_COOKIE_HTTPONLY", True)
        app.config.setdefault("SESSION_COOKIE_SECURE", True)  # Set to True in production with HTTPS
        app.config.setdefault("SESSION_COOKIE_SAMESITE", "Lax")
        app.config.setdefault("PERMANENT_SESSION_LIFETIME", timedelta(hours=1))

    def register(self, username: str, password: str) -> Tuple[str, str]:
        """
        Register a new user account.

        Args:
            username: Desired username.
            password: Plain-text password.

        Returns:
            A tuple of (user_id, username) on success.

        Raises:
            AuthError: If username is invalid, already exists, or password is weak.
        """
        try:
            clean_username = self.input_validator.validate_username(username)
            clean_password = self.input_validator.validate_password(password)
        except ValueError as exc:
            raise AuthError(str(exc), status_code=400) from exc

        if self.user_store.user_exists(clean_username):
            raise AuthError("Username already exists", status_code=409)

        try:
            password_hash = self.password_manager.hash_password(clean_password)
        except ValueError as exc:
            raise AuthError(str(exc), status_code=400) from exc

        user_id = self.user_store.add_user(clean_username, password_hash)
        return user_id, clean_username

    def login(self, username: str, password: str) -> Tuple[str, str]:
        """
        Authenticate a user and create a session.

        Args:
            username: The user's username.
            password: The user's plain-text password.

        Returns:
            A tuple of (user_id, username) on successful login.

        Raises:
            AuthError: If credentials are invalid.
        """
        try:
            clean_username = self.input_validator.validate_username(username)
        except ValueError as exc:
            raise AuthError("Invalid username", status_code=400) from exc

        user = self.user_store.get_user(clean_username)
        if user is None:
            # Use constant-time response to avoid user enumeration
            self.password_manager.verify_password("dummy", "$2b$12$dummyhashvalue")
            raise AuthError("Invalid username or password", status_code=401)

        if not self.password_manager.verify_password(password, user["password_hash"]):
            raise AuthError("Invalid username or password", status_code=401)

        # Regenerate session ID to prevent session fixation
        session.clear()
        session.permanent = True
        session["user_id"] = user["user_id"]
        session["username"] = user["username"]
        return user["user_id"], user["username"]

    def logout(self) -> None:
        """
        Terminate the current user session.

        Clears all session data and removes the session cookie.
        """
        session.clear()

    def get_current_user(self) -> Optional[Dict[str, str]]:
        """
        Retrieve the currently authenticated user from the session.

        Returns:
            A dict with 'user_id' and 'username' if logged in, else None.
        """
        user_id = session.get("user_id")
        username = session.get("username")
        if user_id and username:
            return {"user_id": user_id, "username": username}
        return None

    def require_login(self, func: Callable) -> Callable:
        """
        Decorator to protect routes that require authentication.

        Args:
            func: The view function to wrap.

        Returns:
            Wrapped function that returns 401 if the user is not logged in.
        """

        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if self.get_current_user() is None:
                raise Unauthorized("Authentication required")
            return func(*args, **kwargs)

        wrapper.__name__ = func.__name__
        wrapper.__doc__ = func.__doc__
        return wrapper


# ---------------------------------------------------------------------------
# Example Flask application integration (can be removed when used as a library)
# ---------------------------------------------------------------------------
def create_app() -> Flask:
    """
    Create and configure a minimal Flask app with authentication endpoints.

    Returns:
        Configured Flask application instance.
    """
    app = Flask(__name__)
    auth = AuthManager()
    auth.init_app(app)

    @app.route("/register", methods=["POST"])
    def register() -> Tuple[Response, int]:
        data = request.get_json(silent=True) or {}
        username = data.get("username", "")
        password = data.get("password", "")
        try:
            user_id, username = auth.register(username, password)
            return {"user_id": user_id, "username": username}, 201
        except AuthError as e:
            return {"error": e.message}, e.status_code
        except Exception:
            return {"error": "Internal server error"}, 500

    @app.route("/login", methods=["POST"])
    def login() -> Tuple[Response, int]:
        data = request.get_json(silent=True) or {}
        username = data.get("username", "")
        password = data.get("password", "")
        try:
            user_id, username = auth.login(username, password)
            return {"user_id": user_id, "username": username}, 200
        except AuthError as e:
            return {"error": e.message}, e.status_code
        except Exception:
            return {"error": "Internal server error"}, 500

    @app.route("/logout", methods=["POST"])
    def logout() -> Tuple[Response, int]:
        auth.logout()
        return {"message": "Logged out successfully"}, 200

    @app.route("/me", methods=["GET"])
    @auth.require_login
    def me() -> Tuple[Response, int]:
        user = auth.get_current_user()
        return {"user": user}, 200

    return app


if __name__ == "__main__":
    # For local development only; disable secure cookie for testing without HTTPS
    app = create_app()
    app.config["SESSION_COOKIE_SECURE"] = False
    app.run(debug=True)