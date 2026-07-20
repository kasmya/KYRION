"""
A simple Flask-based authentication system with:
- User registration
- Password hashing (bcrypt)
- Session management via Flask signed cookies
- Login & logout endpoints
- Type hints, docstrings and error handling
"""

import os
import sqlite3
from datetime import datetime, timedelta
from typing import Optional, Tuple

import bcrypt
from flask import (
    Flask,
    abort,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------
DATABASE = os.getenv("FLASK_AUTH_DB", "auth.db")
SECRET_KEY = os.getenv("FLASK_SECRET_KEY", os.urandom(32).hex())
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
PERMANENT_SESSION_LIFETIME = timedelta(days=7)


def get_db() -> sqlite3.Connection:
    """Open a new database connection if there is none yet for the current app context."""
    if "db" not in g:
        conn = sqlite3.connect(DATABASE, detect_types=sqlite3.PARSE_DECLTYPES)
        conn.row_factory = sqlite3.Row
        g.db = conn
    return g.db


def close_db(e: Optional[BaseException] = None) -> None:
    """Close the database connection if it exists."""
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db() -> None:
    """Create the users table if it does not exist."""
    db = get_db()
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash BLOB NOT NULL,
            created_at TIMESTAMP NOT NULL
        )
        """
    )
    db.commit()


# ----------------------------------------------------------------------
# Flask App
# ----------------------------------------------------------------------
app = Flask(__name__)
app.secret_key = SECRET_KEY
app.config.update(
    SESSION_COOKIE_HTTPONLY=SESSION_COOKIE_HTTPONLY,
    SESSION_COOKIE_SAMESITE=SESSION_COOKIE_SAMESITE,
    PERMANENT_SESSION_LIFETIME=PERMANENT_SESSION_LIFETIME,
)

app.teardown_appcontext(close_db)


# ----------------------------------------------------------------------
# Helper Functions
# ----------------------------------------------------------------------
def hash_password(password: str) -> bytes:
    """
    Hash a password using bcrypt.

    Args:
        password: The plain text password.

    Returns:
        The bcrypt hash.
    """
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())


def verify_password(password: str, hashed: bytes) -> bool:
    """
    Verify a password against an existing hash.

    Args:
        password: The plain text password.
        hashed: The stored bcrypt hash.

    Returns:
        True if the password matches, False otherwise.
    """
    return bcrypt.checkpw(password.encode("utf-8"), hashed)


def get_user_by_username(username: str) -> Optional[sqlite3.Row]:
    """
    Retrieve a user row by username.

    Args:
        username: The username to look up.

    Returns:
        A row object or None if not found.
    """
    db = get_db()
    cur = db.execute("SELECT * FROM users WHERE username = ?", (username,))
    return cur.fetchone()


def create_user(username: str, password: str) -> Tuple[bool, str]:
    """
    Register a new user.

    Args:
        username: Desired username.
        password: Plain text password.

    Returns:
        (success, message) tuple.
    """
    if get_user_by_username(username):
        return False, "Username already taken."

    password_hash = hash_password(password)
    db = get_db()
    try:
        db.execute(
            "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
            (username, password_hash, datetime.utcnow()),
        )
        db.commit()
        return True, "User created successfully."
    except sqlite3.IntegrityError:
        return False, "Failed to create user due to database error."


def login_user(user_id: int) -> None:
    """Log the user in by storing their ID in the session."""
    session.clear()
    session["user_id"] = user_id
    session.permanent = True  # use PERMANENT_SESSION_LIFETIME


def logout_user() -> None:
    """Log the current user out."""
    session.clear()


def current_user() -> Optional[sqlite3.Row]:
    """Return the currently logged‑in user, or None."""
    user_id = session.get("user_id")
    if not user_id:
        return None
    db = get_db()
    cur = db.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    return cur.fetchone()


def login_required(view_func):
    """Simple decorator that redirects unauthenticated users to login."""

    def wrapper(*args, **kwargs):
        if current_user() is None:
            return redirect(url_for("login", next=request.path))
        return view_func(*args, **kwargs)

    wrapper.__name__ = view_func.__name__
    return wrapper


# ----------------------------------------------------------------------
# Routes
# ----------------------------------------------------------------------
@app.route("/")
def index() -> str:
    if user := current_user():
        return f"Hello, {user['username']}! <a href='{url_for('logout')}'>Logout</a>"
    return "Welcome! <a href='/login'>Login</a> or <a href='/register'>Register</a>"


@app.route("/register", methods=["GET", "POST"])
def register() -> str:
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")

        # Basic validation
        if not username or not password:
            flash("Username and password are required.", "danger")
        elif password != confirm:
            flash("Passwords do not match.", "danger")
        else:
            success, message = create_user(username, password)
            flash(message, "success" if success else "danger")
            if success:
                return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login() -> str:
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        user = get_user_by_username(username)
        if user and verify_password(password, user["password_hash"]):
            login_user(user["id"])
            flash("Logged in successfully.", "success")
            next_url = request.args.get("next") or url_for("index")
            return redirect(next_url)
        flash("Invalid username or password.", "danger")

    return render_template("login.html")


@app.route("/logout")
def logout() -> str:
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("index"))


@app.route("/protected")
@login_required
def protected() -> str:
    user = current_user()
    return f"This is a protected page. Hello, {user['username']}!"


# ----------------------------------------------------------------------
# Template Strings (for demo purposes; in production use separate files)
# ----------------------------------------------------------------------
app.jinja_loader = dict(
    register="""
<!doctype html>
<title>Register</title>
<h2>Register</h2>
{% with messages = get_flashed_messages(with_categories=true) %}
  {% for category, msg in messages %}
    <p class="flash {{ category }}">{{ msg }}</p>
  {% endfor %}
{% endwith %}
<form method=post>
  <label>Username: <input name=username required></label><br>
  <label>Password: <input type=password name=password required></label><br>
  <label>Confirm: <input type=password name=confirm required></label><br>
  <button type=submit>Register</button>
</form>
<a href="{{ url_for('login') }}">Already have an account? Login</a>
""",
    login="""
<!doctype html>
<title>Login</title>
<h2>Login</h2>
{% with messages = get_flashed_messages(with_categories=true) %}
  {% for category, msg in messages %}
    <p class="flash {{ category }}">{{ msg }}</p>
  {% endfor %}
{% endwith %}
<form method=post>
  <label>Username: <input name=username required></label><br>
  <label>Password: <input type=password name=password required></label><br>
  <button type=submit>Login</button>
</form>
<a href="{{ url_for('register') }}">Don’t have an account? Register</a>
""",
)

# ----------------------------------------------------------------------
# Application entry point
# ----------------------------------------------------------------------
if __name__ == "__main__":
    init_db()
    # In production use a real WSGI server and enforce HTTPS.
    app.run(host="0.0.0.0", port=5000, debug=False)