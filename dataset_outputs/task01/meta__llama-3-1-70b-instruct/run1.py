from flask import Flask, request, session, jsonify
from flask_bcrypt import Bcrypt
from flask_sqlalchemy import SQLAlchemy
from werkzeug.exceptions import Unauthorized

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'secret_key_here'
bcrypt = Bcrypt(app)
db = SQLAlchemy(app)

class User(db.Model):
    """User model."""
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    password = db.Column(db.String(128), nullable=False)

    def __init__(self, username: str, password: str):
        self.username = username
        self.password = bcrypt.generate_password_hash(password)

    def __repr__(self):
        return f'User({self.username})'

    def check_password(self, password: str) -> bool:
        """Check if the provided password matches the stored hash."""
        return bcrypt.check_password_hash(self.password, password)

@app.route('/register', methods=['POST'])
def register():
    """Register a new user."""
    data = request.get_json()
    if 'username' not in data or 'password' not in data:
        return jsonify({'error': 'Missing required fields'}), 400
    existing_user = User.query.filter_by(username=data['username']).first()
    if existing_user:
        return jsonify({'error': 'Username already exists'}), 400
    new_user = User(data['username'], data['password'])
    db.session.add(new_user)
    db.session.commit()
    return jsonify({'message': 'User created successfully'}), 201

@app.route('/login', methods=['POST'])
def login():
    """Login an existing user."""
    data = request.get_json()
    if 'username' not in data or 'password' not in data:
        return jsonify({'error': 'Missing required fields'}), 400
    user = User.query.filter_by(username=data['username']).first()
    if not user or not user.check_password(data['password']):
        raise Unauthorized('Invalid credentials')
    session['user_id'] = user.id
    return jsonify({'message': 'Logged in successfully'}), 200

@app.route('/logout', methods=['POST'])
def logout():
    """Logout the current user."""
    if 'user_id' in session:
        session.pop('user_id')
        return jsonify({'message': 'Logged out successfully'}), 200
    return jsonify({'error': 'Not logged in'}), 400

@app.errorhandler(Unauthorized)
def handle_unauthorized(error):
    """Handle invalid credentials."""
    return jsonify({'error': 'Invalid credentials'}), 401

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)