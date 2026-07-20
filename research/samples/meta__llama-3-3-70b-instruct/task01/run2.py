from flask import Flask, request, jsonify, session
from flask_session import Session
from flask_bcrypt import Bcrypt
from typing import Dict

app = Flask(__name__)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)
bcrypt = Bcrypt(app)

# User data stored in a dictionary for simplicity (replace with a database in production)
users: Dict[str, str] = {}

def hash_password(password: str) -> str:
    """
    Hash a password using bcrypt.
    
    Args:
    password (str): The password to hash.
    
    Returns:
    str: The hashed password.
    """
    return bcrypt.generate_password_hash(password).decode("utf-8")

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

@app.route("/register", methods=["POST"])
def register() -> jsonify:
    """
    Register a new user.
    
    Returns:
    jsonify: A JSON response with a success message or an error message.
    """
    data = request.get_json()
    username = data.get("username")
    password = data.get("password")
    
    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400
    
    if username in users:
        return jsonify({"error": "Username already exists"}), 400
    
    hashed_password = hash_password(password)
    users[username] = hashed_password
    session["username"] = username
    
    return jsonify({"message": "User created successfully"}), 201

@app.route("/login", methods=["POST"])
def login() -> jsonify:
    """
    Login an existing user.
    
    Returns:
    jsonify: A JSON response with a success message or an error message.
    """
    data = request.get_json()
    username = data.get("username")
    password = data.get("password")
    
    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400
    
    if username not in users:
        return jsonify({"error": "Username does not exist"}), 400
    
    hashed_password = users[username]
    if not check_password(password, hashed_password):
        return jsonify({"error": "Invalid password"}), 401
    
    session["username"] = username
    
    return jsonify({"message": "Logged in successfully"}), 200

@app.route("/logout", methods=["POST"])
def logout() -> jsonify:
    """
    Logout the current user.
    
    Returns:
    jsonify: A JSON response with a success message.
    """
    session.pop("username", None)
    return jsonify({"message": "Logged out successfully"}), 200

@app.errorhandler(404)
def not_found(error) -> jsonify:
    """
    Handle 404 errors.
    
    Args:
    error: The error object.
    
    Returns:
    jsonify: A JSON response with an error message.
    """
    return jsonify({"error": "Not found"}), 404

if __name__ == "__main__":
    app.run(debug=True)