"""Flask Login System with SQLAlchemy, bcrypt, and itsdangerous."""
import os, logging, bcrypt
from typing import Dict, Any
from flask import Flask, request, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from itsdangerous import URLSafeTimedSerializer, SignatureExpired

logging.basicConfig(level=logging.INFO)
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///auth.db'
app.config['SECRET_KEY'] = 'super-secret-key'
db = SQLAlchemy(app)
serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    verified = db.Column(db.Boolean, default=False)

with app.app_context():
    db.create_all()

def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def check_password(pw: str, hashed: str) -> bool:
    return bcrypt.checkpw(pw.encode('utf-8'), hashed.encode('utf-8'))

@app.route('/register', methods=['POST'])
def register() -> tuple[Dict[str, str], int]:
    data = request.json
    if not data or 'email' not in data or 'password' not in data:
        return {"error": "Missing credentials"}, 400
    if User.query.filter_by(email=data['email']).first():
        return {"error": "Email exists"}, 409
    user = User(email=data['email'], password_hash=hash_password(data['password']))
    db.session.add(user)
    db.session.commit()
    token = serializer.dumps(data['email'], salt='email-verify')
    logging.info(f"Verify token for {data['email']}: {token}")
    return {"message": "Registered. Verify email.", "token": token}, 201

@app.route('/verify/<token>')
def verify(token: str) -> tuple[Dict[str, str], int]:
    try:
        email = serializer.loads(token, salt='email-verify', max_age=3600)
    except SignatureExpired:
        return {"error": "Token expired"}, 400
    user = User.query.filter_by(email=email).first()
    if user:
        user.verified = True
        db.session.commit()
        return {"message": "Verified"}, 200
    return {"error": "User not found"}, 404

@app.route('/login', methods=['POST'])
def login() -> tuple[Dict[str, str], int]:
    data = request.json
    user = User.query.filter_by(email=data.get('email')).first()
    if user and check_password(data.get('password', ''), user.password_hash):
        session['user_id'] = user.id
        return {"message": "Logged in"}, 200
    return {"error": "Invalid credentials"}, 401

@app.route('/logout', methods=['POST'])
def logout() -> tuple[Dict[str, str], int]:
    session.pop('user_id', None)
    return {"message": "Logged out"}, 200

@app.route('/profile')
def profile() -> tuple[Dict[str, Any], int]:
    if 'user_id' not in session:
        return {"error": "Unauthorized"}, 401
    user = User.query.get(session['user_id'])
    return {"email": user.email, "verified": user.verified}, 200

@app.route('/reset-request', methods=['POST'])
def reset_request() -> tuple[Dict[str, str], int]:
    email = request.json.get('email')
    user = User.query.filter_by(email=email).first()
    if user:
        token = serializer.dumps(email, salt='password-reset')
        logging.info(f"Reset token for {email}: {token}")
    return {"message": "If email exists, reset link sent."}, 200

if __name__ == '__main__':
    app.run(debug=True)