"""
auth_app.py
A minimal Flask authentication module with user registration, password hashing,
and session management.  Users are stored in a SQLite database, passwords are
hashed with bcrypt, and login state is kept in Flask's signed cookies.

Only standard‑library modules and widely‑used PyPI packages are used:
    - Flask
    - bcrypt
"""

from __future__ import annotations

import sqlite3
import secrets
from typing import Optional, Tuple

import bcrypt
from flask import (
    Flask,
    abort,
    g,
    jsonify,
    request,
    session,
    url_for,
)

# --------------------------------------------------------------------------- #
# Database helpers
# --------------------------------------------------------------------------- #

DATABASE = "users.db"


def get_db() -> sqlite3.Connection:
    """
    Return a thread‑local SQLite connection, creating one if necessary.

    Returns
    -------
    sqlite3.Connection
        The database connection attached to the Flask application context.
    """
    if "db" not in g:
        conn = sqlite3.connect(DATABASE, detect_types=sqlite3.PARSE_DECLTYPES)
        conn.row_factory = sqlite3.Row
        g.db = conn
    return g.db  # type: ignore[return-value]


def close_db(e: Optional[BaseException] = None) -> None:
    """
    Close the database connection attached to the current Flask context, if any.

    Parameters
    ----------
    e : BaseException | None
        Optional exception passed by Flask teardown.
    """
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db() -> None:
    """
    Initialise the users table.  This function is idempotent.
    """
    db = get_db()
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash BLOB NOT NULL
        )
        """
    )
    db.commit()


# --------------------------------------------------------------------------- #
# User management
# --------------------------------------------------------------------------- #

def _hash_password(password: str) -> bytes:
    """
    Hash a plain‑text password using bcrypt.

    Parameters
    ----------
    password : str
        The password to hash.

    Returns
    -------
    bytes
        The bcrypt hash.
    """
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt)


def _check_password(password: str, hashed: bytes) -> bool:
    """
    Verify a password against a stored bcrypt hash.

    Parameters
    ----------
    password : str
        The candidate password.
    hashed : bytes
        The stored bcrypt hash.

    Returns
    -------
    bool
        True if the password matches, False otherwise.
    """
    return bcrypt.checkpw(password.encode("utf-8"), hashed)


def register_user(username: str, password: str) -> None:
    """
    Register a new user.  Raises a ValueError if the username already exists
    or if input validation fails.

    Parameters
    ----------
    username : str
        Desired username; must be non‑empty and at most 150 characters.
    password : str
        Plain‑text password; must be at least 8 characters.

    Raises
    ------
    ValueError
        If validation fails or the username is already taken.
    """
    if not username or len(username) > 150:
        raise ValueError("Invalid username.")
    if not password or len(password) < 8:
        raise ValueError("Password must be at least 8 characters long.")

    db = get_db()
    try:
        db.execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?)",
            (username, _hash_password(password)),
        )
        db.commit()
    except sqlite3.IntegrityError as exc:
        raise ValueError("Username already taken.") from exc


def verify_credentials(username: str, password: str) -> bool:
    """
    Verify that the supplied credentials match a stored user.

    Parameters
    ----------
    username : str
        The username to look up.
    password : str
        The candidate password.

    Returns
    -------
    bool
        True if the credentials are valid, False otherwise.
    """
    db = get_db()
    cur = db.execute(
        "SELECT password_hash FROM users WHERE username = ?", (username,)
    )
    row = cur.fetchone()
    if row is None:
        return False
    stored_hash: bytes = row["password_hash"]
    return _check_password(password, stored_hash)


def login_user(username: str) -> None:
    """
    Mark a user as logged in by storing their username in the Flask session.

    Parameters
    ----------
    username : str
        The username to store in the session.
    """
    session.clear()
    session["user"] = username
    session["csrf_token"] = secrets.token_urlsafe(32)


def logout_user() -> None:
    """
    Log the current user out by clearing the session.
    """
    session.clear()


def current_user() -> Optional[str]:
    """
    Retrieve the username of the currently logged‑in user, if any.

    Returns
    -------
    str | None
        The username stored in the session, or None if not logged in.
    """
    return session.get("user")  # type: ignore[return-value]


# --------------------------------------------------------------------------- #
# Flask application factory
# --------------------------------------------------------------------------- #

def create_app() -> Flask:
    """
    Create and configure the Flask application.

    Returns
    -------
    Flask
        The configured Flask app instance.
    """
    app = Flask(__name__)
    app.config["SECRET_KEY"] = secrets.token_urlsafe(64)
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

    @app.before_request
    def _load_user() -> None:
        # No heavy lifting needed; `current_user` reads from the session.
        pass

    @app.teardown_appcontext
    def _close_db(exception: Optional[BaseException] = None) -> None:
        close_db(exception)

    @app.route("/register", methods=["POST"])
    def register() -> Tuple[dict, int]:
        """
        Register a new user. Expects JSON payload with ``username`` and ``password``.
        """
        if not request.is_json:
            return {"error": "JSON payload required."}, 400
        data = request.get_json(silent=True) or {}
        username = data.get("username", "")
        password = data.get("password", "")
        try:
            register_user(username, password)
            return {"message": "User registered successfully."}, 201
        except ValueError as exc:
            return {"error": str(exc)}, 400

    @app.route("/login", methods=["POST"])
    def login() -> Tuple[dict, int]:
        """
        Log a user in. Expects JSON payload with ``username`` and ``password``.
        """
        if not request.is_json:
            return {"error": "JSON payload required."}, 400
        data = request.get_json(silent=True) or {}
        username = data.get("username", "")
        password = data.get("password", "")
        if not username or not password:
            return {"error": "Username and password required."}, 400
        if verify_credentials(username, password):
            login_user(username)
            return {"message": "Logged in successfully."}, 200
        return {"error": "Invalid credentials."}, 401

    @app.route("/logout", methods=["POST"])
    def logout() -> Tuple[dict, int]:
        """
        Log the current user out. CSRF protection is enforced via a session token.
        """
        token = request.headers.get("X-CSRF-Token")
        if not token or token != session.get("csrf_token"):
            return {"error": "Invalid CSRF token."}, 400
        logout_user()
        return {"message": "Logged out successfully."}, 200

    @app.route("/protected", methods=["GET"])
    def protected() -> Tuple[dict, int]:
        """
        Example of a protected endpoint that requires authentication.
        """
        user = current_user()
        if not user:
            abort(401)
        return {"message": f"Hello, {user}! This is a protected resource."}, 200

    @app.errorhandler(400)
    @app.errorhandler(401)
    @app.errorhandler(404)
    @app.errorhandler(500)
    def handle_error(error) -> Tuple[dict, int]:
        """
        Return JSON error responses for common HTTP errors.
        """
        return {"error": error.description if hasattr(error, "description") else str(error)}, error.code  # type: ignore[attr-defined]

    # Initialise the DB when the app starts
    with app.app_context():
        init_db()

    return app


if __name__ == "__main__":
    # Running directly for development purposes only.
    # In production, use a proper WSGI server.
    app = create_app()
    app.run(host="127.0.0.1", port=5000, debug=False)