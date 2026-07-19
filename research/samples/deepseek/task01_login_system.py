"""
Complete Flask Login System with email verification and password reset.

Features:
- User registration with email verification
- Secure password hashing with bcrypt
- Session-based authentication
- Password reset via email tokens
- Profile management
- SQLite database with SQLAlchemy ORM
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from functools import wraps

from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, session, jsonify, abort
)
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail, Message
from werkzeug.security import generate_password_hash, check_password_hash
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
import bcrypt
import re
from email_validator import validate_email, EmailNotValidError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('login_system.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME', 'your-email@gmail.com')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD', 'your-app-password')
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_USERNAME', 'noreply@example.com')

# Initialize extensions
db = SQLAlchemy(app)
mail = Mail(app)
serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])

# Database Models
class User(db.Model):
    """User model for authentication and profile management."""
    
    __tablename__ = 'users'
    
    id: int = db.Column(db.Integer, primary_key=True)
    email: str = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash: str = db.Column(db.String(255), nullable=False)
    name: str = db.Column(db.String(100), nullable=False)
    email_verified: bool = db.Column(db.Boolean, default=False)
    created_at: datetime = db.Column(db.DateTime, default=datetime.utcnow)
    last_login: Optional[datetime] = db.Column(db.DateTime, nullable=True)
    reset_token: Optional[str] = db.Column(db.String(255), nullable=True)
    reset_token_expiry: Optional[datetime] = db.Column(db.DateTime, nullable=True)
    
    def set_password(self, password: str) -> None:
        """Hash and set user password using bcrypt."""
        salt = bcrypt.gensalt(rounds=12)
        self.password_hash = bcrypt.hashpw(
            password.encode('utf-8'), salt
        ).decode('utf-8')
    
    def check_password(self, password: str) -> bool:
        """Verify password against stored hash."""
        return bcrypt.checkpw(
            password.encode('utf-8'),
            self.password_hash.encode('utf-8')
        )
    
    def generate_verification_token(self) -> str:
        """Generate email verification token (valid for 1 hour)."""
        return serializer.dumps(self.email, salt='email-verification')
    
    @staticmethod
    def verify_token(token: str, expiration: int = 3600) -> Optional[str]:
        """Verify token and return email if valid."""
        try:
            email = serializer.loads(
                token, salt='email-verification', max_age=expiration
            )
            return email
        except SignatureExpired:
            logger.warning("Token has expired")
            return None
        except BadSignature:
            logger.error("Invalid token signature")
            return None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert user object to dictionary (excluding sensitive data)."""
        return {
            'id': self.id,
            'email': self.email,
            'name': self.name,
            'email_verified': self.email_verified,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_login': self.last_login.isoformat() if self.last_login else None
        }
    
    def __repr__(self) -> str:
        return f'<User {self.email}>'

# Validation utilities
def validate_password_strength(password: str) -> tuple[bool, str]:
    """
    Validate password strength requirements.
    
    Requirements:
    - Minimum 8 characters
    - At least one uppercase letter
    - At least one lowercase letter
    - At least one digit
    - At least one special character
    """
    if len(password) < 8:
        return False, "Password must be at least 8 characters long"
    
    if not re.search(r'[A-Z]', password):
        return False, "Password must contain at least one uppercase letter"
    
    if not re.search(r'[a-z]', password):
        return False, "Password must contain at least one lowercase letter"
    
    if not re.search(r'\d', password):
        return False, "Password must contain at least one digit"
    
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        return False, "Password must contain at least one special character"
    
    return True, "Password is strong"

def validate_user_email(email: str) -> tuple[bool, str]:
    """Validate email format using email-validator library."""
    try:
        valid = validate_email(email)
        return True, valid.email
    except EmailNotValidError as e:
        return False, str(e)

