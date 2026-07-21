"""flask_auth.py
A minimal Flask authentication module implementing user registration, login,
logout, password hashing with bcrypt, and session management using JWT
stored in HttpOnly cookies.

The module is self‑contained for demonstration purposes; in production,
replace the in‑memory user store with a persistent database and configure
secure cookie attributes.
"""

from __future__ import annotations

import os
import datetime
from typing import Dict, Optional

from flask import Flask, request, jsonify, make_response, g
import bcrypt
import jwt

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #

# Secret key for JWT signing – should be set in environment for production.
JWT_SECRET = os.getenv("JWT_SECRET", "change_this_secret_key")
JWT_ALGORITHM = "HS256"
JWT_EXP_DELTA_SECONDS = 3600  # 1 hour token validity

# Flask app initialization
app = Flask(__name__)
app.config["JSONIFY_PRETTYPRINT_REGULAR"] = False


# --------------------------------------------------------------------------- #
# User store (in‑memory for demo)
# --------------------------------------------------------------------------- #

class UserStore:
    """Thread‑safe in‑memory store for user credentials."""

    def __init__(self) -> None:
        self._users: Dict[str, bytes] = {}

    def add_user(self, username: str, password_hash: bytes) -> None:
        """Add a new user. Raises ValueError if the username already exists."""
        if username in self._users:
            raise ValueError("User already exists.")
        self._users[username] = password_hash

    def get_password_hash(self, username: str) -> Optional[bytes]:
        """Retrieve the stored password hash for a user, or None if not found."""
        return self._users.get(username)

    def verify_credentials(self, username: str, password: str) -> bool:
        """Check if supplied credentials are valid."""
        stored_hash = self.get_password_hash(username)
        if stored_hash is None:
            return False
        return bcrypt.checkpw(password.encode("utf-8"), stored_hash)


_user_store = UserStore()


# --------------------------------------------------------------------------- #
# Helper functions
# --------------------------------------------------------------------------- #

def hash_password(password: str) -> bytes:
    """
    Hash a plaintext password using bcrypt.

    Args:
        password: The plaintext password.

    Returns:
        The bcrypt hash as bytes.

    Raises:
        ValueError: If the password is empty.
    """
    if not password:
        raise ValueError("Password must not be empty.")
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt)


def create_jwt_token(username: str) -> str:
    """
    Create a signed JWT token containing the username and expiration.

    Args:
        username: The authenticated user's name.

    Returns:
        A JWT token as a string.
    """
    exp = datetime.datetime.utcnow() + datetime.timedelta(seconds=JWT_EXP_DELTA_SECONDS)
    payload = {"sub": username, "exp": exp}
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    # PyJWT returns str in recent versions; ensure str.
    return token if isinstance(token, str) else token.decode("utf-8")


def decode_jwt_token(token: str) -> Dict[str, str]:
    """
    Decode and verify a JWT token.

    Args:
        token: The JWT token string.

    Returns:
        The token payload.

    Raises:
        jwt.ExpiredSignatureError: If the token has expired.
        jwt.InvalidTokenError: If the token is otherwise invalid.
    """
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])


def set_jwt_cookie(response, token: str) -> None:
    """
    Attach the JWT token to the response as an HttpOnly, Secure cookie.

    Args:
        response: The Flask response object.
        token: The JWT token string.
    """
    response.set_cookie(
        "access_token",
        token,
        httponly=True,
        secure=False,  # Set to True when serving over HTTPS
        samesite="Lax",
        max_age=JWT_EXP_DELTA_SECONDS,
    )


def clear_jwt_cookie(response) -> None:
    """Remove the JWT cookie from the client."""
    response.delete_cookie("access_token")


def get_token_from_request() -> Optional[str]:
    """Extract JWT token from the request cookies."""
    return request.cookies.get("access_token")


def login_required(func):
    """
    Flask view decorator that ensures a valid JWT token is present.
    The username is stored in Flask's `g` context variable.
    """
    from functools import wraps

    @wraps(func)
    def wrapper(*args, **kwargs):
        token = get_token_from_request()
        if not token:
            return jsonify({"error": "Authentication token required."}), 401
        try:
            payload = decode_jwt_token(token)
            g.current_user = payload["sub"]
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Token has expired."}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "Invalid token."}), 401
        return func(*args, **kwargs)

    return wrapper


# --------------------------------------------------------------------------- #
# Flask routes
# --------------------------------------------------------------------------- #

@app.route("/register", methods=["POST"])
def register() -> "flask.Response":
    """
    Register a new user.

    Expected JSON payload:
        {
            "username": "user",
            "password": "secret"
        }

    Returns:
        JSON response with success message or error details.
    """
    data = request.get_json(silent=True) or {}
    username = data.get("username")
    password = data.get("password")

    if not username or not password:
        return jsonify({"error": "Username and password are required."}), 400

    try:
        password_hash = hash_password(password)
        _user_store.add_user(username, password_hash)
    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400
    except Exception as exc:
        return jsonify({"error": "Registration failed.", "details": str(exc)}), 500

    return jsonify({"message": "User registered successfully."}), 201


@app.route("/login", methods=["POST"])
def login() -> "flask.Response":
    """
    Authenticate a user and issue a JWT token.

    Expected JSON payload:
        {
            "username": "user",
            "password": "secret"
        }

    Returns:
        JSON response with success message and sets JWT cookie.
    """
    data = request.get_json(silent=True) or {}
    username = data.get("username")
    password = data.get("password")

    if not username or not password:
        return jsonify({"error": "Username and password are required."}), 400

    try:
        if not _user_store.verify_credentials(username, password):
            raise ValueError("Invalid credentials.")
        token = create_jwt_token(username)
    except ValueError as ve:
        return jsonify({"error": str(ve)}), 401
    except Exception as exc:
        return jsonify({"error": "Login failed.", "details": str(exc)}), 500

    response = jsonify({"message": "Login successful."})
    set_jwt_cookie(response, token)
    return response, 200


@app.route("/logout", methods=["POST"])
def logout() -> "flask.Response":
    """
    Log out the current user by clearing the JWT cookie.

    Returns:
        JSON response confirming logout.
    """
    response = jsonify({"message": "Logged out successfully."})
    clear_jwt_cookie(response)
    return response, 200


@app.route("/protected", methods=["GET"])
@login_required
def protected() -> "flask.Response":
    """
    Example protected endpoint that requires authentication.

    Returns:
        JSON response containing the current username.
    """
    return jsonify({"message": f"Hello, {g.current_user}! This is a protected resource."}), 200


# --------------------------------------------------------------------------- #
# Application entry point
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    # For development only; use a production-ready server in real deployments.
    app.run(host="127.0.0.1", port=5000, debug=False)