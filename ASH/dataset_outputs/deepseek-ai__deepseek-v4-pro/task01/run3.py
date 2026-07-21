"""
User authentication module providing registration, login, logout, and session management.

Uses bcrypt for password hashing and Flask sessions or JWT for session management.
Implements security best practices including input validation, secure defaults,
and protection against common authentication vulnerabilities.
"""

import re
import secrets
import hashlib
import hmac
import time
import logging
from typing import Dict, Optional, Tuple, Any, Union
from datetime import datetime, timedelta
from functools import wraps

# Third-party imports
import bcrypt
import jwt
from flask import Flask, request, jsonify, session, g, current_app

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class UserAuth:
    """
    Main authentication handler providing user management and session control.
    """

    def __init__(self, app: Flask, secret_key: Optional[str] = None,
                 session_type: str = "flask", token_expiry_hours: int = 24):
        """
        Initialize authentication system.

        Args:
            app: Flask application instance
            secret_key: Secret key for JWT or Flask sessions (auto-generated if not provided)
            session_type: "flask" for server-side sessions, "jwt" for token-based auth
            token_expiry_hours: JWT token expiration time in hours

        Raises:
            UserAuthError: If invalid session_type is provided
        """
        self.app = app
        self.session_type = session_type.lower()
        if self.session_type not in ("flask", "jwt"):
            raise UserAuthError("session_type must be 'flask' or 'jwt'")

        self.secret_key = secret_key or os.urandom(32).hex()
        self.token_expiry_hours = token_expiry_hours

        # In-memory user store (replace with database in production)
        self._users: dict[str, dict[str, Any]] = {}

        # Brute-force protection
        self._login_attempts: dict[str, dict[str, Union[int, float]]] = {}
        self._max_attempts = 5
        self._lockout_duration = 300  # 5 minutes

        # Set Flask secret key for session management
        if self.session_type == "flask":
            app.secret_key = self.secret_key

    def _hash_password(self, password: str) -> str:
        """
        Hash a password using bcrypt with a random salt.

        Args:
            password: Plain text password

        Returns:
            Hashed password string

        Raises:
            ValueError: If password is empty or None
        """
        if not password:
            raise ValueError("Password cannot be empty")
        return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    def _verify_password(self, password: str, hashed: str) -> bool:
        """
        Verify a password against its bcrypt hash.

        Args:
            password: Plain text password
            hashed: Bcrypt hashed password

        Returns:
            True if password matches, False otherwise
        """
        try:
            return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
        except ValueError:
            return False

    def _validate_username(self, username: str) -> bool:
        """
        Validate username format.

        Args:
            username: Username to validate

        Returns:
            True if username is valid, False otherwise
        """
        if not username or len(username) < 3 or len(username) > 50:
            return False
        return bool(re.match(r'^[a-zA-Z0-9_\-\.]+$', username))

    def _validate_password_strength(self, password: str) -> Tuple[bool, str]:
        """
        Validate password strength.

        Args:
            password: Password to validate

        Returns:
            Tuple of (is_valid, message)
        """
        if not password:
            return False, "Password cannot be empty"
        if len(password) < 8:
            return False, "Password must be at least 8 characters long"
        if len(password) > 128:
            return False, "Password must be at most 128 characters long"
        if not re.search(r'[A-Z]', password):
            return False, "Password must contain at least one uppercase letter"
        if not re.search(r'[a-z]', password):
            return False, "Password must contain at least one lowercase letter"
        if not re.search(r'[0-9]', password):
            return False, "Password must contain at least one digit"
        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
            return False, "Password must contain at least one special character"
        return True, "Password is strong"

    def _is_account_locked(self, username: str) -> bool:
        """
        Check if an account is temporarily locked due to failed attempts.

        Args:
            username: Username to check

        Returns:
            True if account is locked, False otherwise
        """
        if username not in self._login_attempts:
            return False

        attempts = self._login_attempts[username]
        if attempts["count"] >= self._max_attempts:
            elapsed = time.time() - attempts["last_attempt"]
            if elapsed < self._lockout_duration:
                return True
            else:
                # Reset attempts after lockout period
                self._login_attempts.pop(username, None)
        return False

    def _record_failed_attempt(self, username: str) -> None:
        """
        Record a failed login attempt for brute-force protection.

        Args:
            username: Username that failed authentication
        """
        if username not in self._login_attempts:
            self._login_attempts[username] = {"count": 0, "last_attempt": 0}
        self._login_attempts[username]["count"] += 1
        self._login_attempts[username]["last_attempt"] = time.time()

    def _reset_login_attempts(self, username: str) -> None:
        """
        Reset login attempts for a username after successful login.

        Args:
            username: Username to reset
        """
        self._login_attempts.pop(username, None)

    def register(self, username: str, password: str) -> Tuple[bool, str]:
        """
        Register a new user.

        Args:
            username: Desired username
            password: User password

        Returns:
            Tuple of (success, message)
        """
        # Validate username
        if not self._validate_username(username):
            return False, "Invalid username format. Use 3-50 alphanumeric characters, dots, underscores, or hyphens."

        # Check if username already exists
        if username in self._users:
            return False, "Username already exists"

        # Validate password strength
        is_strong, msg = self._validate_password_strength(password)
        if not is_strong:
            return False, msg

        try:
            # Hash password and store user
            hashed_password = self._hash_password(password)
            self._users[username] = {
                "username": username,
                "password": hashed_password,
                "created_at": datetime.utcnow().isoformat(),
                "last_login": None
            }
            logger.info(f"User '{username}' registered successfully")
            return True, "Registration successful"
        except Exception as e:
            logger.error(f"Registration error: {e}")
            return False, "Registration failed due to server error"

    def login(self, username: str, password: str) -> Tuple[bool, str, Optional[Any]]:
        """
        Authenticate a user and create a session.

        Args:
            username: Username
            password: Password

        Returns:
            Tuple of (success, message, token_or_session_data)
        """
        # Check for blank inputs
        if not username or not password:
            return False, "Username and password are required", None

        # Check if account is locked
        if self._is_account_locked(username):
            remaining = int(self._lockout_duration - (time.time() - self._login_attempts.get(username, {}).get("last_attempt", 0)))
            return False, f"Account temporarily locked. Try again in {max(0, remaining)} seconds.", None

        # Verify credentials
        user = self._users.get(username)
        if not user or not self._verify_password(password, user["password"]):
            self._record_failed_attempt(username)
            logger.warning(f"Failed login attempt for username '{username}'")
            return False, "Invalid username or password", None

        # Successful login
        self._reset_login_attempts(username)
        user["last_login"] = datetime.utcnow().isoformat()
        logger.info(f"User '{username}' logged in successfully")

        if self.session_type == "flask":
            # Create Flask session
            session["user"] = username
            session["login_time"] = datetime.utcnow().isoformat()
            session.permanent = True
            return True, "Login successful", {"username": username}
        else:
            # Create JWT token
            token = self._create_jwt_token(username)
            return True, "Login successful", {"token": token, "username": username}

    def logout(self) -> Tuple[bool, str]:
        """
        Logout the current user and invalidate session.

        Returns:
            Tuple of (success, message)
        """
        try:
            if self.session_type == "flask":
                # Clear Flask session
                session.clear()
            # For JWT, token invalidation should be handled client-side
            # Optionally maintain a token blacklist
            logger.info("User logged out")
            return True, "Logout successful"
        except Exception as e:
            logger.error(f"Logout error: {e}")
            return False, "Logout failed"

    def _create_jwt_token(self, username: str) -> str:
        """
        Create a JWT token for authenticated user.

        Args:
            username: Authenticated username

        Returns:
            JWT token string
        """
        payload = {
            "username": username,
            "exp": datetime.utcnow() + timedelta(hours=self.token_expiry_hours),
            "iat": datetime.utcnow(),
            "jti": secrets.token_hex(16)  # Unique token ID
        }
        return jwt.encode(payload, self.secret_key, algorithm="HS256")

    def verify_jwt_token(self, token: str) -> Optional[dict]:
        """
        Verify and decode a JWT token.

        Args:
            token: JWT token string

        Returns:
            Decoded token payload if valid, None otherwise
        """
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=["HS256"])
            # Verify user still exists
            if payload.get("username") in self._users:
                return payload
            return None
        except jwt.ExpiredSignatureError:
            logger.warning("Expired JWT token")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid JWT token: {e}")
            return None

    def get_current_user(self) -> Optional[str]:
        """
        Get the currently authenticated user.

        Returns:
            Username if authenticated, None otherwise
        """
        if self.session_type == "flask":
            return session.get("user")
        else:
            # Extract token from Authorization header
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                token = auth_header.split(" ")[1]
                payload = self.verify_jwt_token(token)
                if payload:
                    return payload.get("username")
            return None

    def require_auth(self, f):
        """
        Decorator to protect routes requiring authentication.

        Args:
            f: The view function to decorate

        Returns:
            Decorated function
        """
        @wraps(f)
        def decorated(*args, **kwargs):
            user = self.get_current_user()
            if not user:
                if self.session_type == "flask":
                    return {"error": "Authentication required"}, 401
                else:
                    return {"error": "Invalid or expired token"}, 401
            return f(*args, **kwargs)
        return decorated

    def change_password(self, username: str, current_password: str,
                        new_password: str) -> Tuple[bool, str]:
        """
        Change a user's password.

        Args:
            username: Username
            current_password: Current password for verification
            new_password: New password

        Returns:
            Tuple of (success, message)
        """
        user = self._users.get(username)
        if not user:
            return False, "User not found"

        # Verify current password
        if not self._verify_password(current_password, user["password"]):
            return False, "Current password is incorrect"

        # Validate new password strength
        is_valid, msg = self._validate_password_strength(new_password)
        if not is_valid:
            return False, msg

        # Check that new password is different from current
        if self._verify_password(new_password, user["password"]):
            return False, "New password must be different from current password"

        try:
            # Update password
            user["password"] = self._hash_password(new_password)
            logger.info(f"Password changed for user '{username}'")
            return True, "Password changed successfully"
        except Exception as e:
            logger.error(f"Password change error: {e}")
            return False, "Failed to change password"


