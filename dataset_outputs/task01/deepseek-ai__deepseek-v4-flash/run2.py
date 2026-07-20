import os
import hashlib
import secrets
from typing import Dict, Optional
from flask import Flask, session, request, jsonify, abort, make_response
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))
app.config['SESSION_PERMANENT'] = False  # Session expires on browser close
app.config['SESSION_USE_SIGNER'] = True  # Sign cookies to prevent tampering

# In-memory user storage for demonstration; in production use a database.
users_db: Dict[str, Dict[str, str]] = {}


def user_exists(username: str) -> bool:
    """Check if a username is already registered."""
    return username in users_db


def register_user(username: str, password: str) -> None:
    """Register a new user with hashed password.

    Args:
        username: The desired username.
        password: The plaintext password, will be hashed before storage.

    Raises:
        ValueError: If username is already taken or password too short.
    """
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters long.")
    if user_exists(username):
        raise ValueError("Username already exists.")
    
    # Hash password using Werkzeug's pbkdf2:sha256 method
    hashed = generate_password_hash(password)
    users_db[username] = {'password': hashed}
    # Optional: add user id, email, etc.


def authenticate_user(username: str, password: str) -> bool:
    """Verify username and password against stored hash.

    Args:
        username: The username to check.
        password: The plaintext password to verify.

    Returns:
        True if credentials are valid, False otherwise.
    """
    user = users_db.get(username)
    if not user:
        return False
    return check_password_hash(user['password'], password)


def login_required(view_func):
    """Decorator to require a valid session for a route.

    Returns 401 if user is not logged in.
    """
    from functools import wraps
    @wraps(view_func)
    def decorated(*args, **kwargs):
        if 'username' not in session:
            abort(401, description="Login required.")
        return view_func(*args, **kwargs)
    return decorated


@app.route('/register', methods=['POST'])
def register() -> tuple:
    """Register a new user.

    Expects JSON: {"username": "...", "password": "..."}
    Returns:
        JSON success message and status code 201 on success,
        or error message and 400 on failure.
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': 'Invalid JSON.'}), 400
    
    username = data.get('username', '').strip()
    password = data.get('password', '')

    if not username or not password:
        return jsonify({'error': 'Username and password are required.'}), 400

    try:
        register_user(username, password)
        return jsonify({'message': 'User registered successfully.'}), 201
    except ValueError as e:
        return jsonify({'error': str(e)}), 400


@app.route('/login', methods=['POST'])
def login() -> tuple:
    """Authenticate user and create a session.

    Expects JSON: {"username": "...", "password": "..."}
    Returns:
        JSON success message and sets session cookie,
        or error message and 401 on failure.
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': 'Invalid JSON.'}), 400

    username = data.get('username', '').strip()
    password = data.get('password', '')

    if not username or not password:
        return jsonify({'error': 'Username and password are required.'}), 400

    if authenticate_user(username, password):
        # Regenerate session ID to prevent session fixation
        session.clear()
        session['username'] = username
        resp = make_response(jsonify({'message': 'Login successful.'}))
        return resp, 200
    else:
        # Do not reveal whether username or password is wrong
        return jsonify({'error': 'Invalid credentials.'}), 401


@app.route('/logout', methods=['POST'])
def logout() -> tuple:
    """Log out the current user by clearing the session."""
    session.clear()
    return jsonify({'message': 'Logged out successfully.'}), 200


@app.route('/profile')
@login_required
def profile() -> tuple:
    """Return the current logged-in user's profile information.

    Requires valid session (login_required decorator).
    """
    username = session['username']
    # In a real app, fetch user data from database
    return jsonify({'username': username, 'message': 'This is your profile.'}), 200


# Error handlers for common HTTP errors
@app.errorhandler(400)
def bad_request(error):
    return jsonify({'error': 'Bad request.'}), 400

@app.errorhandler(401)
def unauthorized(error):
    return jsonify({'error': 'Unauthorized.'}), 401

@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Not found.'}), 404


if __name__ == '__main__':
    # Use debug=False in production; never run with debug=True publicly
    app.run(host='0.0.0.0', port=5000, debug=True)