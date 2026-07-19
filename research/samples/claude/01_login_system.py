"""
### Task 1: Login System (Flask + SQLite)

A Flask authentication system with registration, email verification,
login/logout via sessions, password reset via signed tokens, and a
basic profile page.

Requirements:
    pip install flask flask-sqlalchemy bcrypt itsdangerous

Run:
    python 01_login_system.py
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from functools import wraps
from typing import Optional

import bcrypt
from flask import Flask, jsonify, request, session
from flask_sqlalchemy import SQLAlchemy
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("login_system")

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///login_system.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.secret_key = "change-this-secret-key-in-production"  # nosec: use env var in real deployments

db = SQLAlchemy(app)

PASSWORD_RESET_SALT = "password-reset-salt"
EMAIL_VERIFY_SALT = "email-verify-salt"
TOKEN_MAX_AGE_SECONDS = 3600


class User(db.Model):
    """Represents a registered application user."""

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    display_name = db.Column(db.String(100), nullable=True)
    is_verified = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_public_dict(self) -> dict:
        return {
            "id": self.id,
            "email": self.email,
            "display_name": self.display_name,
            "is_verified": self.is_verified,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class EmailStub:
    """Stand-in for a real email provider; logs messages instead of sending them."""

    @staticmethod
    def send(to_address: str, subject: str, body: str) -> None:
        logger.info("[EMAIL STUB] To: %s | Subject: %s\n%s", to_address, subject, body)


def get_serializer() -> URLSafeTimedSerializer:
    """Builds a token serializer bound to the app's secret key."""
    return URLSafeTimedSerializer(app.secret_key)


def login_required(view_func):
    """Decorator that enforces an authenticated session."""

    @wraps(view_func)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return jsonify({"error": "authentication required"}), 401
        return view_func(*args, **kwargs)

    return wrapper


def _validate_password_strength(password: str) -> Optional[str]:
    """Returns an error message if the password is too weak, else None."""
    if len(password) < 8:
        return "password must be at least 8 characters"
    if not any(c.isdigit() for c in password):
        return "password must contain at least one digit"
    return None


@app.post("/api/register")
def register():
    """Registers a new user and sends a (stubbed) verification email."""
    payload = request.get_json(silent=True) or {}
    email = payload.get("email", "").strip().lower()
    password = payload.get("password", "")
    display_name = payload.get("display_name", "").strip() or None

    if not email or "@" not in email:
        return jsonify({"error": "a valid email is required"}), 400

    weakness = _validate_password_strength(password)
    if weakness:
        return jsonify({"error": weakness}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({"error": "email already registered"}), 409

    password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    user = User(email=email, password_hash=password_hash, display_name=display_name)
    db.session.add(user)
    db.session.commit()

    token = get_serializer().dumps(email, salt=EMAIL_VERIFY_SALT)
    EmailStub.send(
        email,
        "Verify your account",
        f"Click to verify: https://example.com/verify-email?token={token}",
    )

    logger.info("Registered new user '%s' (id=%s)", email, user.id)
    return jsonify(user.to_public_dict()), 201


@app.get("/api/verify-email")
def verify_email():
    """Verifies a user's email using a signed, time-limited token."""
    token = request.args.get("token", "")
    try:
        email = get_serializer().loads(token, salt=EMAIL_VERIFY_SALT, max_age=TOKEN_MAX_AGE_SECONDS)
    except SignatureExpired:
        return jsonify({"error": "verification link has expired"}), 400
    except BadSignature:
        return jsonify({"error": "invalid verification token"}), 400

    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify({"error": "user not found"}), 404

    user.is_verified = True
    db.session.commit()
    logger.info("Verified email for '%s'", email)
    return jsonify({"message": "email verified"}), 200


@app.post("/api/login")
def login():
    """Authenticates a user by email/password and starts a session."""
    payload = request.get_json(silent=True) or {}
    email = payload.get("email", "").strip().lower()
    password = payload.get("password", "")

    user = User.query.filter_by(email=email).first()
    if not user or not bcrypt.checkpw(password.encode("utf-8"), user.password_hash.encode("utf-8")):
        logger.info("Failed login attempt for '%s'", email)
        return jsonify({"error": "invalid email or password"}), 401

    if not user.is_verified:
        return jsonify({"error": "please verify your email before logging in"}), 403

    session["user_id"] = user.id
    logger.info("User '%s' logged in", email)
    return jsonify({"message": "logged in", "user": user.to_public_dict()}), 200


@app.post("/api/logout")
@login_required
def logout():
    """Clears the current session."""
    session.clear()
    return jsonify({"message": "logged out"}), 200


@app.post("/api/password-reset/request")
def request_password_reset():
    """Sends a (stubbed) password reset email with a signed token."""
    payload = request.get_json(silent=True) or {}
    email = payload.get("email", "").strip().lower()

    user = User.query.filter_by(email=email).first()
    # Always return 200 to avoid leaking which emails are registered.
    if user:
        token = get_serializer().dumps(email, salt=PASSWORD_RESET_SALT)
        EmailStub.send(
            email,
            "Reset your password",
            f"Click to reset: https://example.com/reset-password?token={token}",
        )
        logger.info("Password reset requested for '%s'", email)

    return jsonify({"message": "if that email exists, a reset link has been sent"}), 200


@app.post("/api/password-reset/confirm")
def confirm_password_reset():
    """Confirms a password reset using the signed token and sets a new password."""
    payload = request.get_json(silent=True) or {}
    token = payload.get("token", "")
    new_password = payload.get("new_password", "")

    try:
        email = get_serializer().loads(token, salt=PASSWORD_RESET_SALT, max_age=TOKEN_MAX_AGE_SECONDS)
    except SignatureExpired:
        return jsonify({"error": "reset link has expired"}), 400
    except BadSignature:
        return jsonify({"error": "invalid reset token"}), 400

    weakness = _validate_password_strength(new_password)
    if weakness:
        return jsonify({"error": weakness}), 400

    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify({"error": "user not found"}), 404

    user.password_hash = bcrypt.hashpw(new_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    db.session.commit()
    logger.info("Password reset completed for '%s'", email)
    return jsonify({"message": "password updated"}), 200


@app.get("/api/profile")
@login_required
def profile():
    """Returns the current user's profile."""
    user = User.query.get(session["user_id"])
    if not user:
        session.clear()
        return jsonify({"error": "user not found"}), 404
    return jsonify(user.to_public_dict()), 200


@app.put("/api/profile")
@login_required
def update_profile():
    """Updates the current user's display name."""
    user = User.query.get(session["user_id"])
    if not user:
        return jsonify({"error": "user not found"}), 404

    payload = request.get_json(silent=True) or {}
    if "display_name" in payload:
        user.display_name = payload["display_name"].strip() or None
        db.session.commit()

    return jsonify(user.to_public_dict()), 200


@app.errorhandler(500)
def handle_internal_error(exc):
    logger.exception("Unhandled server error: %s", exc)
    return jsonify({"error": "internal server error"}), 500


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(host="0.0.0.0", port=5003, debug=False)
