"""
Blog CMS Module

A self-contained blog content management system with user authentication,
post management (CRUD), categories, tags, and comments.
Uses SQLite for storage and standard library for security.
"""

import sqlite3
import hashlib
import secrets
import uuid
import json
import re
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, asdict
from contextlib import contextmanager
from pathlib import Path


@dataclass
class User:
    """Represents a blog user."""
    id: str
    username: str
    email: str
    password_hash: str
    created_at: str
    is_admin: bool = False


@dataclass
class Post:
    """Represents a blog post."""
    id: str
    title: str
    slug: str
    content: str
    author_id: str
    status: str  # draft, published, archived
    created_at: str
    updated_at: str
    published_at: Optional[str] = None


@dataclass
class Category:
    """Represents a post category."""
    id: str
    name: str
    slug: str
    description: str
    created_at: str


@dataclass
class Tag:
    """Represents a post tag."""
    id: str
    name: str
    slug: str
    created_at: str


@dataclass
class Comment:
    """Represents a comment on a post."""
    id: str
    post_id: str
    author_id: str
    content: str
    created_at: str
    updated_at: str
    is_approved: bool = False


class BlogCMSError(Exception):
    """Base exception for Blog CMS errors."""
    pass


class AuthenticationError(BlogCMSError):
    """Authentication related errors."""
    pass


class AuthorizationError(BlogCMSError):
    """Authorization related errors."""
    pass


class ValidationError(BlogCMSError):
    """Input validation errors."""
    pass


class NotFoundError(BlogCMSError):
    """Resource not found errors."""
    pass


class DatabaseError(BlogCMSError):
    """Database operation errors."""
    pass


