"""
Forum Board Module

A self-contained forum board implementation with user authentication, posts, comments,
voting, and search functionality. Uses SQLite for storage and follows security best practices.

Features:
- User registration and login with secure password hashing (PBKDF2)
- Session management with secure tokens
- Create, edit, delete posts and comments
- Upvote/downvote on posts and comments
- Full-text search across posts
- Input validation and SQL injection prevention
- Comprehensive error handling

Dependencies: Python standard library only (sqlite3, hashlib, secrets, etc.)
"""

import sqlite3
import hashlib
import secrets
import re
import time
from datetime import datetime, timedelta
from typing import Optional, List, Tuple, Dict, Any, Union
from dataclasses import dataclass
from contextlib import contextmanager
from functools import wraps
import json


# ============================================================================
# Custom Exceptions
# ============================================================================

class ForumError(Exception):
    """Base exception for forum errors."""
    pass

class ValidationError(ForumError):
    """Raised when input validation fails."""
    pass

class AuthenticationError(ForumError):
    """Raised when authentication fails."""
    pass

class AuthorizationError(ForumError):
    """Raised when user lacks permission for an action."""
    pass

class NotFoundError(ForumError):
    """Raised when a requested resource is not found."""
    pass

class DatabaseError(ForumError):
    """Raised when a database operation fails."""
    pass


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class User:
    """Represents a forum user."""
    id: int
    username: str
    email: str
    created_at: datetime
    is_admin: bool = False

@dataclass
class Post:
    """Represents a forum post."""
    id: int
    author_id: int
    title: str
    content: str
    created_at: datetime
    updated_at: Optional[datetime]
    is_deleted: bool
    upvotes: int = 0
    downvotes: int = 0
    comment_count: int = 0

@dataclass
class Comment:
    """Represents a comment on a post."""
    id: int
    post_id: int
    author_id: int
    content: str
    created_at: datetime
    updated_at: Optional[datetime]
    is_deleted: bool
    upvotes: int = 0
    downvotes: int = 0

@dataclass
class Vote:
    """Represents a user's vote on a post or comment."""
    user_id: int
    target_type: str  # 'post' or 'comment'
    target_id: int
    vote_type: int    # 1 for upvote, -1 for downvote
    created_at: datetime

@dataclass
class Session:
    """Represents a user session."""
    token: str
    user_id: int
    created_at: datetime
    expires_at: datetime


# ============================================================================
# Database Manager
# ============================================================================

class DatabaseManager:
    """Manages database connections and schema initialization."""

    def __init__(self, db_path: str = "forum.db"):
        self.db_path = db_path
        self._init_schema()

    @contextmanager
    def connection(self):
        """Provide a transactional database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_schema(self) -> None:
        """Initialize database schema."""
        with self.connection() as conn:
            # Users table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    salt TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_admin BOOLEAN DEFAULT FALSE
                )
            """)

            # Posts table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS posts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    author_id INTEGER NOT NULL REFERENCES users(id),
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP,
                    is_deleted BOOLEAN DEFAULT FALSE
                )
            """)

            # Comments table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS comments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    post_id INTEGER NOT NULL REFERENCES posts(id),
                    author_id INTEGER NOT NULL REFERENCES users(id),
                    content TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP,
                    is_deleted BOOLEAN DEFAULT FALSE
                )
            """)

            # Votes table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS votes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    target_type TEXT NOT NULL CHECK(target_type IN ('post', 'comment')),
                    target_id INTEGER NOT NULL,
                    vote_type INTEGER NOT NULL CHECK(vote_type IN (1, -1)),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, target_type, target_id)
                )
            """)

            # Sessions table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    token TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP NOT NULL
                )
            """)

            # Indexes for performance
            conn.execute("CREATE INDEX IF NOT EXISTS idx_posts_author ON posts(author_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_comments_post ON comments(post_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_comments_author ON comments(author_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_votes_target ON votes(target_type, target_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires_at)")

            # Full-text search virtual table
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS posts_fts USING fts5(
                    title, content, author_id, post_id UNINDEXED,
                    tokenize='porter unicode61'
                )
            """)

            # Triggers to keep FTS table in sync
            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS posts_fts_insert AFTER INSERT ON posts BEGIN
                    INSERT INTO posts_fts(title, content, author_id, post_id)
                    VALUES (NEW.title, NEW.content, NEW.author_id, NEW.id);
                END
            """)
            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS posts_fts_update AFTER UPDATE ON posts BEGIN
                    UPDATE posts_fts SET title=NEW.title, content=NEW.content
                    WHERE post_id=NEW.id;
                END
            """)
            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS posts_fts_delete AFTER DELETE ON posts BEGIN
                    DELETE FROM posts_fts WHERE post_id=OLD.id;
                END
            """)


# ============================================================================
# Security Utilities
# ============================================================================

