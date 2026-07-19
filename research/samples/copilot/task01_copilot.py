"""
Login System using Flask, SQLAlchemy, bcrypt, and itsdangerous.
Features:
- User registration with email verification
- Secure password hashing
- Login/logout with session management
- Password reset via email token
- Profile page
"""

from flask import Flask, request, redirect, url_for, render_template_string, session, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
import logging
from typing import Optional

# Configure logging
logging.basicConfig(level=logging.INFO)

app = Flask(__name__)
app.config["SECRET_KEY"] = "supersecretkey"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///users.db"
db = SQLAlchemy(app)

# Serializer for email verification and password reset
serializer = URLSafeTimedSerializer(app.config["SECRET_KEY"])


class User(db.Model):
    """Database model for users."""

    id: int = db.Column(db.Integer, primary_key=True)
    email: str = db.Column(db.String(120), unique=True, nullable=False)
    password_hash: str = db.Column(db.String(128), nullable=False)
    is_verified: bool = db.Column(db.Boolean, default=False)


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register a new user with email and password."""
    if request.method == "POST":
        email: str = request.form.get("email", "")
        password: str = request.form.get("password", "")
        if not email or not password:
            flash("Email and password required")
            return redirect(url_for("register"))

        if User.query.filter_by(email=email).first():
            flash("Email already registered")
            return redirect(url_for("register"))

        hashed_pw: str = generate_password_hash(password)
        user = User(email=email, password_hash=hashed_pw)
        db.session.add(user)
        db.session.commit()

        # Generate verification token
        token: str = serializer.dumps(email, salt="email-verify")
        logging.info(f"Verification link: {url_for('verify_email', token=token, _external=True)}")
        flash("Check logs for verification link (stubbed email).")
        return redirect(url_for("login"))

    return render_template_string("""
        <form method="post">
            Email: <input name="email"><br>
            Password: <input name="password" type="password"><br>
            <button type="submit">Register</button>
        </form>
    """)


@app.route("/verify/<token>")
def verify_email(token: str):
    """Verify user email using token."""
    try:
        email: str = serializer.loads(token, salt="email-verify", max_age=3600)
    except (BadSignature, SignatureExpired):
        flash("Invalid or expired token")
        return redirect(url_for("login"))

    user: Optional[User] = User.query.filter_by(email=email).first()
    if user:
        user.is_verified = True
        db.session.commit()
        flash("Email verified successfully")
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    """Login user with email and password."""
    if request.method == "POST":
        email: str = request.form.get("email", "")
        password: str = request.form.get("password", "")
        user: Optional[User] = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password_hash, password):
            if not user.is_verified:
                flash("Please verify your email first")
                return redirect(url_for("login"))
            session["user_id"] = user.id
            flash("Logged in successfully")
            return redirect(url_for("profile"))
        flash("Invalid credentials")
    return render_template_string("""
        <form method="post">
            Email: <input name="email"><br>
            Password: <input name="password" type="password"><br>
            <button type="submit">Login</button>
        </form>
    """)


@app.route("/logout")
def logout():
    """Logout user by clearing session."""
    session.clear()
    flash("Logged out")
    return redirect(url_for("login"))


@app.route("/profile")
def profile():
    """Display user profile if logged in."""
    user_id: Optional[int] = session.get("user_id")
    if not user_id:
        flash("Login required")
        return redirect(url_for("login"))
    user: Optional[User] = User.query.get(user_id)
    return f"Welcome {user.email}"


@app.route("/reset_request", methods=["GET", "POST"])
def reset_request():
    """Request password reset link."""
    if request.method == "POST":
        email: str = request.form.get("email", "")
        user: Optional[User] = User.query.filter_by(email=email).first()
        if user:
            token: str = serializer.dumps(email, salt="reset-password")
            logging.info(f"Password reset link: {url_for('reset_password', token=token, _external=True)}")
            flash("Check logs for reset link (stubbed email).")
        else:
            flash("Email not found")
    return render_template_string("""
        <form method="post">
            Email: <input name="email"><br>
            <button type="submit">Request Reset</button>
        </form>
    """)


@app.route("/reset/<token>", methods=["GET", "POST"])
def reset_password(token: str):
    """Reset password using token."""
    try:
        email: str = serializer.loads(token, salt="reset-password", max_age=3600)
    except (BadSignature, SignatureExpired):
        flash("Invalid or expired token")
        return redirect(url_for("login"))

    if request.method == "POST":
        new_password: str = request.form.get("password", "")
        user: Optional[User] = User.query.filter_by(email=email).first()
        if user:
            user.password_hash = generate_password_hash(new_password)
            db.session.commit()
            flash("Password reset successfully")
            return redirect(url_for("login"))
    return render_template_string("""
        <form method="post">
            New Password: <input name="password" type="password"><br>
            <button type="submit">Reset</button>
        </form>
    """)


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)

