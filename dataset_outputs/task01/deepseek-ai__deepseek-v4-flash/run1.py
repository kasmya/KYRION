import re
from typing import Optional, Dict, Tuple

import bcrypt
from flask import Flask, request, jsonify, session
from werkzeug.security import safe_str_cmp
from datetime import timedelta

app = Flask(__name__)
app.secret_key = 'CHANGE_ME_TO_A_STRONG_RANDOM_SECRET'
app.permanent_session_lifetime = timedelta(hours=1)

# In-memory user store (for demonstration only; use a database in production)
users: Dict[str, Dict[str, str]] = {}  # username -> {password_hash, email?}

def hash_password(password: str) -> str:
    """Hash a password with a random salt using bcrypt."""
    if not password or not isinstance(password, str):
        raise ValueError("Password must be a non-empty string")
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')

def verify_password(password: str, hashed: str) -> bool:
    """Verify a password against its bcrypt hash."""
    try:
        return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
    except (ValueError, AttributeError):
        return False

def validate_email(email: str) -> bool:
    """Simple email format validation (not exhaustive)."""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

@app.route('/register', methods=['POST'])
def register() -> Tuple[Dict, int]:
    """
    Register a new user.
    Expects JSON: { "username": "...", "password": "...", "email": "..." (optional) }
    Returns 201 on success, 400 on validation error, 409 if username exists.
    """
    data = request.get_json(silent=True)
    if not data:
        return {"error": "Request must contain JSON data"}, 400

    username = data.get('username', '').strip()
    password = data.get('password', '')
    email = data.get('email', '').strip()

    if not username or not password:
        return {"error": "Username and password are required"}, 400

    if len(password) < 8:
        return {"error": "Password must be at least 8 characters long"}, 400

    if email and not validate_email(email):
        return {"error": "Invalid email format"}, 400

    if username in users:
        return {"error": "Username already exists"}, 409

    try:
        hashed = hash_password(password)
    except ValueError as e:
        return {"error": str(e)}, 400

    users[username] = {
        "password_hash": hashed,
        "email": email if email else None
    }
    return {"message": "User registered successfully"}, 201

@app.route('/login', methods=['POST'])
def login() -> Tuple[Dict, int]:
    """
    Authenticate a user and start a session.
    Expects JSON: { "username": "...", "password": "..." }
    Returns 200 with user info on success, 401 on invalid credentials.
    """
    data = request.get_json(silent=True)
    if not data:
        return {"error": "Request must contain JSON data"}, 400

    username = data.get('username', '').strip()
    password = data.get('password', '')

    if not username or not password:
        return {"error": "Username and password are required"}, 400

    user = users.get(username)
    if not user:
        # Use constant-time comparison to avoid user enumeration (though we already do simple existence check;
        # for further security consider dummy comparison with a fake hash)
        return {"error": "Invalid username or password"}, 401

    if not verify_password(password, user['password_hash']):
        return {"error": "Invalid username or password"}, 401

    # Regenerate session ID to prevent session fixation
    session.permanent = True
    session['user_id'] = username
    # Optional: store role or other data (avoid storing password)
    return {
        "message": "Login successful",
        "user": {"username": username, "email": user.get("email")}
    }, 200

@app.route('/logout', methods=['POST'])
def logout() -> Tuple[Dict, int]:
    """
    Log out the current user by clearing the session.
    Returns 200 regardless (no error if not logged in).
    """
    session.clear()
    return {"message": "Logged out successfully"}, 200

@app.route('/protected', methods=['GET'])
def protected() -> Tuple[Dict, int]:
    """
    Example protected endpoint that requires a valid session.
    Returns user info or 401 if not authenticated.
    """
    user_id = session.get('user_id')
    if not user_id:
        return {"error": "Authentication required"}, 401

    user = users.get(user_id)
    if not user:
        # Session data is invalid (user deleted)
        session.clear()
        return {"error": "User not found"}, 401

    return {
        "message": "Access granted",
        "user": {"username": user_id, "email": user.get("email")}
    }, 200

@app.before_request
def ensure_session_permanent() -> None:
    """Make sessions permanent (respects lifetime)."""
    session.permanent = True

if __name__ == '__main__':
    # In production, use environment variable for secret key and HTTPS.
    app.run(debug=True)