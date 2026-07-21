"""
User authentication module providing registration, login, logout, and session management.

This module implements a secure authentication system using Flask for web framework,
bcrypt for password hashing, and Flask sessions for session management.
It follows security best practices including secure password storage, session protection,
and proper error handling.

Dependencies:
    - flask: Web framework for routing and session management
    - bcrypt: Password hashing library
    - typing: Type hints support

Usage:
    Run this module directly to start the development server:
        python auth_module.py

    Then access endpoints:
        POST /register - Register new user
        POST /login - Login user
        POST /logout - Logout user
        GET /profile - Protected route requiring authentication
"""

from __future__ import annotations

import secrets
from typing import Dict, Tuple, Optional, Any
from dataclasses import dataclass
from functools import wraps

from flask import Flask, request, session, jsonify, Response
import bcrypt


@dataclass
class User:
    """Represents a user account with securely stored credentials."""
    username: str
    password_hash: bytes
    email: str


class AuthError(Exception):
    """Base exception for authentication errors."""
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class ValidationError(AuthError):
    """Raised when input validation fails."""
    pass


class AuthenticationError(AuthError):
    """Raised when authentication fails."""
    def __init__(self, message: str = "Invalid credentials") -> None:
        super().__init__(message, 401)


class AuthorizationError(AuthError):
    """Raised when authorization fails."""
    def __init__(self, message: str = "Authentication required") -> None:
        super().__init__(message, 403)


class UserStore:
    """In-memory user storage with thread-safe operations.
    
    Note: In production, replace with a proper database implementation.
    """
    
    def __init__(self) -> None:
        self._users: Dict[str, User] = {}
        self._lock = __import__('threading').Lock()
    
    def add_user(self, username: str, password_hash: bytes, email: str) -> None:
        """Add a new user to the store.
        
        Args:
            username: Unique username
            password_hash: Bcrypt hashed password
            email: User's email address
            
        Raises:
            ValidationError: If username already exists
        """
        with self._lock:
            if username in self._users:
                raise ValidationError("Username already exists")
            self._users[username] = User(username, password_hash, email)
    
    def get_user(self, username: str) -> Optional[User]:
        """Retrieve a user by username.
        
        Args:
            username: Username to look up
            
        Returns:
            User object if found, None otherwise
        """
        with self._lock:
            return self._users.get(username)
    
    def verify_user(self, username: str, password: str) -> bool:
        """Verify user credentials.
        
        Args:
            username: Username to verify
            password: Plaintext password to check
            
        Returns:
            True if credentials are valid, False otherwise
        """
        user = self.get_user(username)
        if not user:
            return False
        try:
            return bcrypt.checkpw(password.encode('utf-8'), user.password_hash)
        except (ValueError, TypeError):
            return False


def create_app() -> Flask:
    """Create and configure the Flask application.
    
    Returns:
        Configured Flask application instance
    """
    app = Flask(__name__)
    
    # Security configuration
    app.config.update(
        SECRET_KEY=secrets.token_hex(32),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SECURE=False,  # Set to True in production with HTTPS
        SESSION_COOKIE_SAMESITE='Lax',
        PERMANENT_SESSION_LIFETIME=3600,  # 1 hour
    )
    
    # Initialize user store
    app.user_store = UserStore()
    
    # Register routes
    register_routes(app)
    
    return app


def register_routes(app: Flask) -> None:
    """Register all authentication routes with the Flask app.
    
    Args:
        app: Flask application instance
    """
    app.add_url_rule('/register', 'register', register, methods=['POST'])
    app.add_url_rule('/login', 'login', login, methods=['POST'])
    app.add_url_rule('/logout', 'logout', logout, methods=['POST'])
    app.add_url_rule('/profile', 'profile', profile, methods=['GET'])


def validate_registration_data(data: Dict[str, Any]) -> Tuple[str, str, str]:
    """Validate registration request data.
    
    Args:
        data: Request JSON data
        
    Returns:
        Tuple of (username, password, email)
        
    Raises:
        ValidationError: If validation fails
    """
    if not data:
        raise ValidationError("Request body must be JSON")
    
    username = data.get('username', '').strip()
    password = data.get('password', '')
    email = data.get('email', '').strip()
    
    if not username:
        raise ValidationError("Username is required")
    if len(username) < 3:
        raise ValidationError("Username must be at least 3 characters")
    if not username.isalnum():
        raise ValidationError("Username must be alphanumeric")
    
    if not password:
        raise ValidationError("Password is required")
    if len(password) < 8:
        raise ValidationError("Password must be at least 8 characters")
    if not any(c.isupper() for c in password):
        raise ValidationError("Password must contain at least one uppercase letter")
    if not any(c.islower() for c in password):
        raise ValidationError("Password must contain at least one lowercase letter")
    if not any(c.isdigit() for c in password):
        raise ValidationError("Password must contain at least one digit")
    
    if not email:
        raise ValidationError("Email is required")
    if '@' not in email or '.' not in email.split('@')[-1]:
        raise ValidationError("Invalid email format")
    
    return username, password, email


