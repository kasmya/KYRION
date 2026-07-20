import bcrypt
from flask import Flask, request, jsonify, session
from typing import Dict, Tuple
from datetime import datetime, timedelta
import jwt

app = Flask(__name__)
app.secret_key = "your-secret-key-here"  # Replace with a secure secret key
app.config['JWT_SECRET_KEY'] = 'super-secret'  # Replace with a secure secret key
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=30)

# In-memory user storage for demonstration (use a database in production)
users: Dict[str, Dict[str, str]] = {}

def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def check_password(plain_password: str, hashed_password: str) -> bool:
    """Verify if a plain password matches a hashed password."""
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))

def generate_jwt(token_data: Dict[str, str]) -> str:
    """Generate a JWT token."""
    return jwt.encode(token_data, app.config['JWT_SECRET_KEY'], algorithm="HS256")

def verify_jwt(token: str) -> Dict[str, str]:
    """Verify a JWT token and return its payload."""
    try:
        return jwt.decode(token, app.config['JWT_SECRET_KEY'], algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise ValueError("Token has expired")
    except jwt.InvalidTokenError:
        raise ValueError("Invalid token")

@app.route('/register', methods=['POST'])
def register() -> Tuple[str, int]:
    """Register a new user."""
    try:
        data = request.json
        if not data or 'username' not in data or 'password' not in data:
            return jsonify({"error": "Missing username or password"}), 400
        
        username, password = data['username'], data['password']
        if username in users:
            return jsonify({"error": "Username already exists"}), 400
        
        hashed_password = hash_password(password)
        users[username] = {"password": hashed_password}
        return jsonify({"message": "User created successfully"}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/login', methods=['POST'])
def login() -> Tuple[str, int]:
    """Login an existing user and issue a JWT token."""
    try:
        data = request.json
        if not data or 'username' not in data or 'password' not in data:
            return jsonify({"error": "Missing username or password"}), 400
        
        username, password = data['username'], data['password']
        if username not in users:
            return jsonify({"error": "Username not found"}), 404
        
        if not check_password(password, users[username]["password"]):
            return jsonify({"error": "Invalid credentials"}), 401
        
        # Issue JWT token
        token = generate_jwt({"username": username, "exp": datetime.utcnow() + timedelta(minutes=60)})
        return jsonify({"token": token}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/protected', methods=['GET'])
def protected() -> Tuple[str, int]:
    """A protected route that requires a valid JWT token."""
    try:
        token = request.headers.get('Authorization')
        if not token:
            return jsonify({"error": "Token missing"}), 401
        
        # Verify JWT token
        payload = verify_jwt(token)
        return jsonify({"message": f"Hello, {payload['username']}"}), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 401

@app.route('/session_login', methods=['POST'])
def session_login() -> Tuple[str, int]:
    """Login using Flask session management."""
    try:
        data = request.json
        if not data or 'username' not in data or 'password' not in data:
            return jsonify({"error": "Missing username or password"}), 400
        
        username, password = data['username'], data['password']
        if username not in users:
            return jsonify({"error": "Username not found"}), 404
        
        if not check_password(password, users[username]["password"]):
            return jsonify({"error": "Invalid credentials"}), 401
        
        # Use Flask session
        session['username'] = username
        return jsonify({"message": "Logged in successfully"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/session_protected', methods=['GET'])
def session_protected() -> Tuple[str, int]:
    """A protected route using Flask session."""
    if 'username' not in session:
        return jsonify({"error": "Not logged in"}), 401
    return jsonify({"message": f"Hello, {session['username']}"}), 200

@app.route('/logout', methods=['POST'])
def logout() -> Tuple[str, int]:
    """Logout the current user (clears session)."""
    session.clear()
    return jsonify({"message": "Logged out successfully"}), 200

if __name__ == '__main__':
    app.run(debug=True)