class BlogCMS:
    """
    Main Blog CMS class handling all operations.
    
    Provides user authentication, post management, categories, tags, and comments.
    Uses parameterized queries to prevent SQL injection.
    """

    def __init__(self, db_path: str = "blog.db") -> None:
        """
        Initialize the Blog CMS with database connection.
        
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
            SQLite connection with row factory set.
            
        Raises:
            DatabaseError: If connection fails.
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            yield conn
        except sqlite3.Error as e:
            raise DatabaseError(f"Database connection failed: {e}") from e
        finally:
            if 'conn' in locals():
                conn.close()

    def _init_database(self) -> None:
        """Initialize database schema with all required tables."""
        schema = """
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            created_at TEXT NOT NULL,
            is_admin INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS posts (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            slug TEXT UNIQUE NOT NULL,
            content TEXT NOT NULL,
            author_id TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'draft',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            published_at TEXT,
            FOREIGN KEY (author_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS categories (
            id TEXT PRIMARY KEY,
            name TEXT UNIQUE NOT NULL,
            slug TEXT UNIQUE NOT NULL,
            description TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS tags (
            id TEXT PRIMARY KEY,
            name TEXT UNIQUE NOT NULL,
            slug TEXT UNIQUE NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS post_categories (
            post_id TEXT NOT NULL,
            category_id TEXT NOT NULL,
            PRIMARY KEY (post_id, category_id),
            FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE,
            FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS post_tags (
            post_id TEXT NOT NULL,
            tag_id TEXT NOT NULL,
            PRIMARY KEY (post_id, tag_id),
            FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE,
            FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS comments (
            id TEXT PRIMARY KEY,
            post_id TEXT NOT NULL,
            author_id TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            is_approved INTEGER DEFAULT 0,
            FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE,
            FOREIGN KEY (author_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_posts_slug ON posts(slug);
        CREATE INDEX IF NOT EXISTS idx_posts_author ON posts(author_id);
        CREATE INDEX IF NOT EXISTS idx_posts_status ON posts(status);
        CREATE INDEX IF NOT EXISTS idx_comments_post ON comments(post_id);
        CREATE INDEX IF NOT EXISTS idx_comments_approved ON comments(is_approved);
        """
        with self._get_connection() as conn:
            conn.executescript(schema)
            conn.commit()

    @staticmethod
    def _hash_password(password: str, salt: Optional[str] = None) -> Tuple[str, str]:
        """
        Hash password using PBKDF2 with SHA-256.
        
        Args:
            password: Plain text password.
            salt: Optional salt, generates new if not provided.
            
        Returns:
            Tuple of (hash, salt) as hex strings.
        """
        if salt is None:
            salt = secrets.token_hex(16)
        hash_obj = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000)
        return hash_obj.hex(), salt

    @staticmethod
    def _verify_password(password: str, password_hash: str, salt: str) -> bool:
        """
        Verify password against hash.
        
        Args:
            password: Plain text password.
            password_hash: Stored hash.
            salt: Stored salt.
            
        Returns:
            True if password matches.
        """
        computed_hash, _ = BlogCMS._hash_password(password, salt)
        return secrets.compare_digest(computed_hash, password_hash)

    @staticmethod
    def _generate_slug(text: str) -> str:
        """
        Generate URL-friendly slug from text.
        
        Args:
            text: Input text.
            
        Returns:
            Slug string.
        """
        slug = re.sub(r'[^\w\s-]', '', text.lower())
        slug = re.sub(r'[-\s]+', '-', slug)
        return slug.strip('-')

    @staticmethod
    def _validate_email(email: str) -> bool:
        """Validate email format."""
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))

    @staticmethod
    def _validate_username(username: str) -> bool:
        """Validate username format."""
        return bool(re.match(r'^[a-zA-Z0-9_]{3,30}$', username))

    # User Management
    def register_user(self, username: str, email: str, password: str, is_admin: bool = False) -> User:
        """
        Register a new user.
        
        Args:
            username: Unique username (3-30 alphanumeric/underscore).
            email: Unique email address.
            password: Plain text password (min 8 chars).
            is_admin: Whether user is admin.
            
        Returns:
            Created User object.
            
        Raises:
            ValidationError: If input validation fails.
            DatabaseError: If username/email already exists.
        """
        if not self._validate_username(username):
            raise ValidationError("Username must be 3-30 alphanumeric characters or underscores")
        if not self._validate_email(email):
            raise ValidationError("Invalid email format")
        if len(password) < 8:
            raise ValidationError("Password must be at least 8 characters")

        user_id = str(uuid.uuid4())
        password_hash, salt = self._hash_password(password)
        created_at = datetime.utcnow().isoformat()

        with self._get_connection() as conn:
            try:
                conn.execute(
                    """INSERT INTO users (id, username, email, password_hash, salt, created_at, is_admin)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (user_id, username, email, password_hash, salt, created_at, int(is_admin))
                )
                conn.commit()
            except sqlite3.IntegrityError as e:
                if "username" in str(e):
                    raise DatabaseError("Username already exists") from e
                elif "email" in str(e):
                    raise DatabaseError("Email already exists") from e
                raise DatabaseError(f"Registration failed: {e}") from e

        return User(
            id=user_id,
            username=username,
            email=email,
            password_hash=password_hash,
            created_at=created_at,
            is_admin=is_admin
        )

    def authenticate_user(self, username: str, password: str) -> User:
        """
        Authenticate user with username and password.
        
        Args:
            username: Username or email.
            password: Plain text password.
            
        Returns:
            Authenticated User object.
            
        Raises:
            AuthenticationError: If credentials invalid.
        """
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE username = ? OR email = ?",
                (username, username)
            ).fetchone()

        if not row:
            raise AuthenticationError("Invalid credentials")

        if not self._verify_password(password, row["password_hash"], row["salt"]):
            raise AuthenticationError("Invalid credentials")

        return User(
            id=row["id"],
            username=row["username"],
            email=row["email"],
            password_hash=row["password_hash"],
            created_at=row["created_at"],
            is_admin=bool(row["is_admin"])
        )

    def get_user(self, user_id: str) -> User:
        """
        Get user by ID.
        
        Args:
            user_id: User ID.
            
        Returns:
            User object.
            
        Raises:
            NotFoundError: If user not found.
        """
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()

        if not row:
            raise NotFoundError(f"User {user_id} not found")

        return User(
            id=row["id"],
            username=row["username"],
            email=row["email"],
            password_hash=row["password_hash"],
            created_at=row["created_at"],
            is_admin=bool(row["is_admin"])
        )

    def update_user(self, user_id: str, email: Optional[str] = None, 
                    password: Optional[str] = None, is_admin: Optional[bool] = None) -> User:
        """
        Update user details.
        
        Args:
            user_id: User ID.
            email: New email (optional).
            password: New password (optional).
            is_admin: Admin status (optional).
            
        Returns:
            Updated User object.
            
        Raises:
            NotFoundError: If user not found.
            ValidationError: If validation fails.
        """
        user = self.get_user(user_id)
        updates = []
        params = []

        if email is not None:
            if not self._validate_email(email):
                raise ValidationError("Invalid email format")
            updates.append("email = ?")
            params.append(email)

        if password is not None:
            if len(password) < 8:
                raise ValidationError("Password must be at least 8 characters")
            password_hash, salt = self._hash_password(password)
            updates.append("password_hash = ?")
            updates.append("salt = ?")
            params.extend([password_hash, salt])

        if is_admin is not None:
            updates.append("is_admin = ?")
            params.append(int(is_admin))

        if not updates:
            return user

        params.append(user_id)
        with self._get_connection() as conn:
            try:
                conn.execute(f"UPDATE users SET {', '.join(updates)} WHERE id = ?", params)
                conn.commit()
            except sqlite3.IntegrityError as e:
                raise DatabaseError(f"Update failed: {e}") from e

        return self.get_user(user_id)

    def delete_user(self, user_id: str, requester_id: str) -> None:
        """
        Delete a user (admin only or self).
        
        Args:
            user_id: User to delete.
            requester_id: ID of user making request.
            
        Raises:
            NotFoundError: If user not found.
            AuthorizationError: If not authorized.
        """
        requester = self.get_user(requester_id)
        target = self.get_user(user_id)

        if not requester.is_admin and requester.id != target.id:
            raise AuthorizationError("Not authorized to delete this user")

        with self._get_connection() as conn:
            conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
            conn.commit()

    # Category Management
    def create_category(self, name: str, description: str = "") -> Category:
        """
        Create a new category.
        
        Args:
            name: Category name.
            description: Category description.
            
        Returns:
            Created Category object.
            
        Raises:
            ValidationError: If name empty.
            DatabaseError: If category exists.
        """
        if not name.strip():
            raise ValidationError("Category name cannot be empty")

        category_id = str(uuid.uuid4())
        slug = self._generate_slug(name)
        created_at = datetime.utcnow().isoformat()

        with self._get_connection() as conn:
            try:
                conn.execute(
                    "INSERT INTO categories (id, name, slug, description, created_at) VALUES (?, ?, ?, ?, ?)",
                    (category_id, name, slug, description, created_at)
                )
                conn.commit()
            except sqlite3.IntegrityError as e:
                raise DatabaseError(f"Category already exists: {e}") from e

        return Category(
            id=category_id,
            name=name,
            slug=slug,
            description=description,
            created_at=created_at
        )

    def get_category(self, category_id: str) -> Category:
        """Get category by ID."""
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM categories WHERE id = ?", (category_id,)).fetchone()

        if not row:
            raise NotFoundError(f"Category {category_id} not found")

        return Category(
            id=row["id"],
            name=row["name"],
            slug=row["slug"],
            description=row["description"],
            created_at=row["created_at"]
        )

    def list_categories(self) -> List[Category]:
        """List all categories."""
        with self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM categories ORDER BY name").fetchall()

        return [
            Category(
                id=row["id"],
                name=row["name"],
                slug=row["slug"],
                description=row["description"],
                created_at=row["created_at"]
            )
            for row in rows
        ]

    def update_category(self, category_id: str, name: Optional[str] = None,
                        description: Optional[str] = None) -> Category:
        """Update category."""
        category = self.get_category(category_id)
        updates = []
        params = []

        if name is not None:
            if not name.strip():
                raise ValidationError("Category name cannot be empty")
            updates.append("name = ?")
            updates.append("slug = ?")
            params.extend([name, self._generate_slug(name)])

        if description is not None:
            updates.append("description = ?")
            params.append(description)

        if not updates:
            return category

        params.append(category_id)
        with self._get_connection() as conn:
            try:
                conn.execute(f"UPDATE categories SET {', '.join(updates)} WHERE id = ?", params)
                conn.commit()
            except sqlite3.IntegrityError as e:
                raise DatabaseError(f"Update failed: {e}") from e

        return self.get_category(category_id)

    def delete_category(self, category_id: str) -> None:
        """Delete category