class Security:
    """Security-related utilities."""

    PBKDF2_ITERATIONS = 100000
    HASH_ALGORITHM = 'sha256'
    SALT_LENGTH = 32
    TOKEN_LENGTH = 32
    SESSION_DAYS = 30

    @staticmethod
    def hash_password(password: str, salt: Optional[bytes] = None) -> Tuple[str, str]:
        """
        Hash a password with PBKDF2.

        Args:
            password: Plain text password
            salt: Optional salt (generated if not provided)

        Returns:
            Tuple of (hash_hex, salt_hex)
        """
        if salt is None:
            salt = secrets.token_bytes(Security.SALT_LENGTH)
        elif isinstance(salt, str):
            salt = bytes.fromhex(salt)

        hash_bytes = hashlib.pbkdf2_hmac(
            Security.HASH_ALGORITHM,
            password.encode('utf-8'),
            salt,
            Security.PBKDF2_ITERATIONS
        )
        return hash_bytes.hex(), salt.hex()

    @staticmethod
    def verify_password(password: str, password_hash: str, salt: str) -> bool:
        """Verify a password against its hash."""
        computed_hash, _ = Security.hash_password(password, salt)
        return secrets.compare_digest(computed_hash, password_hash)

    @staticmethod
    def generate_token() -> str:
        """Generate a secure random token."""
        return secrets.token_hex(Security.TOKEN_LENGTH)

    @staticmethod
    def validate_username(username: str) -> bool:
        """Validate username format."""
        return bool(re.match(r'^[a-zA-Z0-9_]{3,30}$', username))

    @staticmethod
    def validate_email(email: str) -> bool:
        """Validate email format."""
        return bool(re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email))

    @staticmethod
    def validate_password(password: str) -> bool:
        """Validate password strength."""
        return len(password) >= 8

    @staticmethod
    def sanitize_text(text: str, max_length: int = 10000) -> str:
        """Sanitize text input."""
        # Remove null bytes and control characters except newlines/tabs
        sanitized = ''.join(char for char in text if char == '\n' or char == '\t' or ord(char) >= 32)
        return sanitized[:max_length]


# ============================================================================
# Forum Core
# ============================================================================

class Forum:
    """Main forum application class."""

    def __init__(self, db_path: str = "forum.db"):
        self.db = DatabaseManager(db_path)
        self.security = Security()

    # ---------------------------------------------------------------------
    # Authentication & Session Management
    # ---------------------------------------------------------------------

    def register_user(self, username: str, email: str, password: str) -> User:
        """
        Register a new user.

        Args:
            username: Desired username (3-30 alphanumeric/underscore)
            email: User's email address
            password: Password (min 8 characters)

        Returns:
            Created User object

        Raises:
            ValidationError: If input validation fails
            DatabaseError: If username/email already exists
        """
        # Validate inputs
        if not self.security.validate_username(username):
            raise ValidationError("Username must be 3-30 alphanumeric characters or underscores")
        if not self.security.validate_email(email):
            raise ValidationError("Invalid email format")
        if not self.security.validate_password(password):
            raise ValidationError("Password must be at least 8 characters")

        password_hash, salt = self.security.hash_password(password)

        with self.db.connection() as conn:
            try:
                cursor = conn.execute(
                    """INSERT INTO users (username, email, password_hash, salt)
                       VALUES (?, ?, ?, ?)""",
                    (username, email, password_hash, salt)
                )
                user_id = cursor.lastrowid
            except sqlite3.IntegrityError as e:
                if "username" in str(e):
                    raise ValidationError("Username already taken")
                elif "email" in str(e):
                    raise ValidationError("Email already registered")
                raise DatabaseError("Registration failed")

        return self._get_user_by_id(user_id)

    def login(self, username: str, password: str) -> str:
        """
        Authenticate user and create session.

        Args:
            username: Username or email
            password: Password

        Returns:
            Session token

        Raises:
            AuthenticationError: If credentials are invalid
        """
        with self.db.connection() as conn:
            user_row = conn.execute(
                """SELECT id, password_hash, salt FROM users
                   WHERE username = ? OR email = ?""",
                (username, username)
            ).fetchone()

        if not user_row:
            raise AuthenticationError("Invalid username or password")

        if not self.security.verify_password(password, user_row['password_hash'], user_row['salt']):
            raise AuthenticationError("Invalid username or password")

        return self._create_session(user_row['id'])

    def logout(self, token: str) -> bool:
        """
        Invalidate a session.

        Args:
            token: Session token

        Returns:
            True if session was found and removed
        """
        with self.db.connection() as conn:
            cursor = conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
            return cursor.rowcount > 0

    def validate_session(self, token: str) -> User:
        """
        Validate session token and return associated user.

        Args:
            token: Session token

        Returns:
            User object

        Raises:
            AuthenticationError: If session is invalid or expired
        """
        with self.db.connection() as conn:
            session_row = conn.execute(
                """SELECT user_id, expires_at FROM sessions WHERE token = ?""",
                (token,)
            ).fetchone()

        if not session_row:
            raise AuthenticationError("Invalid session")

        if datetime.fromisoformat(session_row['expires_at']) < datetime.now():
            self.logout(token)
            raise AuthenticationError("Session expired")

        return self._get_user_by_id(session_row['user_id'])

    def _create_session(self, user_id: int) -> str:
        """Create a new session for user."""
        token = self.security.generate_token()
        expires_at = datetime.now() + timedelta(days=self.security.SESSION_DAYS)

        with self.db.connection() as conn:
            conn.execute(
                """INSERT INTO sessions (token, user_id, expires_at)
                   VALUES (?, ?, ?)""",
                (token, user_id, expires_at.isoformat())
            )
        return token

    def _get_user_by_id(self, user_id: int) -> User:
        """Get user by ID."""
        with self.db.connection() as conn:
            row = conn.execute(
                "SELECT id, username, email, created_at, is_admin FROM users WHERE id = ?",
                (user_id,)
            ).fetchone()

        if not row:
            raise NotFoundError("User not found")

        return User(
            id=row['id'],
            username=row['username'],
            email=row['email'],
            created_at=datetime.fromisoformat(row['created_at']),
            is_admin=bool(row['is_admin'])
        )

    # ---------------------------------------------------------------------
    # Post Management
    # ---------------------------------------------------------------------

    def create_post(self, token: str, title: str, content: str) -> Post:
        """
        Create a new post.

        Args:
            token: Session token
            title: Post title (max 200 chars)
            content: Post content

        Returns:
            Created Post object

        Raises:
            AuthenticationError: If session invalid
            ValidationError: If title/content invalid
        """
        user = self.validate_session(token)

        title = self.security.sanitize_text(title.strip