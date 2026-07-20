# Import necessary libraries
from flask import Flask, request, session, jsonify
from flask_bcrypt import Bcrypt
from typing import Dict
import json

# Create Flask app instance and bcrypt hasher
app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key'  # Replace with a secure secret key
bcrypt = Bcrypt(app)

# In-memory user storage (replace with a database in production)
users: Dict[str, str] = {}

def hash_password(password: str) -> str:
    """
    Hash a password using bcrypt.
    
    Args:
    password (str): The password to hash.
    
    Returns:
    str: The hashed password.
    """
    return bcrypt.generate_password_hash(password).decode('utf-8')

def check_password(plain_password: str, hashed_password: str) -> bool:
    """
    Check if a plain password matches a hashed password.
    
    Args:
    plain_password (str): The plain password to check.
    hashed_password (str): The hashed password to compare with.
    
    Returns:
    bool: True if the passwords match, False otherwise.
    """
    return bcrypt.check_password_hash(hashed_password, plain_password)

@app.route('/register', methods=['POST'])
def register():
    """
    Handle user registration.
    
    Expects a JSON payload with 'username' and 'password' fields.
    
    Returns:
    - 201 Created on successful registration
    - 400 Bad Request for invalid requests
    - 409 Conflict if the username is already taken
    """
    data = request.get_json()
    if not data or 'username' not in data or 'password' not in data:
        return jsonify({'error': 'Invalid request'}), 400
    
    username, password = data['username'], data['password']
    if username in users:
        return jsonify({'error': 'Username already taken'}), 409
    
    hashed_password = hash_password(password)
    users[username] = hashed_password
    return jsonify({'message': 'User created successfully'}), 201

@app.route('/login', methods=['POST'])
def login():
    """
    Handle user login.
    
    Expects a JSON payload with 'username' and 'password' fields.
    
    Returns:
    - 200 OK on successful login with a JWT token
    - 401 Unauthorized for invalid credentials
    - 400 Bad Request for invalid requests
    """
    data = request.get_json()
    if not data or 'username' not in data or 'password' not in data:
        return jsonify({'error': 'Invalid request'}), 400
    
    username, plain_password = data['username'], data['password']
    if username not in users:
        return jsonify({'error': 'Invalid credentials'}), 401
    
    if check_password(plain_password, users[username]):
        # Generate a simple token for demo (use JWT in production)
        token = f"TOKEN-{username}"
        session['logged_in'] = True
        session['username'] = username
        return jsonify({'token': token, 'message': 'Logged in successfully'}), 200
    else:
        return jsonify({'error': 'Invalid credentials'}), 401

@app.route('/logout', methods=['POST'])
def logout():
    """
    Handle user logout.
    
    Returns:
    - 200 OK on successful logout
    """
    session.pop('logged_in', None)
    session.pop('username', None)
    return jsonify({'message': 'Logged out successfully'}), 200

@app.route('/protected', methods=['GET'])
def protected():
    """
    A protected route that requires login.
    
    Returns:
    - 200 OK if logged in
    - 401 Unauthorized if not logged in
    """
    if 'logged_in' in session and session['logged_in']:
        return jsonify({'message': f'Welcome, {session["username"]}'}), 200
    else:
        return jsonify({'error': 'You must be logged in'}), 401

if __name__ == '__main__':
    app.run(debug=True)