# Flask route examples (for reference, not automatically registered)
def setup_auth_routes(app: Flask, auth: UserAuth) -> None:
    """
    Register authentication routes with Flask application.

    Args:
        app: Flask application instance
        auth: UserAuth instance
    """

    @app.route("/register", methods=["POST"])
    def register_route():
        """Register a new user."""
        data = request.get_json()
        if not data:
            return {"error": "Invalid request"}, 400

        username = data.get("username", "").strip()
        password = data.get("password", "")

        success, message = auth.register(username, password)
        if success:
            return {"message": message}, 201
        return {"error": message}, 400

    @app.route("/login", methods=["POST"])
    def login_route():
        """Login user."""
        data = request.get_json()
        if not data:
            return {"error": "Invalid request"}, 400

        username = data.get("username", "").strip()
        password = data.get("password", "")

        success, message, token_data = auth.login(username, password)
        if success:
            return {"message": message, "data": token_data}, 200
        return {"error": message}, 401

    @app.route("/logout", methods=["POST"])
    def logout_route():
        """Logout user."""
        success, message = auth.logout()
        if success:
            return {"message": message}, 200
        return {"error": message}, 500

    @app.route("/profile", methods=["GET"])
    @auth.require_auth
    def profile_route():
        """Get current user profile (protected route)."""
        username = auth.get_current_user()
        return {"username": username}, 200

    @app.route("/change-password", methods=["POST"])
    @auth.require_auth
    def change_password_route():
        """Change user password (protected route)."""
        data = request.get_json()
        if not data:
            return {"error": "Invalid request"}, 400

        username = auth.get_current_user()
        current_password = data.get("current_password", "")
        new_password = data.get("new_password", "")

        success, message = auth.change_password(username, current_password, new_password)
        if success:
            return {"message": message}, 200
        return {"error": message}, 400