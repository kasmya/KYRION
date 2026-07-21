"""
User Authentication Module

This module provides a complete user authentication system including
registration, login, logout, and session management. It uses bcrypt for
password hashing and supports both Flask session-based and JWT-based
authentication strategies. All functions include comprehensive error
handling and follow security best practices.
"""

import hashlib
import hmac
import logging
import os
import secrets
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple, Union

import bcrypt
import jwt
from flask import Flask, session as flask_session, request

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Constants
DEFAULT_TOKEN_EXPIRY = 3600  # 1 hour
MIN_PASSWORD_LENGTH = 8
BCRYPT_ROUNDS = 12

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class User:
    """Represents a registered user."""
    user_id: str
    username: str
    email: str
    password_hash: str
    created_at: float = field(default_factory=time.time)
    last_login: Optional[float] = None


# ---------------------------------------------------------------------------
# In-memory user store (replace with a real database in production)
# ---------------------------------------------------------------------------

_users_db: Dict[str, User] = {}
_username_index: Dict[str, str] = {}  # username -> user_id
_email_index: Dict[str, str] = {}     # email -> user_id

# ---------------------------------------------------------------------------
# Password utilities
# ---------------------------------------------------------------------------

def hash_password(password: str) -> str:
    """
    Hash a plaintext password using bcrypt with a random salt.

    Args:
        password: The plaintext password to hash.

    Returns:
        A bcrypt hash string suitable for storage.

    Raises:
        ValueError: If the password is empty or does not meet complexity requirements.
    """
    if not password or len(password) < MIN_TOKEN_LENGTH:
        raise ValueError(f"Password must be at least {MIN_TOKEN_LENGTH} characters long.")
    salt = bcrypt.gensalt(rounds=BCRYPT_ROUNDS)
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')


def verify_password(password: str, password_hash: str) -> bool:
    """
    Verify a plaintext password against a stored bcrypt hash.

    Args:
        password: The plaintext password to verify.
        password_hash: The bcrypt hash to compare against.

    Returns:
        True if the password matches the hash, False otherwise.
    """
    if not password or not password_hash:
        return False
    try:
        return bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))
    except (ValueError, AttributeError) as e:
        logger.error(f"Password verification error: {e}")
        return False


# ---------------------------------------------------------------------------
# User management
# ---------------------------------------------------------------------------

def register_user(username: str, email: str, password: str) -> User:
    """
    Register a new user with the provided credentials.

    Args:
        username: Desired username (must be unique).
        email: User's email address (must be unique).
        password: Plaintext password meeting complexity requirements.

    Returns:
        The newly created User object.

    Raises:
        ValueError: If the username or email is already taken, or if
                    validation fails.
    """
    # Input validation
    if not username or not isinstance(username, str):
        raise ValueError("Username is required and must be a string.")
    if not email or not isinstance(email, str) or "@" not in email:
        raise ValueError("A valid email address is required.")
    if not password or len(password) < MIN_TOKEN_LENGTH:
        raise ValueError(f"Password must be at least {MIN_TOKEN_LENGTH} characters long.")

    username_lower = username.lower().strip()
    email_lower = email.lower().strip()

    # Check for existing username
    if username_lower in _username_index:
        raise ValueError("Username already exists.")

    # Check for existing email
    if email_lower in _email_index:
        raise ValueError("Email already registered.")

    # Generate a secure user ID
    user_id = hashlib.sha256(os.urandom(32)).hexdigest()

    # Hash the password
    try:
        password_hash = hash_password(password)
    except Exception as e:
        logger.error(f"Failed to hash password: {e}")
        raise RuntimeError("Could not process password.") from e

    # Create and store user
    user = User(
        user_id=user_id,
        username=username_lower,
        email=email_lower,
        password_hash=password_hash
    )
    _users_db[user_id] = user
    _username_index[username_lower] = user_id
    _email_index[email_lower] = user_id

    logger.info(f"User registered: {username_lower}")
    return user


def authenticate_user(identifier: str, password: str) -> Optional[User]:
    """
    Authenticate a user by username or email and password.

    Args:
        identifier: Username or email address.
        password: Plaintext password.

    Returns:
        The authenticated User object if credentials are valid, None otherwise.
    """
    if not identifier or not password:
        return None

    identifier_lower = identifier.lower().strip()
    user_id = _username_index.get(identifier_lower) or _email_index.get(identifier_lower)

    if not user_id:
        return None

    user = _users_db.get(user_id)
    if not user:
        return None

    if verify_password(password, user.password_hash):
        user.last_login = time.time()
        _users_db[user_id] = user
        logger.info(f"User {user.username} authenticated successfully.")
        return user

    logger.warning(f"Failed authentication attempt for {identifier_lower}.")
    return None


