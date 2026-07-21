"""
Forum Board Application

A complete forum board implementation with user authentication, posts, comments,
voting, and search functionality. Built with Flask and SQLite.

Security Features:
- Password hashing with bcrypt
- SQL injection prevention via parameterized queries
- CSRF protection for state-changing operations
- Secure session management
- Input validation and sanitization
- XSS prevention through template auto-escaping

Dependencies:
- flask (web framework)
- bcrypt (password hashing)
"""

import os
import secrets
import hashlib
import sqlite3
import re
from datetime import datetime
from functools import wraps
from typing import Optional, List, Dict, Any, Tuple, Union
from contextlib import contextmanager

from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, g, abort, make_response
)
import bcrypt


# ============================================================================
# Configuration
# ============================================================================

class Config:
    """Application configuration."""
    SECRET_KEY: str = os.environ.get('SECRET_KEY', secrets.token_hex(32))
    DATABASE: str = os.environ.get('DATABASE_PATH', 'forum.db')
    BCRYPT_ROUNDS: int = 12
    SESSION_COOKIE_HTTPONLY: bool = True
    SESSION_COOKIE_SECURE: bool = False  # Set True in production with HTTPS
    SESSION_COOKIE_SAMESITE: str = 'Lax'
    MAX_CONTENT_LENGTH: int = 16 * 1024 * 1024  # 16 MB


app = Flask(__name__)
app.config.from_object(Config)


# ============================================================================
# Database Layer
# ============================================================================

