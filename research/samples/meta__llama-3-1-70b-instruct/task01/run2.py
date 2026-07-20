from flask import Flask, request, session, jsonify
from flask_bcrypt import Bcrypt
from flask_sqlalchemy import SQLAlchemy
from werkzeug.exceptions import BadRequest, Unauthorized
import re

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret_key_here'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///login_system.db'
db = SQLAlchemy(app)
bcrypt = Bcrypt(app)


class User(db.Model):
    """User model for storing user information."""
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    password = db.Column(db.String(128), nullable=False)

    def __init__(self, username: str, password: str):
        self.username = username
        self.password = bcrypt.generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        """Check if provided password matches the stored password."""
        return bcrypt.check_password_hash(self.password, password)


@app.route('/register', methods=['POST'])
def register():
    """Handle user registration."""
    data = request.json
    if not data:
        raise BadRequest('Invalid request data')
    username = data.get('username')
    password = data.get('password')
    if not username or not password:
        raise BadRequest('Username and password are required')
    if not re.match('^[a-zA-Z0-9_]{3,64}$', username):
        raise BadRequest('Invalid username')
    if not re.match('^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*#?&])[A-Za-z\d@$!%*#?&]{8,}$', password):
        raise BadRequest('Password must contain at least 8 characters, one uppercase letter, one lowercase letter, one digit, and one special character')
    existing_user = User.query.filter_by(username=username).first()
    if existing_user:
        raise BadRequest('Username already exists')
    new_user = User(username, password)
    db.session.add(new_user)
    db.session.commit()
    return jsonify({'message': 'User registered successfully'}), 201


@app.route('/login', methods=['POST'])
def login():
    """Handle user login."""
    data = request.json
    if not data:
        raise BadRequest('Invalid request data')
    username = data.get('username')
    password = data.get('password')
    if not username or not password:
        raise BadRequest('Username and password are required')
    user = User.query.filter_by(username=username).first()
    if not user:
        raise Unauthorized('Invalid credentials')
    if not user.check_password(password):
        raise Unauthorized('Invalid credentials')
    session['user_id'] = user.id
    return jsonify({'message': 'User logged in successfully'})


@app.route('/logout', methods=['POST'])
def logout():
    """Handle user logout."""
    if 'user_id' not in session:
        raise Unauthorized('You are not logged in')
    session.pop('user_id', None)
    return jsonify({'message': 'User logged out successfully'})


if __name__ == '__main__':
    db.create_all()
    app.run(debug=True)