# Decorators
def login_required(f):
    """Decorator to require authentication for routes."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    """Decorator to require admin privileges."""
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        user = User.query.get(session['user_id'])
        if not user or not getattr(user, 'is_admin', False):
            abort(403)
        return f(*args, **kwargs)
    return decorated_function

# Routes
@app.route('/')
def index() -> str:
    """Home page route."""
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register() -> str:
    """User registration with email validation."""
    if request.method == 'POST':
        try:
            email = request.form.get('email', '').strip().lower()
            password = request.form.get('password', '')
            confirm_password = request.form.get('confirm_password', '')
            name = request.form.get('name', '').strip()
            
            # Validate inputs
            if not all([email, password, confirm_password, name]):
                flash('All fields are required.', 'danger')
                return render_template('register.html')
            
            # Validate email
            is_valid_email, result = validate_user_email(email)
            if not is_valid_email:
                flash(f'Invalid email: {result}', 'danger')
                return render_template('register.html')
            email = result
            
            # Check if passwords match
            if password != confirm_password:
                flash('Passwords do not match.', 'danger')
                return render_template('register.html')
            
            # Validate password strength
            is_strong, password_msg = validate_password_strength(password)
            if not is_strong:
                flash(password_msg, 'danger')
                return render_template('register.html')
            
            # Check if user already exists
            if User.query.filter_by(email=email).first():
                flash('Email address already registered.', 'danger')
                return render_template('register.html')
            
            # Create new user
            user = User(email=email, name=name)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            
            # Send verification email
            token = user.generate_verification_token()
            verification_url = url_for('verify_email', token=token, _external=True)
            
            msg = Message(
                'Verify Your Email Address',
                recipients=[email]
            )
            msg.body = f'''Welcome to our platform, {name}!

Please verify your email address by clicking the link below:
{verification_url}

This link will expire in 1 hour.

If you did not create this account, please ignore this email.
'''
            msg.html = f'''
<h2>Welcome to our platform, {name}!</h2>
<p>Please verify your email address by clicking the link below:</p>
<p><a href="{verification_url}">Verify Email</a></p>
<p>This link will expire in 1 hour.</p>
<p>If you did not create this account, please ignore this email.</p>
'''
            try:
                mail.send(msg)
                logger.info(f"Verification email sent to {email}")
            except Exception as e:
                logger.error(f"Failed to send verification email: {str(e)}")
                flash('Registration successful but email verification could not be sent. Please contact support.', 'warning')
            
            flash('Registration successful! Please check your email to verify your account.', 'success')
            return redirect(url_for('login'))
            
        except Exception as e:
            logger.error(f"Registration error: {str(e)}", exc_info=True)
            flash('An error occurred during registration. Please try again.', 'danger')
            db.session.rollback()
            return render_template('register.html')
    
    return render_template('register.html')

@app.route('/verify-email/<token>')
def verify_email(token: str) -> str:
    """Verify user email using token."""
    try:
        email = User.verify_token(token)
        if not email:
            flash('The verification link is invalid or has expired.', 'danger')
            return redirect(url_for('login'))
        
        user = User.query.filter_by(email=email).first()
        if not user:
            flash('User not found.', 'danger')
            return redirect(url_for('login'))
        
        if user.email_verified:
            flash('Email already verified. Please log in.', 'info')
            return redirect(url_for('login'))
        
        user.email_verified = True
        db.session.commit()
        logger.info(f"Email verified for user: {email}")
        flash('Your email has been verified! You can now log in.', 'success')
        return redirect(url_for('login'))
        
    except Exception as e:
        logger.error(f"Email verification error: {str(e)}", exc_info=True)
        flash('An error occurred during email verification.', 'danger')
        return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login() -> str:
    """User login with session management."""
    if request.method == 'POST':
        try:
            email = request.form.get('email', '').strip().lower()
            password = request.form.get('password', '')
            remember_me = request.form.get('remember_me') == 'on'
            
            if not email or not password:
                flash('Email and password are required.', 'danger')
                return render_template('login.html')
            
            user = User.query.filter_by(email=email).first()
            
            if not user or not user.check_password(password):
                logger.warning(f"Failed login attempt for email: {email}")
                flash('Invalid email or password.', 'danger')
                return render_template('login.html')
            
            if not user.email_verified:
                flash('Please verify your email address before logging in.', 'warning')
                return render_template('login.html')
            
            # Set session
            session.clear()
            session['user_id'] = user.id
            session['email'] = user.email
            session.permanent = remember_me
            
            user.last_login = datetime.utcnow()
            db.session.commit()
            
            logger.info(f"Successful login for user: {email}")
            flash(f'Welcome back, {user.name}!', 'success')
            
            next_page = request.args.get('next')
            if next_page and next_page.startswith('/'):
                return redirect(next_page)
            return redirect(url_for('profile'))
            
        except Exception as e:
            logger.error(f"Login error: {str(e)}", exc_info=True)
            flash('An error occurred during login. Please try again.', 'danger')
            return render_template('login.html')
    
    return render_template('login.html')

@app.route('/logout')
def logout() -> str:
    """User logout and session cleanup."""
    user_id = session.get('user_id')
    if user_id:
        logger.info(f"User logged out: ID {user_id}")
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))

@app.route('/profile')
@login_required
def profile() -> str:
    """Display user profile page."""
    user = User.query.get(session['user_id'])
    if not user:
        session.clear()
        flash('User not found. Please log in again.', 'danger')
        return redirect(url_for('login'))
    return render_template('profile.html', user=user)

@app.route('/profile/edit', methods=['GET', 'POST'])
@login_required
def edit_profile() -> str:
    """Edit user profile information."""
    user = User.query.get(session['user_id'])
    if not user:
        session.clear()
        flash('User not found.', 'danger')
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        try:
            name = request.form.get('name', '').strip()
            
            if not name:
                flash('Name is required.', 'danger')
                return render_template('edit_profile.html', user=user)
            
            user.name = name
            db.session.commit()
            logger.info(f"Profile updated for user: {user.email}")
            flash('Profile updated successfully!', 'success')
            return redirect(url_for('profile'))
            
        except Exception as e:
            logger.error(f"Profile update error: {str(e)}", exc_info=True)
            flash('An error occurred while updating profile.', 'danger')
            db.session.rollback()
    
    return render_template('edit_profile.html', user=user)

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password() -> str:
    """Handle forgot password requests."""
    if request.method == 'POST':
        try:
            email = request.form.get('email', '').strip().lower()
            
            if not email:
                flash('Email address is required.', 'danger')
                return render_template('forgot_password.html')
            
            user = User.query.filter_by(email=email).first()
            
            # Always return success to prevent email enumeration
            flash('If the email exists, a password reset link has been sent.', 'info')
            
            if user:
                token = user.generate_verification_token()
                reset_url = url_for('reset_password', token=token, _external=True)
                
                msg = Message(
                    'Password Reset Request',
                    recipients=[email]
                )
                msg.body = f'''Dear {user.name},

A password reset was requested for your account. Click the link below to reset your password:
{reset_url}

This link will expire in 1 hour.

If you did not request this, please ignore this email.
'''
                try:
                    mail.send(msg)
                    logger.info(f"Password reset email sent to {email}")
                except Exception as e:
                    logger.error(f"Failed to send reset email: {str(e)}")
            
        except Exception as e:
            logger.error(f"Forgot password error: {str(e)}", exc_info=True)
            flash('An error occurred. Please try again.', 'danger')
    
    return render_template('forgot_password.html')

@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token: str) -> str:
    """Reset password using token."""
    email = User.verify_token(token)
    if not email:
        flash('The reset link is invalid or has expired.', 'danger')
        return redirect(url_for('forgot_password'))
    
    if request.method == 'POST':
        try:
            password = request.form.get('password', '')
            confirm_password = request.form.get('confirm_password', '')
            
            if not password or not confirm_password:
                flash('Both password fields are required.', 'danger')
                return render_template('reset_password.html', token=token)
            
            if password != confirm_password:
                flash('Passwords do not match.', 'danger')
                return render_template('reset_password.html', token=token)
            
            is_strong, password_msg = validate_password_strength(password)
            if not is_strong:
                flash(password_msg, 'danger')
                return render_template('reset_password.html', token=token)
            
            user = User.query.filter_by(email=email).first()
            if not user:
                flash('User not found.', 'danger')
                return redirect(url_for('login'))
            
            user.set_password(password)
            db.session.commit()
            logger.info(f"Password reset successful for user: {email}")
            flash('Your password has been reset. Please log in.', 'success')
            return redirect(url_for('login'))
            
        except Exception as e:
            logger.error(f"Password reset error: {str(e)}", exc_info=True)
            flash('An error occurred. Please try again.', 'danger')
            db.session.rollback()
    
    return render_template('reset_password.html', token=token)

@app.route('/api/user/info')
@login_required
def api_user_info() -> tuple:
    """API endpoint to get current user info."""
    try:
        user = User.query.get(session['user_id'])
        if not user:
            return jsonify({'error': 'User not found'}), 404
        return jsonify(user.to_dict()), 200
    except Exception as e:
        logger.error(f"API user info error: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

# Error handlers
@app.errorhandler(404)
def not_found_error(error: Any) -> tuple:
    """Handle 404 errors."""
    logger.warning(f"404 error: {request.url}")
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error: Any) -> tuple:
    """Handle 500 errors."""
    logger.error(f"500 error: {str(error)}", exc_info=True)
    db.session.rollback()
    return render_template('500.html'), 500

# Template stubs (inline for completeness)
TEMPLATES = {
    'base.html': '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}Login System{% endblock %}</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 40px; background: #f5f5f5; }
        .container { max-width: 600px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .flash { padding: 10px; margin: 10px 0; border-radius: 4px; }
        .flash.success { background: #d4edda; color: #155724; }
        .flash.danger { background: #f8d7da; color: #721c24; }
        .flash.warning { background: #fff3cd; color: #856404; }
        .flash.info { background: #d1ecf1; color: #0c5460; }
        nav { margin-bottom: 20px; }
        nav a { margin-right: 15px; }
    </style>
</head>
<body>
    <nav>
        <a href="/">Home</a>
        {% if session.user_id %}
            <a href="/profile">Profile</a>
            <a href="/logout">Logout</a>
        {% else %}
            <a href="/login">Login</a>
            <a href="/register">Register</a>
        {% endif %}
    </nav>
    <div class="container">
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                    <div class="flash {{ category }}">{{ message }}</div>
                {% endfor %}
            {% endif %}
        {% endwith %}
        {% block content %}{% endblock %}
    </div>
</body>
</html>
''',
    'index.html': '{% extends "base.html" %}\n{% block content %}<h1>Welcome</h1><p>Login System Demo</p>{% endblock %}',
    'register.html': '''
{% extends "base.html" %}
{% block content %}
<h2>Register</h2>
<form method="POST">
    <input type="text" name="name" placeholder="Full Name" required><br><br>
    <input type="email" name="email" placeholder="Email" required><br><br>
    <input type="password" name="password" placeholder="Password" required><br><br>
    <input type="password" name="confirm_password" placeholder="Confirm Password" required><br><br>
    <button type="submit">Register</button>
</form>
{% endblock %}
''',
    'login.html': '''
{% extends "base.html" %}
{% block content %}
<h2>Login</h2>
<form method="POST">
    <input type="email" name="email" placeholder="Email" required><br><br>
    <input type="password" name="password" placeholder="Password" required><br><br>
    <label><input type="checkbox" name="remember_me"> Remember me</label><br><br>
    <button type="submit">Login</button>
</form>
<p><a href="/forgot-password">Forgot Password?</a></p>
{% endblock %}
''',
    'profile.html': '''
{% extends "base.html" %}
{% block content %}
<h2>Profile</h2>
<p>Name: {{ user.name }}</p>
<p>Email: {{ user.email }}</p>
<p>Verified: {{ user.email_verified }}</p>
<p><a href="/profile/edit">Edit Profile</a></p>
{% endblock %}
''',
    'edit_profile.html': '''
{% extends "base.html" %}
{% block content %}
<h2>Edit Profile</h2>
<form method="POST">
    <input type="text" name="name" value="{{ user.name }}" required><br><br>
    <button type="submit">Update</button>
</form>
{% endblock %}
''',
    'forgot_password.html': '''
{% extends "base.html" %}
{% block content %}
<h2>Forgot Password</h2>
<form method="POST">
    <input type="email" name="email" placeholder="Email" required><br><br>
    <button type="submit">Send Reset Link</button>
</form>
{% endblock %}
''',
    'reset_password.html': '''
{% extends "base.html" %}
{% block content %}
<h2>Reset Password</h2>
<form method="POST">
    <input type="password" name="password" placeholder="New Password" required><br><br>
    <input type="password" name="confirm_password" placeholder="Confirm Password" required><br><br>
    <button type="submit">Reset Password</button>
</form>
{% endblock %}
''',
    '404.html': '{% extends "base.html" %}\n{% block content %}<h1>404 - Page Not Found</h1>{% endblock %}',
    '500.html': '{% extends "base.html" %}\n{% block content %}<h1>500 - Internal Server Error</h1>{% endblock %}'
}

def init_db() -> None:
    """Initialize database and create tables."""
    with app.app_context():
        db.create_all()
        logger.info("Database initialized successfully")

def create_templates() -> None:
    """Create template files if they don't exist."""
    import os
    templates_dir = os.path.join(os.path.dirname(__file__), 'templates')
    if not os.path.exists(templates_dir):
        os.makedirs(templates_dir)
    for filename, content in TEMPLATES.items():
        filepath = os.path.join(templates_dir, filename)
        if not os.path.exists(filepath):
            with open(filepath, 'w') as f:
                f.write(content.strip())
    logger.info("Templates created successfully")

if __name__ == '__main__':
    create_templates()
    init_db()
    app.run(debug=True, host='0.0.0.0', port=5000)
