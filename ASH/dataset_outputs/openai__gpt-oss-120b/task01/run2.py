"""
flask_auth.py

A self-contained Flask authentication module providing user registration,
login, logout, and session management using secure password hashing with
bcrypt and SQLite for persistent storage.

Features
--------
- User registration with unique username validation.
- Password hashing with bcrypt (salted, adaptive).
- Login with credential verification.
- Session management via Flask's signed secure cookies.
- Logout endpoint that clears the session.
- Simple protected route example.
- Explicit error handling and type hints for all functions.

Dependencies
------------
- Flask
- bcrypt (PyPI package)
"""

from __future__ import annotations

import sqlite3
import os
from typing import Optional, Tuple, Dict, Any

from flask import Flask, request, session, redirect, url_for, jsonify, abort, g
import bcrypt

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #

DATABASE = os.path.join(os.path.abspath(os.path.dirname(__file__)), "users.db")
SECRET_KEY = os.urandom(24)  # In production, use a constant secret stored securely.

app = Flask(__name__)
app.config["SECRET_KEY"] = SECRET_KEY
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = False  # Set True when using HTTPS.


# --------------------------------------------------------------------------- #
# Database utilities
# --------------------------------------------------------------------------- #

def get_db() -> sqlite3.Connection:
    """
    Retrieve a thread‑local SQLite connection, creating the database if needed.

    Returns
    -------
    sqlite3.Connection
        The SQLite connection object.
    """
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE, detect_types=sqlite3.PARSE_DECLTYPES)
        g.db.row_factory = sqlite3.Row
    return g.db


def close_db(e: Optional[BaseException] = None) -> None:
    """
    Close the SQLite connection if it exists.

    Parameters
    ----------
    e : Optional[BaseException]
        Exception passed by Flask teardown (ignored).
    """
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db() -> None:
    """
    Initialize the users table in the SQLite database.
    """
    db = get_db()
    try:
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash BLOB NOT NULL
            );
            """
        )
        db.commit()
    except sqlite3.Error as exc:
        raise RuntimeError(f"Database initialization failed: {exc}") from exc


@app.before_first_request
def _initialize() -> None:
    """Initialize the database before handling the first request."""
    init_db()


@app.teardown_appcontext
def _teardown_db(exception: Optional[BaseException]) -> None:
    """Close the DB connection after each request."""
    close_db(exception)


# --------------------------------------------------------------------------- #
# User management functions
# --------------------------------------------------------------------------- #

def _hash_password(password: str) -> bytes:
    """
    Hash a plaintext password using bcrypt.

    Parameters
    ----------
    password : str
        The plaintext password.

    Returns
    -------
    bytes
        The bcrypt hash.
    """
    try:
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password.encode("utf-8"), salt)
    except (ValueError, TypeError) as exc:
        raise ValueError("Invalid password provided.") from exc


def _verify_password(password: str, password_hash: bytes) -> bool:
    """
    Verify a plaintext password against a stored bcrypt hash.

    Parameters
    ----------
    password : str
        The plaintext password to verify.
    password_hash : bytes
        The stored bcrypt hash.

    Returns
    -------
    bool
        True if the password matches, False otherwise.
    """
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash)
    except (ValueError, TypeError) as exc:
        raise ValueError("Invalid password or hash for verification.") from exc


def create_user(username: str, password: str) -> int:
    """
    Register a new user with a unique username.

    Parameters
    ----------
    username : str
        Desired username (must be unique, non‑empty).
    password : str
        Plaintext password (must meet basic criteria).

    Returns
    -------
    int
        The newly created user's ID.

    Raises
    ------
    ValueError
        If the username is taken or input validation fails.
    RuntimeError
        If the database operation fails.
    """
    if not username or not password:
        raise ValueError("Username and password cannot be empty.")

    password_hash = _hash_password(password)

    db = get_db()
    try:
        cursor = db.execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?)",
            (username, password_hash),
        )
        db.commit()
        return cursor.lastrowid
    except sqlite3.IntegrityError as exc:
        raise ValueError("Username already exists.") from exc
    except sqlite3.Error as exc:
        raise RuntimeError(f"Failed to create user: {exc}") from exc


def get_user_by_username(username: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve a user record by username.

    Parameters
    ----------
    username : str
        Username to look up.

    Returns
    -------
    Optional[Dict[str, Any]]
        User record dict with keys 'id', 'username', 'password_hash' if found,
        otherwise None.
    """
    db = get_db()
    cursor = db.execute(
        "SELECT id, username, password_hash FROM users WHERE username = ?", (username,)
    )
    row = cursor.fetchone()
    if row:
        return {"id": row["id"], "username": row["username"], "password_hash": row["password_hash"]}
    return None


