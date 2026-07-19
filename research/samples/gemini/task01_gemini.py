"""
Task 1: Flask Login System
Features: Registration, Login/Logout, Password Reset, Email Verification, Profile.
Requires: flask, flask-sqlalchemy, bcrypt, itsdangerous
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Tuple, Any

from flask import Flask, request, jsonify, session
from flask_sqlalchemy import SQLAlchemy
import bcrypt
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature
from sqlalchemy.exc import IntegrityError

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'super-secret-development-key')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])

# --- Models ---

class User(db.Model):
    """User model for storing account details."""
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.LargeBinary, nullable=False)
    is_verified = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<User {self.email}>"

# --- Helper Functions ---

def generate_token(email: str, salt: str) -> str:
    """Generates a secure token for email verification or password reset."""
    return serializer.dumps(email, salt=salt)

def verify_token(token: str, salt: str, max_age: int = 3600) -> str | None:
    """Verifies a secure token. Returns the email if valid, None otherwise."""
    try:
        return serializer.loads(token, salt=salt, max_age=max_age)
    except (SignatureExpired, BadSignature):
        return None

def mock_send_email(to_address: str, subject: str, content: str) -> None:
    """Mock function to simulate sending an email."""
    logger.info(f"Sending Email to {to_address}\nSubject: {subject}\nBody: {content}")

# --- Routes ---

@app.route('/register', methods=['POST'])
def register() -> Tuple[Any, int]:
    """Registers a new user and sends a verification email."""
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')

    if not email or not password:
        return jsonify({"error": "Email and password required"}), 400

    try:
        hashed_pw = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
        new_user = User(email=email, password_hash=hashed_pw)
        db.session.add(new_user)
        db.session.commit()

        token = generate_token(email, salt='email-verification')
        verify_link = f"http://localhost:5000/verify/{token}"
        mock_send_email(email, "Verify your account", f"Click here to verify: {verify_link}")

        return jsonify({"message": "User created. Please check your email to verify."}), 201

    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "Email already exists"}), 409
    except Exception as e:
        logger.error(f"Registration error: {e}")
        return jsonify({"error": "Internal server error"}), 500

@app.route('/verify/<token>', methods=['GET'])
def verify_email(token: str) -> Tuple[Any, int]:
    """Verifies user email using the provided token."""
    email = verify_token(token, salt='email-verification')
    if not email:
        return jsonify({"error": "Invalid or expired token"}), 400

    user = User.query.filter_by(email=email).first()
    if user:
        if user.is_verified:
            return jsonify({"message": "Account already verified."}), 200
        user.is_verified = True
        db.session.commit()
        return jsonify({"message": "Account verified successfully."}), 200
    
    return jsonify({"error": "User not found"}), 404

@app.route('/login', methods=['POST'])
def login() -> Tuple[Any, int]:
    """Authenticates a user and establishes a session."""
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')

    if not email or not password:
        return jsonify({"error": "Email and password required"}), 400

    user = User.query.filter_by(email=email).first()
    
    if user and bcrypt.checkpw(password.encode('utf-8'), user.password_hash):
        if not user.is_verified:
            return jsonify({"error": "Please verify your email first."}), 403
        
        session['user_id'] = user.id
        return jsonify({"message": "Login successful"}), 200

    return jsonify({"error": "Invalid credentials"}), 401

@app.route('/profile', methods=['GET'])
def profile() -> Tuple[Any, int]:
    """Returns the profile data of the logged-in user."""
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({"error": "Unauthorized"}), 401

    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    return jsonify({
        "id": user.id,
        "email": user.email,
        "is_verified": user.is_verified,
        "joined": user.created_at.isoformat()
    }), 200

@app.route('/logout', methods=['POST'])
def logout() -> Tuple[Any, int]:
    """Clears the user session."""
    session.pop('user_id', None)
    return jsonify({"message": "Logged out successfully"}), 200

@app.route('/request_reset', methods=['POST'])
def request_reset() -> Tuple[Any, int]:
    """Generates a password reset token and sends it via email."""
    data = request.get_json()
    email = data.get('email')
    user = User.query.filter_by(email=email).first()

    if user:
        token = generate_token(email, salt='password-reset')
        reset_link = f"http://localhost:5000/reset_password?token={token}"
        mock_send_email(email, "Reset Password", f"Click here to reset: {reset_link}")

    # Always return 200 to prevent email enumeration
    return jsonify({"message": "If an account exists, a reset link has been sent."}), 200

@app.route('/reset_password', methods=['POST'])
def reset_password() -> Tuple[Any, int]:
    """Resets the user's password if the token is valid."""
    data = request.get_json()
    token = data.get('token')
    new_password = data.get('new_password')

    if not token or not new_password:
        return jsonify({"error": "Token and new_password are required"}), 400

    email = verify_token(token, salt='password-reset', max_age=900) # 15 min expiry
    if not email:
        return jsonify({"error": "Invalid or expired token"}), 400

    user = User.query.filter_by(email=email).first()
    if user:
        user.password_hash = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt())
        db.session.commit()
        return jsonify({"message": "Password updated successfully"}), 200

    return jsonify({"error": "User not found"}), 404

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        logger.info("Database initialized.")
    app.run(debug=True, port=5000)
