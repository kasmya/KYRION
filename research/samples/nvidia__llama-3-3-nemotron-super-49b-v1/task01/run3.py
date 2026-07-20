# Importing necessary libraries
from flask import Flask, request, jsonify, session
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_sqlalchemy import SQLAlchemy
import bcrypt
from typing import Dict, Any
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Flask application
app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key_here'  # Replace with a secure secret key
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////tmp/test.db'  # Replace with your database URI
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize Flask-SQLAlchemy
db = SQLAlchemy(app)

# Initialize Flask-Login
login_manager = LoginManager(app)

# Define User model
class User(UserMixin, db.Model):
    """Represents a user in the system."""
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)

    def set_password(self, password: str) -> None:
        """Sets the user's password after hashing it with bcrypt."""
        self.password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    def check_password(self, password: str) -> bool:
        """Checks if the provided password matches the hashed password."""
        return bcrypt.checkpw(password.encode('utf-8'), self.password_hash.encode('utf-8'))

    def __repr__(self) -> str:
        return f"<User {self.username}>"

# Load user for Flask-Login
@login_manager.user_loader
def load_user(user_id: int) -> User:
    """Loads a user by their ID."""
    return User.query.get(int(user_id))

# User registration endpoint
@app.route('/register', methods=['POST'])
def register() -> Dict[str, Any]:
    """
    Registers a new user.

    Request Body:
    - username (str): The desired username.
    - password (str): The desired password.

    Returns:
    - A JSON response indicating success or failure.
    """
    try:
        data = request.json
        if not data or 'username' not in data or 'password' not in data:
            return jsonify({'error': 'Missing username or password'}), 400

        username = data['username']
        password = data['password']

        if not username or not password:
            return jsonify({'error': 'Username and password are required'}), 400

        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            return jsonify({'error': 'Username already exists'}), 400

        new_user = User(username=username)
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()
        return jsonify({'message': 'User created successfully'}), 201
    except Exception as e:
        logger.error(f"Registration failed: {e}")
        return jsonify({'error': 'Internal Server Error'}), 500

# Login endpoint
@app.route('/login', methods=['POST'])
def login() -> Dict[str, Any]:
    """
    Logs in an existing user.

    Request Body:
    - username (str): The username.
    - password (str): The password.

    Returns:
    - A JSON response indicating success or failure.
    """
    try:
        data = request.json
        if not data or 'username' not in data or 'password' not in data:
            return jsonify({'error': 'Missing username or password'}), 400

        username = data['username']
        password = data['password']

        user = User.query.filter_by(username=username).first()
        if not user or not user.check_password(password):
            return jsonify({'error': 'Invalid username or password'}), 401

        login_user(user)
        return jsonify({'message': 'Logged in successfully'}), 200
    except Exception as e:
        logger.error(f"Login failed: {e}")
        return jsonify({'error': 'Internal Server Error'}), 500

# Protected route example
@app.route('/protected', methods=['GET'])
@login_required
def protected() -> Dict[str, Any]:
    """A protected route that requires login."""
    return jsonify({'message': f'Hello, {current_user.username}!'}), 200

# Logout endpoint
@app.route('/logout', methods=['POST'])
@login_required
def logout() -> Dict[str, Any]:
    """Logs out the current user."""
    logout_user()
    return jsonify({'message': 'Logged out successfully'}), 200

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)