# ---------------------------------------------------------------------------
# Flask session-based authentication
# ---------------------------------------------------------------------------

def login_session(user: User, app: Flask) -> None:
    """
    Log in a user using Flask's signed session cookies.

    Args:
        user: The authenticated User object.
        app: The Flask application instance (must have a secret key configured).

    Raises:
        RuntimeError: If the Flask app does not have a secret key set.
    """
    if not app.secret_key:
        raise RuntimeError("Flask app must have a secret_key configured for session management.")
    flask_session['user_id'] = user.user_id
    flask_session['username'] = user.username
    flask_session['login_time'] = time.time()
    logger.info(f"Session login for user {user.username}.")


def logout_session() -> None:
    """
    Log out the current user by clearing the Flask session.
    """
    flask_session.clear()
    logger.info("User session cleared.")


def get_current_user_from_session() -> Optional[User]:
    """
    Retrieve the currently logged-in user from the Flask session.

    Returns:
        The User object if a valid session exists, None otherwise.
    """
    user_id = flask_session.get('user_id')
    if not user_id:
        return None
    return _users_db.get(user_id)


# ---------------------------------------------------------------------------
# JWT-based authentication
# ---------------------------------------------------------------------------

def generate_jwt(user: User, secret_key: str, expires_in: int = DEFAULT_TOKEN_EXPIRY) -> str:
    """
    Generate a JSON Web Token (JWT) for the given user.

    Args:
        user: The authenticated User object.
        secret_key: Secret key used to sign the token.
        expires_in: Token lifetime in seconds (default 3600).

    Returns:
        A signed JWT string.

    Raises:
        ValueError: If the secret key is empty or missing.
    """
    if not secret_key:
        raise ValueError("A non-empty secret_key is required for JWT generation.")

    now = int(time.time())
    payload = {
        'sub': user.user_id,
        'username': user.username,
        'iat': now,
        'exp': now + expires_in,
        'jti': hashlib.sha256(os.urandom(32)).hexdigest()
    }
    try:
        token = jwt.encode(payload, secret_key, algorithm="HS256")
        logger.info(f"JWT generated for {user.username}.")
        return token
    except Exception as e:
        logger.error(f"JWT encoding failed: {e}")
        raise RuntimeError("Could not generate authentication token.") from e


def decode_jwt(token: str, secret_key: str) -> Optional[Dict[str, Any]]:
    """
    Decode and validate a JWT token.

    Args:
        token: The JWT string to decode.
        secret_key: The secret key used to verify the token signature.

    Returns:
        The token payload as a dictionary if valid, None otherwise.
    """
    if not token or not secret_key:
        return None
    try:
        payload = jwt.decode(token, secret_key, algorithms=["HS256"])
        return payload
    except jwt.ExpiredSignatureError:
        logger.warning("JWT token has expired.")
        return None
    except jwt.InvalidTokenError as e:
        logger.warning(f"Invalid JWT token: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected JWT decoding error: {e}")
        return None


def get_current_user_from_jwt(token: str, secret_key: str) -> Optional[User]:
    """
    Retrieve the user associated with a valid JWT token.

    Args:
        token: The JWT string.
        secret_key: The secret key used to verify the token.

    Returns:
        The User object if the token is valid and user exists, None otherwise.
    """
    payload = decode_jwt(token, secret_key)
    if not payload:
        return None
    user_id = payload.get("sub")
    if not user_id:
        return None
    return _users_db.get(user_id)


# ---------------------------------------------------------------------------
# Request helpers (Flask)
# ---------------------------------------------------------------------------

def require_jwt_auth(secret_key: str) -> Optional[User]:
    """
    Extract and validate a JWT token from the Authorization header of a Flask request.

    Args:
        secret_key: The secret key used to verify the token.

    Returns:
        The authenticated User if the token is valid, None otherwise.
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    token = auth_header.split(" ", 1)[1].strip()
    return get_current_user_from_jwt(token, secret_key)


# ---------------------------------------------------------------------------
# Example usage (commented out)
# ---------------------------------------------------------------------------
# if __name__ == "__main__":
#     from flask import Flask
#     app = Flask(__name__)
#     app.secret_key = os.urandom(24)
#
#     # Registration
#     try:
#         user = register_user("alice", "alice@example.com", "SecurePass123!")
#     except ValueError as e:
#         print(f"Registration failed: {e}")
#
#     # Authentication
#     user = authenticate_user("alice", "SecurePass123!")
#     if user:
#         # Session login
#         with app.test_request_context():
#             login_session(user, app)
#             current = get_current_user_from_session()
#
#         # JWT login
#         token = generate_jwt(user, app.secret_key)
#         # Later: user = get_current_user_from_jwt(token, app.secret_key)