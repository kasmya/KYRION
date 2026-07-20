from flask import Flask, request, session, jsonify
from flask_bcrypt import Bcrypt
from flask_session import Session
from typing import Dict

app = Flask(__name__)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
app.config["SECRET_KEY"] = "secret_key_here"

bcrypt = Bcrypt(app)
Session(app)


class User:
    """User class to store user data."""

    def __init__(self, username: str, password: str):
        """Initialize User instance."""
        self.username = username
        self.password = bcrypt.generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        """Check if provided password matches hashed password."""
        return bcrypt.check_password_hash(self.password, password)


class LoginSystem:
    """Login system class to handle user registration and login."""

    def __init__(self):
        """Initialize LoginSystem instance."""
        self.users: Dict[str, User] = {}

    def register(self, username: str, password: str):
        """Register a new user."""
        if username in self.users:
            raise ValueError("Username already exists")
        self.users[username] = User(username, password)

    def login(self, username: str, password: str) -> bool:
        """Login an existing user."""
        if username not in self.users:
            raise ValueError("Username does not exist")
        user = self.users[username]
        if user.check_password(password):
            session["username"] = username
            return True
        return False

    def logout(self):
        """Logout the current user."""
        if "username" in session:
            del session["username"]


login_system = LoginSystem()


@app.route("/register", methods=["POST"])
def register():
    """Register a new user."""
    try:
        data = request.json
        username = data["username"]
        password = data["password"]
        login_system.register(username, password)
        return jsonify({"message": "User registered successfully"}), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": "Internal server error"}), 500


@app.route("/login", methods=["POST"])
def login():
    """Login an existing user."""
    try:
        data = request.json
        username = data["username"]
        password = data["password"]
        if login_system.login(username, password):
            return jsonify({"message": "User logged in successfully"}), 200
        else:
            return jsonify({"error": "Invalid credentials"}), 401
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": "Internal server error"}), 500


@app.route("/logout", methods=["POST"])
def logout():
    """Logout the current user."""
    try:
        login_system.logout()
        return jsonify({"message": "User logged out successfully"}), 200
    except Exception as e:
        return jsonify({"error": "Internal server error"}), 500


if __name__ == "__main__":
    app.run(debug=True)