def validate_login_data(data: Dict[str, Any]) -> Tuple[str, str]:
    """Validate login request data.
    
    Args:
        data: Request JSON data
        
    Returns:
        Tuple of (username, password)
        
    Raises:
        ValidationError: If validation fails
    """
    if not data:
        raise ValidationError("Request body must be JSON")
    
    username = data.get('username', '').strip()
    password = data.get('password', '')
    
    if not username:
        raise ValidationError("Username is required")
    if not password:
        raise ValidationError("Password is required")
    
    return username, password


def hash_password(password: str) -> bytes:
    """Hash a password using bcrypt.
    
    Args:
        password: Plaintext password
        
    Returns:
        Bcrypt hashed password as bytes
    """
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password.encode('utf-8'), salt)


def login_required(f: callable) -> callable:
    """Decorator to require authentication for a route.
    
    Args:
        f: View function to decorate
        
    Returns:
        Decorated function
    """
    @wraps(f)
    def decorated_function(*args: Any, **kwargs: Any) -> Response:
        if 'user_id' not in session:
            raise AuthorizationError()
        return f(*args, **kwargs)
    return decorated_function


def handle_auth_error(error: AuthError) -> Response:
    """Handle authentication errors and return JSON response.
    
    Args:
        error: Authentication error instance
        
    Returns:
        JSON error response with appropriate status code
    """
    response = jsonify({'error': error.message})
    response.status_code = error.status_code
    return response


def register() -> Response:
    """Register a new user account.
    
    Expected JSON payload:
        {
            "username": "string",
            "password": "string",
            "email": "string"
        }
        
    Returns:
        JSON response with success message or error
    """
    try:
        data = request.get_json()
        username, password, email = validate_registration_data(data)
        
        password_hash = hash_password(password)
        
        # Access user store from app context
        user_store = request.app.user_store
        user_store.add_user(username, password_hash, email)
        
        return jsonify({
            'message': 'User registered successfully',
            'username': username
        }), 201
        
    except ValidationError as e:
        return handle_auth_error(e)
    except Exception as e:
        # Log the error in production
        return handle_auth_error(AuthError("Registration failed", 500))


def login() -> Response:
    """Authenticate user and create session.
    
    Expected JSON payload:
        {
            "username": "string",
            "password": "string"
        }
        
    Returns:
        JSON response with success message or error
    """
    try:
        data = request.get_json()
        username, password = validate_login_data(data)
        
        user_store = request.app.user_store
        if not user_store.verify_user(username, password):
            raise AuthenticationError()
        
        # Create secure session
        session.permanent = True
        session['user_id'] = username
        session['csrf_token'] = secrets.token_hex(16)
        
        return jsonify({
            'message': 'Login successful',
            'username': username
        }), 200
        
    except (ValidationError, AuthenticationError) as e:
        return handle_auth_error(e)
    except Exception as e:
        return handle_auth_error(AuthError("Login failed", 500))


def logout() -> Response:
    """Logout user and destroy session.
    
    Returns:
        JSON response with success message
    """
    try:
        session.clear()
        return jsonify({'message': 'Logout successful'}), 200
    except Exception as e:
        return handle_auth_error(AuthError("Logout failed", 500))


@login_required
def profile() -> Response:
    """Get authenticated user's profile information.
    
    Requires valid session.
    
    Returns:
        JSON response with user profile data
    """
    try:
        username = session['user_id']
        user_store = request.app.user_store
        user = user_store.get_user(username)
        
        if not user:
            raise AuthorizationError("User not found")
        
        return jsonify({
            'username': user.username,
            'email': user.email
        }), 200
        
    except AuthorizationError as e:
        return handle_auth_error(e)
    except Exception as e:
        return handle_auth_error(AuthError("Profile retrieval failed", 500))


# Register error handlers
def register_error_handlers(app: Flask) -> None:
    """Register error handlers for authentication errors.
    
    Args:
        app: Flask application instance
    """
    app.errorhandler(ValidationError)(handle_auth_error)
    app.errorhandler(AuthenticationError)(handle_auth_error)
    app.errorhandler(AuthorizationError)(handle_auth_error)


# Create app instance
app = create_app()
register_error_handlers(app)


if __name__ == '__main__':
    # Development server - not for production use
    app.run(debug=True, host='0.0.0.0', port=5000)