@contextmanager
def get_db() -> sqlite3.Connection:
    """
    Get a database connection with row factory.
    
    Yields:
        sqlite3.Connection: Database connection with row_factory set.
        
    Raises:
        sqlite3.Error: If database connection fails.
    """
    conn = sqlite3.connect(app.config['DATABASE'])
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    try:
        yield conn
        conn.commit()
    except sqlite3.Error:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    """
    Initialize the database schema.
    
    Creates tables for users, posts, comments, and votes if they don't exist.
    
    Raises:
        sqlite3.Error: If schema creation fails.
    """
    with get_db() as conn:
        conn.executescript('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_admin BOOLEAN DEFAULT FALSE
            );
            
            CREATE TABLE IF NOT EXISTS posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            
            CREATE TABLE IF NOT EXISTS comments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                post_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            
            CREATE TABLE IF NOT EXISTS votes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                post_id INTEGER,
                comment_id INTEGER,
                vote_type INTEGER NOT NULL CHECK (vote_type IN (-1, 1)),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE,
                FOREIGN KEY (comment_id) REFERENCES comments(id) ON DELETE CASCADE,
                UNIQUE(user_id, post_id),
                UNIQUE(user_id, comment_id),
                CHECK (
                    (post_id IS NOT NULL AND comment_id IS NULL) OR
                    (post_id IS NULL AND comment_id IS NOT NULL)
                )
            );
            
            CREATE INDEX IF NOT EXISTS idx_posts_user ON posts(user_id);
            CREATE INDEX IF NOT EXISTS idx_comments_post ON comments(post_id);
            CREATE INDEX IF NOT EXISTS idx_comments_user ON comments(user_id);
            CREATE INDEX IF NOT EXISTS idx_votes_post ON votes(post_id);
            CREATE INDEX IF NOT EXISTS idx_votes_comment ON votes(comment_id);
            CREATE INDEX IF NOT EXISTS idx_votes_user ON votes(user_id);
        ''')


# ============================================================================
# Authentication & Session Management
# ============================================================================

def hash_password(password: str) -> str:
    """
    Hash a password using bcrypt.
    
    Args:
        password: Plain text password.
        
    Returns:
        str: Bcrypt hash of the password.
        
    Raises:
        ValueError: If password is empty or too long.
    """
    if not password:
        raise ValueError("Password cannot be empty")
    if len(password) > 72:  # bcrypt limit
        raise ValueError("Password too long (max 72 characters)")
    
    salt = bcrypt.gensalt(rounds=app.config['BCRYPT_ROUNDS'])
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')


def verify_password(password: str, password_hash: str) -> bool:
    """
    Verify a password against its bcrypt hash.
    
    Args:
        password: Plain text password.
        password_hash: Stored bcrypt hash.
        
    Returns:
        bool: True if password matches, False otherwise.
    """
    try:
        return bcrypt.checkpw(
            password.encode('utf-8'),
            password_hash.encode('utf-8')
        )
    except (ValueError, TypeError):
        return False


def generate_csrf_token() -> str:
    """
    Generate a CSRF token and store in session.
    
    Returns:
        str: The generated CSRF token.
    """
    if 'csrf_token' not in session:
        session['csrf_token'] = secrets.token_hex(32)
    return session['csrf_token']


def validate_csrf_token(token: str) -> bool:
    """
    Validate a CSRF token against session.
    
    Args:
        token: Token to validate.
        
    Returns:
        bool: True if valid, False otherwise.
    """
    return secrets.compare_digest(session.get('csrf_token', ''), token)


def login_required(f):
    """
    Decorator to require user login for a route.
    
    Args:
        f: View function to wrap.
        
    Returns:
        Wrapped function that checks authentication.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'error')
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function


def get_current_user() -> Optional[sqlite3.Row]:
    """
    Get the currently logged-in user from database.
    
    Returns:
        sqlite3.Row or None: User row if logged in, None otherwise.
    """
    if 'user_id' not in session:
        return None
    
    with get_db() as conn:
        user = conn.execute(
            'SELECT id, username, email, created_at, is_admin FROM users WHERE id = ?',
            (session['user_id'],)
        ).fetchone()
    
    if user is None:
        session.clear()
    return user


@app.before_request
def load_user() -> None:
    """Load current user into g before each request."""
    g.user = get_current_user()
    g.csrf_token = generate_csrf_token()


# ============================================================================
# Input Validation & Sanitization
# ============================================================================

def validate_username(username: str) -> Tuple[bool, str]:
    """
    Validate username format.
    
    Args:
        username: Username to validate.
        
    Returns:
        Tuple of (is_valid, error_message).
    """
    if not username:
        return False, "Username is required"
    if len(username) < 3:
        return False, "Username must be at least 3 characters"
    if len(username) > 30:
        return False, "Username must be at most 30 characters"
    if not re.match(r'^[a-zA-Z0-9_-]+$', username):
        return False, "Username can only contain letters, numbers, underscore, and hyphen"
    return True, ""


def validate_email(email: str) -> Tuple[bool, str]:
    """
    Validate email format.
    
    Args:
        email: Email to validate.
        
    Returns:
        Tuple of (is_valid, error_message).
    """
    if not email:
        return False, "Email is required"
    if len(email) > 254:
        return False, "Email is too long"
    # Simple RFC 5322 compliant regex
    pattern = r'^[a-zA-Z0-9.!#$%&\'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)+$'
    if not re.match(pattern, email):
        return False, "Invalid email format"
    return True, ""


def validate_password(password: str) -> Tuple[bool, str]:
    """
    Validate password strength.
    
    Args:
        password: Password to validate.
        
    Returns:
        Tuple of (is_valid, error_message).
    """
    if not password:
        return False, "Password is required"
    if len(password) < 8:
        return False, "Password must be at least 8 characters"
    if len(password) > 72:
        return False, "Password must be at most 72 characters"
    if not re.search(r'[A-Z]', password):
        return False, "Password must contain at least one uppercase letter"
    if not re.search(r'[a-z]', password):
        return False, "Password must contain at least one lowercase letter"
    if not re.search(r'\d', password):
        return False, "Password must contain at least one number"
    return True, ""


def validate_post_title(title: str) -> Tuple[bool, str]:
    """
    Validate post title.
    
    Args:
        title: Title to validate.
        
    Returns:
        Tuple of (is_valid, error_message).
    """
    if not title or not title.strip():
        return False, "Title is required"
    if len(title.strip()) > 200:
        return False, "Title must be at most 200 characters"
    return True, ""


def validate_content(content: str, max_length: int = 10000) -> Tuple[bool, str]:
    """
    Validate post/comment content.
    
    Args:
        content: Content to validate.
        max_length: Maximum allowed length.
        
    Returns:
        Tuple of (is_valid, error_message).
    """
    if not content or not content.strip():
        return False, "Content is required"
    if len(content) > max_length:
        return False, f"Content must be at most {max_length} characters"
    return True, ""


def sanitize_search_query(query: str) -> str:
    """
    Sanitize search query for SQLite FTS.
    
    Args:
        query: Raw search query.
        
    Returns:
        str: Sanitized query safe for MATCH clause.
    """
    # Remove special FTS characters except quotes for phrase search
    sanitized = re.sub(r'[^\w\s\-\"\']', ' ', query)
    # Limit length
    return sanitized[:200].strip()


# ============================================================================
# User Operations
# ============================================================================

def create_user(username: str, email: str, password: str) -> int:
    """
    Create a new user account.
    
    Args:
        username: Desired username.
        email: User's email address.
        password: Plain text password.
        
    Returns:
        int: ID of the newly created user.
        
    Raises:
        ValueError: If validation fails or user already exists.
        sqlite3.Error: If database operation fails.
    """
    valid, msg = validate_username(username)
    if not valid:
        raise ValueError(msg)
    
    valid, msg = validate_email(email)
    if not valid:
        raise ValueError(msg)
    
    valid, msg = validate_password(password)
    if not valid:
        raise ValueError(msg)
    
    password_hash = hash_password(password)
    
    with get_db() as conn:
        cursor = conn.execute(
            'INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)',
            (username.strip(), email.strip().lower(), password_hash)
        )
        return cursor.lastrowid


def authenticate_user(username_or_email: str, password: str) -> Optional[sqlite3.Row]:
    """
    Authenticate a user with username/email and password.
    
    Args:
        username_or_email: Username or email.
        password: Plain text password.
        
    Returns:
        sqlite3.Row or None: User row if authentication succeeds, None otherwise.
    """
    with get_db() as conn:
        user = conn.execute(
            'SELECT id, username, email, password_hash, is_admin FROM users '
            'WHERE username = ? OR email = ?',
            (username_or_email, username_or_email.lower())
        ).fetchone()
    
    if user and verify_password(password, user['password_hash']):
        return user
    return None


def get_user_by_id(user_id: int) -> Optional[sqlite3.Row]:
    """
    Get user by ID.
    
    Args:
        user_id: User ID to look up.
        
    Returns:
        sqlite3.Row or None: User row if found, None otherwise.
    """
    with get_db() as conn:
        return conn.execute(
            'SELECT id, username, email, created_at, is_admin FROM users WHERE id = ?',
            (user_id,)
        ).fetchone()


# ============================================================================
# Post Operations
# ============================================================================

def create_post(user_id: int, title: str, content: str) -> int:
    """
    Create a new post.
    
    Args:
        user_id: ID of the author.
        title: Post title.
        content: Post content.
        
    Returns:
        int: ID of the newly created post.
        
    Raises:
        ValueError: If validation fails.
        sqlite3.Error: If database operation fails.
    """
    valid, msg = validate_post_title(title)
    if not valid:
        raise ValueError(msg)
    
    valid, msg = validate_content(content)
    if not valid:
        raise ValueError(msg)
    
    with get_db() as conn:
        cursor = conn.execute(
            'INSERT INTO posts (user_id, title, content) VALUES (?, ?, ?)',
            (user_id, title.strip(), content.strip())
        )
        return cursor.lastrowid


def get_post(post_id: int) -> Optional[sqlite3.Row]:
    """
    Get a post by ID with author info and vote counts.
    
    Args:
        post_id: Post ID to retrieve.
        
    Returns:
        sqlite3.Row or None: Post with aggregated data if found.
    """
    with get_db() as conn:
        return conn.execute('''
            SELECT 
                p.id, p.user_id, p.title, p.content, p.created_at, p.updated_at,
                u.username as author_username,
                COALESCE(SUM(CASE WHEN v.vote_type = 1 THEN 1 ELSE 0 END), 0) as upvotes,
                COALESCE(SUM(CASE WHEN v.vote_type = -1 THEN 1 ELSE 0 END), 0) as downvotes
            FROM posts p
            JOIN users u ON p.user_id = u.id
            LEFT JOIN votes v ON v.post_id = p.id
            WHERE p.id = ?
            GROUP BY p.id
        ''', (post_id,)).fetchone()


def get_posts(page: int = 1, per_page: int = 20) -> Tuple[List[sqlite3.Row], int]:
    """
    Get paginated list of posts