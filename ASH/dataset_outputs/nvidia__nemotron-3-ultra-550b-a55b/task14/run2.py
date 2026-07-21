"""
Forum Board Module

A self-contained forum implementation with user authentication, posts, comments,
voting, and search functionality. Uses SQLite for storage and follows security
best practices including parameterized queries, password hashing, and input validation.

Requirements:
- Python 3.8+
- Standard library only (sqlite3, hashlib, secrets, uuid, datetime, re, typing)
"""

import sqlite3
import hashlib
import secrets
import uuid
import re
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple
from contextlib import contextmanager
from dataclasses import dataclass


# Custom Exceptions
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


class DuplicateError(ForumError):
    """Raised when a unique constraint is violated."""
    pass


# Data Classes
@dataclass
class User:
    """Represents a forum user."""
    id: str
    username: str
    created_at: datetime


@dataclass
class Post:
    """Represents a forum post."""
    id: str
    user_id: str
    title: str
    content: str
    created_at: datetime
    updated_at: datetime
    score: int = 0
    comment_count: int = 0


@dataclass
class Comment:
    """Represents a comment on a post."""
    id: str
    post_id: str
    user_id: str
    content: str
    created_at: datetime
    updated_at: datetime
    score: int = 0


@dataclass
class Vote:
    """Represents a vote on a post or comment."""
    user_id: str
    target_type: str  # 'post' or 'comment'
    target_id: str
    value: int  # 1 or -1


