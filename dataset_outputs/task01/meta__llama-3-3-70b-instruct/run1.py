from flask import Flask, request, jsonify, session
from flask import abort
from flask_bcrypt import Bcrypt
from typing import Dict

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret_key_here'
bcrypt = Bcrypt(app)

# In-memory user storage for simplicity (replace with a database in production)
users: Dict[str, str] = {}

def hash_password(password: str) -> str:
    """
    Hashes a password using bcrypt.

    Args:
    password (str): The password to hash.

    Returns:
    str: The hashed password.
    """
    return bcrypt.generate_password_hash(password).decode('utf-8')

def check_password(password: str, hashed_password: str) -> bool:
    """
    Checks if a password matches a hashed password.

    Args:
    password (str): The password to check.
    hashed_password (str): The hashed password.

    Returns:
    bool: True if the password matches, False otherwise.
    """
    return bcrypt.check_password_hash(hashed_password, password)

@app.route('/register', methods=['POST'])
def register():
    """
    Registers a new user.

    Expects:
    - username (str): The username.
    - password (str): The password.

    Returns:
    - 201 Created: If the user was created successfully.
    - 400 Bad Request: If the request was invalid.
    """
    data = request.json
    if not data or 'username' not in data or 'password' not in data:
        abort(400, 'Invalid request')

    username = data['username']
    password = data['password']

    if username in users:
        abort(400, 'Username already taken')

    hashed_password = hash_password(password)
    users[username] = hashed_password

    return jsonify({'message': 'User created successfully'}), 201

@app.route('/login', methods=['POST'])
def login():
    """
    Logs in an existing user.

    Expects:
    - username (str): The username.
    - password (str): The password.

    Returns:
    - 200 OK: If the user was logged in successfully.
    - 401 Unauthorized: If the credentials were invalid.
    """
    data = request.json
    if not data or 'username' not in data or 'password' not in data:
        abort(400, 'Invalid request')

    username = data['username']
    password = data['password']

    if username not in users:
        abort(401, 'Invalid credentials')

    hashed_password = users[username]
    if not check_password(password, hashed_password):
        abort(401, 'Invalid credentials')

    session['username'] = username
    return jsonify({'message': 'Logged in successfully'})

@app.route('/logout', methods=['POST'])
def logout():
    """
    Logs out the current user.

    Returns:
    - 200 OK: If the user was logged out successfully.
    """
    session.pop('username', None)
    return jsonify({'message': 'Logged out successfully'})

@app.route('/protected', methods=['GET'])
def protected():
    """
    A protected route that requires the user to be logged in.

    Returns:
    - 200 OK: If the user is logged in.
    - 401 Unauthorized: If the user is not logged in.
    """
    if 'username' not in session:
        abort(401, 'You must be logged in to access this route')
    return jsonify({'message': f'Hello, {session["username"]}!'})

if __name__ == '__main__':
    app.run(debug=True)