def authenticate_user(username: str, password: str) -> int:
    """
    Verify credentials and return the user's ID.

    Parameters
    ----------
    username : str
        Username supplied.
    password : str
        Plaintext password supplied.

    Returns
    -------
    int
        Authenticated user's ID.

    Raises
    ------
    ValueError
        If authentication fails.
    """
    user = get_user_by_username(username)
    if user is None:
        raise ValueError("Invalid username or password.")

    if not _verify_password(password, user["password_hash"]):
        raise ValueError("Invalid username or password.")

    return user["id"]


# --------------------------------------------------------------------------- #
# Flask route handlers
# --------------------------------------------------------------------------- #

@app.route("/register", methods=["POST"])
def register() -> Tuple[str, int]:
    """
    Handle user registration.

    Expected JSON payload:
        {
            "username": "desired_name",
            "password": "plain_text_password"
        }

    Returns
    -------
    Tuple[str, int]
        JSON message and HTTP status code.
    """
    if not request.is_json:
        abort(400, description="Request must be JSON.")

    data = request.get_json()
    username = data.get("username")
    password = data.get("password")

    try:
        user_id = create_user(username, password)
        return jsonify({"msg": "User registered.", "user_id": user_id}), 201
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/login", methods=["POST"])
def login() -> Tuple[str, int]:
    """
    Authenticate a user and establish a session.

    Expected JSON payload:
        {
            "username": "existing_user",
            "password": "plain_text_password"
        }

    Returns
    -------
    Tuple[str, int]
        JSON message and HTTP status code.
    """
    if not request.is_json:
        abort(400, description="Request must be JSON.")

    data = request.get_json()
    username = data.get("username")
    password = data.get("password")

    try:
        user_id = authenticate_user(username, password)
        session.clear()
        session["user_id"] = user_id
        session["username"] = username
        return jsonify({"msg": "Login successful."}), 200
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 401
    except Exception as exc:  # Catch unexpected errors
        return jsonify({"error": f"Login failed: {exc}"}), 500


@app.route("/logout", methods=["POST"])
def logout() -> Tuple[str, int]:
    """
    Log out the current user by clearing the session.

    Returns
    -------
    Tuple[str, int]
        JSON message and HTTP status code.
    """
    session.clear()
    return jsonify({"msg": "Logged out."}), 200


def login_required(view_func):
    """
    Decorator to protect routes requiring authentication.

    Parameters
    ----------
    view_func : Callable
        The view function to wrap.

    Returns
    -------
    Callable
        Wrapped view function.
    """
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            abort(401, description="Authentication required.")
        return view_func(*args, **kwargs)
    wrapper.__name__ = view_func.__name__
    return wrapper


@app.route("/profile", methods=["GET"])
@login_required
def profile() -> Tuple[Dict[str, Any], int]:
    """
    Example protected endpoint returning current user's info.

    Returns
    -------
    Tuple[Dict[str, Any], int]
        JSON payload with username and user_id, and HTTP status code.
    """
    return jsonify({
        "user_id": session.get("user_id"),
        "username": session.get("username")
    }), 200


# --------------------------------------------------------------------------- #
# Application entry point
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    # For development only; in production use a WSGI server.
    app.run(host="127.0.0.1", port=5000, debug=False)