class Forum:
    """
    Forum board implementation with full CRUD operations, voting, and search.
    
    Uses SQLite with parameterized queries for security. Passwords are hashed
    using PBKDF2 with SHA-256 and a random salt.
    """
    
    # Constants
    MIN_USERNAME_LENGTH = 3
    MAX_USERNAME_LENGTH = 30
    MIN_PASSWORD_LENGTH = 8
    MAX_PASSWORD_LENGTH = 128
    MAX_TITLE_LENGTH = 200
    MAX_CONTENT_LENGTH = 10000
    MAX_COMMENT_LENGTH = 5000
    PBKDF2_ITERATIONS = 100000
    HASH_ALGORITHM = 'sha256'
    SALT_LENGTH = 16
    
    # Username regex: alphanumeric, underscore, hyphen only
    USERNAME_PATTERN = re.compile(r'^[a-zA-Z0-9_-]+$')
    
    def __init__(self, db_path: str = 'forum.db') -> None:
        """
        Initialize the forum with a database connection.
        
        Args:
            db_path: Path to SQLite database file.
        """
        self.db_path = db_path
        self._init_database()
    
    @contextmanager
    def _get_connection(self) -> sqlite3.Connection:
        """
        Context manager for database connections.
        
        Yields:
            sqlite3.Connection: Database connection with row factory set.
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys = ON')
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    
    def _init_database(self) -> None:
        """Create database tables if they don't exist."""
        with self._get_connection() as conn:
            # Users table
            conn.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    salt TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Posts table
            conn.execute('''
                CREATE TABLE IF NOT EXISTS posts (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            ''')
            
            # Comments table
            conn.execute('''
                CREATE TABLE IF NOT EXISTS comments (
                    id TEXT PRIMARY KEY,
                    post_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            ''')
            
            # Votes table
            conn.execute('''
                CREATE TABLE IF NOT EXISTS votes (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    target_type TEXT NOT NULL CHECK (target_type IN ('post', 'comment')),
                    target_id TEXT NOT NULL,
                    value INTEGER NOT NULL CHECK (value IN (1, -1)),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    UNIQUE(user_id, target_type, target_id)
                )
            ''')
            
            # Indexes for performance
            conn.execute('CREATE INDEX IF NOT EXISTS idx_posts_user ON posts(user_id)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_comments_post ON comments(post_id)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_comments_user ON comments(user_id)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_votes_target ON votes(target_type, target_id)')
            conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_posts_search 
                ON posts(title, content)
            ''')
    
    # --- Password Hashing ---
    def _hash_password(self, password: str, salt: bytes) -> str:
        """
        Hash a password with PBKDF2.
        
        Args:
            password: Plaintext password.
            salt: Random salt bytes.
            
        Returns:
            Hex-encoded hash string.
        """
        hash_obj = hashlib.pbkdf2_hmac(
            self.HASH_ALGORITHM,
            password.encode('utf-8'),
            salt,
            self.PBKDF2_ITERATIONS
        )
        return hash_obj.hex()
    
    def _verify_password(self, password: str, salt: bytes, stored_hash: str) -> bool:
        """
        Verify a password against a stored hash.
        
        Args:
            password: Plaintext password to verify.
            salt: Salt used for original hash.
            stored_hash: Stored hex-encoded hash.
            
        Returns:
            True if password matches, False otherwise.
        """
        computed_hash = self._hash_password(password, salt)
        return secrets.compare_digest(computed_hash, stored_hash)
    
    # --- Input Validation ---
    def _validate_username(self, username: str) -> None:
        """
        Validate username format and length.
        
        Args:
            username: Username to validate.
            
        Raises:
            ValidationError: If username is invalid.
        """
        if not username:
            raise ValidationError("Username cannot be empty")
        if len(username) < self.MIN_USERNAME_LENGTH:
            raise ValidationError(f"Username must be at least {self.MIN_USERNAME_LENGTH} characters")
        if len(username) > self.MAX_USERNAME_LENGTH:
            raise ValidationError(f"Username must be at most {self.MAX_USERNAME_LENGTH} characters")
        if not self.USERNAME_PATTERN.match(username):
            raise ValidationError("Username can only contain letters, numbers, underscores, and hyphens")
    
    def _validate_password(self, password: str) -> None:
        """
        Validate password length.
        
        Args:
            password: Password to validate.
            
        Raises:
            ValidationError: If password is invalid.
        """
        if not password:
            raise ValidationError("Password cannot be empty")
        if len(password) < self.MIN_PASSWORD_LENGTH:
            raise ValidationError(f"Password must be at least {self.MIN_PASSWORD_LENGTH} characters")
        if len(password) > self.MAX_PASSWORD_LENGTH:
            raise ValidationError(f"Password must be at most {self.MAX_PASSWORD_LENGTH} characters")
    
    def _validate_title(self, title: str) -> None:
        """
        Validate post title.
        
        Args:
            title: Title to validate.
            
        Raises:
            ValidationError: If title is invalid.
        """
        if not title or not title.strip():
            raise ValidationError("Title cannot be empty")
        if len(title) > self.MAX_TITLE_LENGTH:
            raise ValidationError(f"Title must be at most {self.MAX_TITLE_LENGTH} characters")
    
    def _validate_content(self, content: str, max_length: int) -> None:
        """
        Validate content length.
        
        Args:
            content: Content to validate.
            max_length: Maximum allowed length.
            
        Raises:
            ValidationError: If content is invalid.
        """
        if not content or not content.strip():
            raise ValidationError("Content cannot be empty")
        if len(content) > max_length:
            raise ValidationError(f"Content must be at most {max_length} characters")
    
    def _validate_vote_value(self, value: int) -> None:
        """
        Validate vote value is 1 or -1.
        
        Args:
            value: Vote value to validate.
            
        Raises:
            ValidationError: If value is invalid.
        """
        if value not in (1, -1):
            raise ValidationError("Vote value must be 1 (upvote) or -1 (downvote)")
    
    # --- User Management ---
    def register(self, username: str, password: str) -> User:
        """
        Register a new user.
        
        Args:
            username: Desired username.
            password: User's password.
            
        Returns:
            User: The newly created user.
            
        Raises:
            ValidationError: If username or password invalid.
            DuplicateError: If username already exists.
        """
        self._validate_username(username)
        self._validate_password(password)
        
        salt = secrets.token_bytes(self.SALT_LENGTH)
        password_hash = self._hash_password(password, salt)
        user_id = str(uuid.uuid4())
        now = datetime.utcnow()
        
        with self._get_connection() as conn:
            try:
                conn.execute(
                    'INSERT INTO users (id, username, password_hash, salt, created_at) VALUES (?, ?, ?, ?, ?)',
                    (user_id, username, password_hash, salt.hex(), now)
                )
            except sqlite3.IntegrityError as e:
                if 'UNIQUE constraint failed: users.username' in str(e):
                    raise DuplicateError(f"Username '{username}' already exists")
                raise
        
        return User(id=user_id, username=username, created_at=now)
    
    def login(self, username: str, password: str) -> User:
        """
        Authenticate a user.
        
        Args:
            username: Username.
            password: Password.
            
        Returns:
            User: The authenticated user.
            
        Raises:
            ValidationError: If username or password empty.
            AuthenticationError: If credentials invalid.
        """
        if not username or not password:
            raise ValidationError("Username and password are required")
        
        with self._get_connection() as conn:
            row = conn.execute(
                'SELECT id, username, password_hash, salt, created_at FROM users WHERE username = ?',
                (username,)
            ).fetchone()
        
        if not row:
            raise AuthenticationError("Invalid username or password")
        
        salt = bytes.fromhex(row['salt'])
        if not self._verify_password(password, salt, row['password_hash']):
            raise AuthenticationError("Invalid username or password")
        
        return User(
            id=row['id'],
            username=row['username'],
            created_at=datetime.fromisoformat(row['created_at'])
        )
    
    def get_user(self, user_id: str) -> User:
        """
        Get a user by ID.
        
        Args:
            user_id: User ID.
            
        Returns:
            User: The user object.
            
        Raises:
            NotFoundError: If user not found.
        """
        with self._get_connection() as conn:
            row = conn.execute(
                'SELECT id, username, created_at FROM users WHERE id = ?',
                (user_id,)
            ).fetchone()
        
        if not row:
            raise NotFoundError(f"User {user_id} not found")
        
        return User(
            id=row['id'],
            username=row['username'],
            created_at=datetime.fromisoformat(row['created_at'])
        )
    
    # --- Post Management ---
    def create_post(self, user_id: str, title: str, content: str) -> Post:
        """
        Create a new post.
        
        Args:
            user_id: Author's user ID.
            title: Post title.
            content: Post content.
            
        Returns:
            Post: The created post.
            
        Raises:
            ValidationError: If title or content invalid.
            NotFoundError: If user not found.
        """
        self._validate_title(title)
        self._validate_content(content, self.MAX_CONTENT_LENGTH)
        
        # Verify user exists
        self.get_user(user_id)
        
        post_id = str(uuid.uuid4())
        now = datetime.utcnow()
        
        with self._get_connection() as conn:
            conn.execute(
                'INSERT INTO posts (id, user_id, title, content, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)',
                (post_id, user_id, title.strip(), content.strip(), now, now)
            )
        
        return Post(
            id=post_id,
            user_id=user_id,
            title=title.strip(),
            content=content.strip(),
            created_at=now,
            updated_at=now
        )
    
    def get_post(self, post_id: str) -> Post:
        """
        Get a post by ID with score and comment count.
        
        Args:
            post_id: Post ID.
            
        Returns:
            Post: The post with computed score and comment count.
            
        Raises:
            NotFoundError: If post not found.
        """
        with self._get_connection()