import json
import os
import secrets
from hashlib import pbkdf2_hmac
from typing import Dict, Optional
from functools import wraps

from flask import Flask, request, session, redirect, url_for, render_template_string, flash, g

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
SECRET_KEY = secrets.token_hex(32)
USER_DATA_FILE = "users.json"
HASH_ALGORITHM = "sha256"
ITERATIONS = 300_000  # OWASP recommended minimum for PBKDF2-HMAC-SHA256
SALT_LENGTH = 32
TOKEN_BYTES = 64

app = Flask(__name__)
app.secret_key = SECRET_KEY
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
# In production, set SESSION_COOKIE_SECURE = True when using HTTPS


# ---------------------------------------------------------------------------
# Helper functions for user storage (JSON file)
# ---------------------------------------------------------------------------
def load_users() -> Dict[str, Dict]:
    """Load user database from JSON file.

    Returns:
        Dict mapping username -> user data dictionary.
    """
    if not os.path.exists(USER_DATA_FILE):
        return {}
    try:
        with open(USER_DATA_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_users(users: Dict[str, Dict]) -> None:
    """Save user database to JSON file.

    Args:
        users: Dictionary of user records.
    """
    with open(USER_DATA_FILE, "w") as f:
        json.dump(users, f, indent=2)


# ---------------------------------------------------------------------------
# Password hashing using PBKDF2 (from hashlib)
# ---------------------------------------------------------------------------
def hash_password(password: str) -> Dict[str, str]:
    """Hash a password with a random salt and return the hash and salt.

    Args:
        password: The plain-text password.

    Returns:
        Dictionary with keys 'hash' (hex) and 'salt' (hex).
    """
    salt = secrets.token_hex(SALT_LENGTH)
    pwd_hash = pbkdf2_hmac(
        HASH_ALGORITHM,
        password.encode("utf-8"),
        salt.encode("utf-8"),
        ITERATIONS,
    ).hex()
    return {"hash": pwd_hash, "salt": salt}


def verify_password(password: str, stored_hash: str, stored_salt: str) -> bool:
    """Verify a password against a stored PBKDF2 hash.

    Args:
        password: The plain-text password to check.
        stored_hash: The hex-encoded hash from the user record.
        stored_salt: The hex-encoded salt from the user record.

    Returns:
        True if the password matches, False otherwise.
    """
    pwd_hash = pbkdf2_hmac(
        HASH_ALGORITHM,
        password.encode("utf-8"),
        stored_salt.encode("utf-8"),
        ITERATIONS,
    ).hex()
    return pwd_hash == stored_hash


# ---------------------------------------------------------------------------
# Login required decorator
# ---------------------------------------------------------------------------
def login_required(f):
    """Decorator to require an active session for a view.

    Redirects to login page if user is not authenticated.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "username" not in session:
            flash("You must be logged in to view this page.", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.route("/")
def home():
    """Home page. Shows welcome message and login status."""
    username = session.get("username")
    if username:
        return f"<h1>Welcome back, {username}!</h1><a href='/logout'>Logout</a>"
    return "<h1>Login System</h1><a href='/login'>Login</a> | <a href='/register'>Register</a>"


@app.route("/register", methods=["GET", "POST"])
def register():
    """User registration view.

    GET: Show registration form.
    POST: Validate input, create user account (with hashed password), store in file.
    """
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")

        # Input validation
        errors = []
        if not username:
            errors.append("Username is required.")
        if not password:
            errors.append("Password is required.")
        if password != confirm:
            errors.append("Passwords do not match.")
        if len(password) < 8:
            errors.append("Password must be at least 8 characters long.")

        # Check for duplicate username
        users = load_users()
        if username in users:
            errors.append("Username already exists.")

        if errors:
            for err in errors:
                flash(err, "danger")
            return redirect(url_for("register"))

        # Hash password and store user
        pwd_data = hash_password(password)
        users[username] = {
            "hash": pwd_data["hash"],
            "salt": pwd_data["salt"],
        }
        save_users(users)
        flash("Registration successful! Please log in.", "success")
        return redirect(url_for("login"))

    # GET request -> render registration form
    return render_template_string("""
        <h1>Register</h1>
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                <ul>
                {% for category, message in messages %}
                    <li style="color: {{ 'red' if category == 'danger' else 'green' }}">{{ message }}</li>
                {% endfor %}
                </ul>
            {% endif %}
        {% endwith %}
        <form method="POST">
            <p>Username: <input type="text" name="username" required></p>
            <p>Password: <input type="password" name="password" required></p>
            <p>Confirm password: <input type="password" name="confirm" required></p>
            <p><input type="submit" value="Register"></p>
        </form>
        <a href='/login'>Already have an account? Login</a>
    """)


@app.route("/login", methods=["GET", "POST"])
def login():
    """User login view.

    GET: Show login form.
    POST: Validate credentials, create session, redirect to home.
    """
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if not username or not password:
            flash("Username and password are required.", "danger")
            return redirect(url_for("login"))

        users = load_users()
        user = users.get(username)

        if user is None or not verify_password(password, user["hash"], user["salt"]):
            flash("Invalid username or password.", "danger")
            return redirect(url_for("login"))

        # Successful login
        session["username"] = username
        session.permanent = False  # Session expires when browser closes
        flash("Logged in successfully.", "success")
        return redirect(url_for("home"))

    return render_template_string("""
        <h1>Login</h1>
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                <ul>
                {% for category, message in messages %}
                    <li style="color: {{ 'red' if category == 'danger' else 'green' }}">{{ message }}</li>
                {% endfor %}
                </ul>
            {% endif %}
        {% endwith %}
        <form method="POST">
            <p>Username: <input type="text" name="username" required></p>
            <p>Password: <input type="password" name="password" required></p>
            <p><input type="submit" value="Login"></p>
        </form>
        <a href='/register'>Don't have an account? Register</a>
    """)


@app.route("/logout")
def logout():
    """Logout the current user by clearing the session."""
    session.pop("username", None)
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("home"))


@app.route("/protected")
@login_required
def protected():
    """A protected resource that requires authentication."""
    return f"<h1>Protected Area</h1><p>Hello, {session['username']}!</p><a href='/home'>Home</a> | <a href='/logout'>Logout</a>"


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    # Ensure user data file exists
    if not os.path.exists(USER_DATA_FILE):
        with open(USER_DATA_FILE, "w") as f:
            json.dump({}, f)

    # SECURITY NOTE: In production, do not run with debug=True, use a proper
    # production WSGI server, enable HTTPS, and set stronger session cookie settings.
    app.run(debug=True, host="0.0.0.0", port=5000)