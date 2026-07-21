"""
User Authentication Module

This module implements a secure user authentication system with registration, login, logout,
and session management using Flask and bcrypt. It follows security best practices including
password hashing, secure session cookies, and input validation.

Dependencies:
    - Flask (web framework)
    - bcrypt (password hashing)
    - typing (type hints)

Usage:
    Run this module directly to start the development server:
        python auth_module.py

    Then access the API endpoints:
        POST /register - Register a new user
        POST /login    - Login and create session
        POST /logout   - Logout and destroy session
        GET  /profile  - Access protected resource (requires authentication)
"""

import os
import secrets
from typing import Dict, Tuple, Optional, Any
from dataclasses import dataclass
from functools import wraps

from flask import Flask, request, jsonify, session, Response
import bcrypt


@dataclass
class User:
    """Represents a user account with securely hashed password."""
    username: str
    password_hash: bytes
    email: str


class AuthError(Exception):
    """Custom exception for authentication errors with HTTP status codes."""
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class UserStore:
    """
    In-memory user storage with thread-safe operations.
    In production, replace with a proper database (PostgreSQL, SQLite, etc.).
    """
    
    def __init__(self) -> None:
        self._users: Dict[str, User] = {}
        self._lock = __import__('threading').Lock()
    
    def add_user(self, username: str, password_hash: bytes, email: str) -> None:
        """
        Add a new user to the store.
        
        Args:
            username: Unique username
            password_hash: Bcrypt hashed password
            email: User's email address
            
        Raises:
            AuthError: If username already exists
        """
        with self._lock:
            if username in self._users:
                raise AuthError("Username already exists", 409)
            self._users[username] = User(username, password_hash, email)
    
    def get_user(self, username: str) -> Optional[User]:
        """
        Retrieve a user by username.
        
        Args:
            username: Username to look up
            
        Returns:
            User object if found, None otherwise
        """
        with self._lock:
            return self._users.get(username)
    
    def verify_user(self, username: str, password: str) -> bool:
        """
        Verify user credentials.
        
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
    """
    Create and configure the Flask application.
    
    Returns:
        Configured Flask application instance
    """
    app = Flask(__name__)
    
    # Security configuration
    app.config.update(
        SECRET_KEY=os.environ.get('SECRET_KEY', secrets.token_hex(32)),
        SESSION_COOKIE_SECURE=True,       # Requires HTTPS in production
        SESSION_COOKIE_HTTPONLY=True,     # Prevent XSS attacks
        SESSION_COOKIE_SAMESITE='Lax',    # CSRF protection
        PERMANENT_SESSION_LIFETIME=3600,  # 1 hour session timeout
    )
    
    # Initialize user store
    user_store = UserStore()
    
    def hash_password(password: str) -> bytes:
        """
        Hash a password using bcrypt with a secure work factor.
        
        Args:
            password: Plaintext password to hash
            
        Returns:
            Bcrypt hashed password as bytes
        """
        salt = bcrypt.gensalt(rounds=12)
        return bcrypt.hashpw(password.encode('utf-8'), salt)
    
    def validate_registration_data(data: Dict[str, Any]) -> Tuple[str, str, str]:
        """
        Validate registration input data.
        
        Args:
            data: Request JSON data
            
        Returns:
            Tuple of (username, password, email)
            
        Raises:
            AuthError: If validation fails
        """
        username = data.get('username', '').strip()
        password = data.get('password', '')
        email = data.get('email', '').strip()
        
        if not username:
            raise AuthError("Username is required", 400)
        if not password:
            raise AuthError("Password is required", 400)
        if len(password) < 8:
            raise AuthError("Password must be at least 8 characters", 400)
        if not email or '@' not in email:
            raise AuthError("Valid email is required", 400)
        if len(username) > 50:
            raise AuthError("Username too long (max 50 characters)", 400)
            
        return username, password, email
    
    def login_required(f):
        """
        Decorator to protect routes requiring authentication.
        
        Args:
            f: View function to decorate
            
        Returns:
            Wrapped function that checks authentication
        """
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                raise AuthError("Authentication required", 401)
            return f(*args, **kwargs)
        return decorated_function
    
    @app.errorhandler(AuthError)
    def handle_auth_error(error: AuthError) -> Tuple[Response, int]:
        """
        Global error handler for authentication errors.
        
        Args:
            error: AuthError instance
            
        Returns:
            JSON error response with appropriate status code
        """
        response = jsonify({'error': error.message})
        response.status_code = error.status_code
        return response
    
    @app.errorhandler(Exception)
    def handle_generic_error(error: Exception) -> Tuple[Response, int]:
        """
        Global error handler for unexpected errors.
        
        Args:
            error: Exception instance
            
        Returns:
            JSON error response with 500 status code
        """
        app.logger.error(f"Unexpected error: {error}", exc_info=True)
        response = jsonify({'error': 'Internal server error'})
        response.status_code = 500
        return response
    
    @app.route('/register', methods=['POST'])
    def register() -> Tuple[Response, int]:
        """
        Register a new user account.
        
        Expected JSON payload:
            {
                "username": "string",
                "password": "string",
                "email": "string"
            }
            
        Returns:
            JSON response with success message and 201 status code
            
        Raises:
            AuthError: If validation fails or username exists
        """
        if not request.is_json:
            raise AuthError("Request must be JSON", 400)
            
        username, password, email = validate_registration_data(request.get_json())
        password_hash = hash_password(password)
        
        user_store.add_user(username, password_hash, email)
        
        return jsonify({
            'message': 'User registered successfully',
            'username': username
        }), 201
    
    @app.route('/login', methods=['POST'])
    def login() -> Tuple[Response, int]:
        """
        Authenticate user and create session.
        
        Expected JSON payload:
            {
                "username": "string",
                "password": "string"
            }
            
        Returns:
            JSON response with success message and 200 status code
            
        Raises:
            AuthError: If credentials are invalid
        """
        if not request.is_json:
            raise AuthError("Request must be JSON", 400)
            
        data = request.get_json()
        username = data.get('username', '').strip()
        password = data.get('password', '')
        
        if not username or not password:
            raise AuthError("Username and password are required", 400)
        
        if not user_store.verify_user(username, password):
            # Use generic message to prevent user enumeration
            raise AuthError("Invalid credentials", 401)
        
        # Create secure session
        session.permanent = True
        session['user_id'] = username
        session['csrf_token'] = secrets.token_hex(16)
        
        return jsonify({
            'message': 'Login successful',
            'username': username
        }), 200
    
    @app.route('/logout', methods=['POST'])
    def logout() -> Tuple[Response, int]:
        """
        Destroy user session and log out.
        
        Returns:
            JSON response with success message and 200 status code
        """
        session.clear()
        return jsonify({'message': 'Logout successful'}), 200
    
    @app.route('/profile', methods=['GET'])
    @login_required
    def profile() -> Tuple[Response, int]:
        """
        Access protected user profile information.
        
        Requires valid session cookie.
        
        Returns:
            JSON response with user profile data and 200 status code
        """
        username = session['user_id']
        user = user_store.get_user(username)
        
        if not user:
            raise AuthError("User not found", 404)
            
        return jsonify({
            'username': user.username,
            'email': user.email
        }), 200
    
    @app.route('/health', methods=['GET'])
    def health_check() -> Tuple[Response, int]:
        """
        Health check endpoint for monitoring.
        
        Returns:
            JSON response with status and 200 status code
        """
        return jsonify({'status': 'healthy'}), 200
    
    return app


if __name__ == '__main__':
    # Development server - use proper WSGI server (gunicorn, uwsgi) in production
    app = create_app()
    app.run(
        host='0.0.0.0',
        port=int(os.environ.get('PORT', 5000)),
        debug=os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    )