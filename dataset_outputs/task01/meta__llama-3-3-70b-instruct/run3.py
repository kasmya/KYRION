from flask import Flask, request, jsonify, session
from flask_bcrypt import Bcrypt
from flask_session import Session
import jwt
from typing import Dict

app = Flask(__name__)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
app.config["SECRET_KEY"] = "secret_key_here"
Session(app)
bcrypt = Bcrypt(app)

# User class for storing user data
class User:
    def __init__(self, username: str, password: str):
        self.username = username
        self.password = bcrypt.generate_password_hash(password).decode("utf-8")

# Dictionary to store registered users
registered_users: Dict[str, User] = {}

# Register a new user
@app.route("/register", methods=["POST"])
def register_user() -> str:
    """
    Register a new user.

    Request Body:
    {
        "username": "username",
        "password": "password"
    }

    Returns:
    "User registered successfully"
    """
    data = request.get_json()
    username = data.get("username")
    password = data.get("password")

    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400

    if username in registered_users:
        return jsonify({"error": "Username already exists"}), 400

    new_user = User(username, password)
    registered_users[username] = new_user

    return "User registered successfully"

# Login a user
@app.route("/login", methods=["POST"])
def login_user() -> str:
    """
    Login a user.

    Request Body:
    {
        "username": "username",
        "password": "password"
    }

    Returns:
    "Logged in successfully"
    """
    data = request.get_json()
    username = data.get("username")
    password = data.get("password")

    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400

    if username not in registered_users:
        return jsonify({"error": "Username does not exist"}), 400

    user = registered_users[username]
    if not bcrypt.check_password_hash(user.password, password):
        return jsonify({"error": "Invalid password"}), 401

    # Generate JWT token
    token = jwt.encode({"username": username}, app.config["SECRET_KEY"], algorithm="HS256")
    session["token"] = token

    return "Logged in successfully"

# Logout a user
@app.route("/logout", methods=["POST"])
def logout_user() -> str:
    """
    Logout a user.

    Returns:
    "Logged out successfully"
    """
    session.pop("token", None)
    return "Logged out successfully"

# Protected route
@app.route("/protected", methods=["GET"])
def protected_route() -> str:
    """
    Protected route.

    Returns:
    "Hello, {username}!"
    """
    token = session.get("token")
    if not token:
        return jsonify({"error": "You are not logged in"}), 401

    try:
        payload = jwt.decode(token, app.config["SECRET_KEY"], algorithms=["HS256"])
        username = payload["username"]
        return f"Hello, {username}!"
    except jwt.ExpiredSignatureError:
        return jsonify({"error": "Token has expired"}), 401
    except jwt.InvalidTokenError:
        return jsonify({"error": "Invalid token"}), 401

if __name__ == "__main__":
    app.run(debug=True)