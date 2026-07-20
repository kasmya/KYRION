"""
Flask based authentication system with:

- User registration
- Password hashing using bcrypt
- Session management using JWT stored in HttpOnly secure cookies
- Login / logout endpoints
- Type hints, docstrings and error handling
"""

from __future__ import annotations

import datetime as _dt
import os
from typing import Optional, Tuple

import bcrypt
import jwt
from flask import Flask, jsonify, request, make_response, g
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import IntegrityError

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATABASE_URI = f"sqlite:///{os.path.join(BASE_DIR, 'users.db')}"
JWT_SECRET = os.environ.get("JWT_SECRET", "change-me-please")
JWT_ALGORITHM = "HS256"
JWT_EXPIRES_MINUTES = 30

# --------------------------------------------------------------------------- #
# Flask app & DB init
# --------------------------------------------------------------------------- #
app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URI
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SECRET_KEY"] = JWT_SECRET

db = SQLAlchemy(app)


# --------------------------------------------------------------------------- #
# Database model
# --------------------------------------------------------------------------- #
class User(db.Model):
    """Simple user table."""

    __tablename__ = "users"

    id: int = db.Column(db.Integer, primary_key=True)
    username: str = db.Column(db.String(150), unique=True, nullable=False, index=True)
    password_hash: bytes = db.Column(db.LargeBinary(60), nullable=False)

    def verify_password(self, password: str) -> bool:
        """Check plain password against stored hash."""
        return bcrypt.checkpw(password.encode("utf-8"), self.password_hash)


# --------------------------------------------------------------------------- #
# Helper functions
# --------------------------------------------------------------------------- #
def _hash_password(password: str) -> bytes:
    """Return bcrypt hash of password."""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt)


def _create_jwt(user_id: int) -> str:
    """Create a signed JWT for given user id."""
    payload = {
        "sub": user_id,
        "iat": _dt.datetime.utcnow(),
        "exp": _dt.datetime.utcnow() + _dt.timedelta(minutes=JWT_EXPIRES_MINUTES),
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    # jwt.encode returns str on pyjwt>=2, bytes on older versions
    return token if isinstance(token, str) else token.decode("utf-8")


def _decode_jwt(token: str) -> Optional[int]:
    """Decode JWT and return user_id or None if invalid/expired."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return int(payload["sub"])
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError, KeyError):
        return None


def _set_auth_cookie(response, token: str) -> None:
    """Attach JWT to response as a secure HttpOnly cookie."""
    response.set_cookie(
        "access_token",
        token,
        httponly=True,
        secure=True,
        samesite="Lax",
        max_age=JWT_EXPIRES_MINUTES * 60,
    )


def _clear_auth_cookie(response) -> None:
    """Remove JWT cookie."""
    response.delete_cookie("access_token")


def _get_current_user() -> Optional[User]:
    """Return user object for request based on JWT cookie."""
    token = request.cookies.get("access_token")
    if not token:
        return None
    user_id = _decode_jwt(token)
    if not user_id:
        return None
    return User.query.get(user_id)


# --------------------------------------------------------------------------- #
# Request hooks
# --------------------------------------------------------------------------- #
@app.before_request
def load_user() -> None:
    """Load user into flask.g for the lifetime of the request."""
    g.current_user = _get_current_user()


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #
@app.route("/register", methods=["POST"])
def register() -> Tuple[dict, int]:
    """
    Register a new user.
    Expected JSON: {"username": "...", "password": "..."}
    """
    data = request.get_json(silent=True) or {}
    username = data.get("username")
    password = data.get("password")

    if not username or not password:
        return jsonify({"error": "username and password required"}), 400

    if len(password) < 8:
        return jsonify({"error": "password must be at least 8 characters"}), 400

    password_hash = _hash_password(password)

    new_user = User(username=username, password_hash=password_hash)
    db.session.add(new_user)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "username already exists"}), 409

    return jsonify({"message": "user created"}), 201


@app.route("/login", methods=["POST"])
def login() -> Tuple[dict, int]:
    """
    Authenticate user and issue JWT.
    Expected JSON: {"username": "...", "password": "..."}
    """
    data = request.get_json(silent=True) or {}
    username = data.get("username")
    password = data.get("password")

    if not username or not password:
        return jsonify({"error": "username and password required"}), 400

    user: Optional[User] = User.query.filter_by(username=username).first()
    if not user or not user.verify_password(password):
        # Do not reveal which field is wrong
        return jsonify({"error": "invalid credentials"}), 401

    token = _create_jwt(user.id)
    resp = make_response(jsonify({"message": "login successful"}))
    _set_auth_cookie(resp, token)
    return resp, 200


@app.route("/logout", methods=["POST"])
def logout() -> Tuple[dict, int]:
    """Invalidate JWT by clearing cookie."""
    resp = make_response(jsonify({"message": "logged out"}))
    _clear_auth_cookie(resp)
    return resp, 200


@app.route("/profile", methods=["GET"])
def profile() -> Tuple[dict, int]:
    """Protected endpoint returning basic user info."""
    if not g.current_user:
        return jsonify({"error": "authentication required"}), 401

    user: User = g.current_user
    return jsonify({"id": user.id, "username": user.username}), 200


# --------------------------------------------------------------------------- #
# Application entry point
# --------------------------------------------------------------------------- #
def create_app() -> Flask:
    """Factory used by external tools (e.g., gunicorn)."""
    with app.app_context():
        db.create_all()
    return app


if __name__ == "__main__":
    # For local development only; use a proper WSGI server in production.
    create_app()
    app.run(host="0.0.0.0", port=5000, debug=False)