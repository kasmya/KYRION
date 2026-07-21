"""
A self-contained blog content management system module.

Provides functionality for managing blog posts, user authentication,
comments, and post categorization/tagging with security best practices.
"""

import sqlite3
import hashlib
import secrets
import datetime
import re
from typing import List, Optional, Dict, Any, Tuple, Union
from contextlib import contextmanager
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Data Transfer Objects
# ---------------------------------------------------------------------------

@dataclass
class User:
    """Represents a blog user."""
    id: int
    username: str
    email: str
    is_admin: bool = False
    created_at: str = ""


@dataclass
class Category:
    """Represents a post category."""
    id: int
    name: str
    slug: str


@dataclass
class Tag:
    """Represents a post tag."""
    id: int
    name: str
    slug: str


@dataclass
class Post:
    """Represents a blog post."""
    id: int
    title: str
    slug: str
    content: str
    author_id: int
    status: str  # 'draft' or 'published'
    created_at: str = ""
    updated_at: str = ""
    categories: Optional[List[Category]] = None
    tags: Optional[List[Tag]] = None


@dataclass
class Comment:
    """Represents a comment on a post."""
    id: int
    post_id: int
    author_name: str
    author_email: str
    content: str
    created_at: str = ""
    is_approved: bool = True


# ---------------------------------------------------------------------------
# Security & Utility Helpers
# ---------------------------------------------------------------------------

def _hash_password(password: str, salt: Optional[str] = None) -> Tuple[str, str]:
    """
    Hash a password with a salt using SHA-256 and a random salt.

    Args:
        password: The plaintext password.
        salt: Optional existing salt. If not provided, a new one is generated.

    Returns:
        A tuple of (hashed_password, salt).
    """
    if salt is None:
        salt = secrets.token_hex(16)
    hashed = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"),
                                 salt.encode("utf-8"), 100_000).hex()
    return hashed, salt


def _sanitize_slug(text: str) -> str:
    """
    Create a URL-safe slug from text.

    Args:
        text: The input text.

    Returns:
        A slugified version of the text.
    """
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_]+', '-', text)
    text = re.sub(r'-+', '-', text)
    return text.strip('-')


def _validate_email(email: str) -> bool:
    """
    Validate email format.

    Args:
        email: The email address to validate.

    Returns:
        True if email format is valid, otherwise False.
    """
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None


def _sanitize_html(text: str) -> str:
    """
    Basic HTML sanitisation to prevent XSS.

    Args:
        text: Input text possibly containing HTML.

    Returns:
        Text with dangerous characters escaped.
    """
    replacements = {
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#x27;",
    }
    for char, repl in replacements.items():
        text = text.replace(char, repl)
    return text


# ---------------------------------------------------------------------------
# Database Connection and Schema
# ---------------------------------------------------------------------------

class Database:
    """Encapsulates SQLite database operations."""

    def __init__(self, db_path: str = "blog_cms.db") -> None:
        """
        Initialise Database and create tables if they don't exist.

        Args:
            db_path: Path to the SQLite database file.
        """
        self.db_path: str = db_path
        self._create_tables()

    @contextmanager
    def get_connection(self):
        """
        Context manager for database connections.

        Yields:
            An sqlite3.Connection object.
        """
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

    def _create_tables(self) -> None:
        """Create the database schema if not exists."""
        with self.get_connection() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    password_salt TEXT NOT NULL,
                    is_admin INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS categories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    slug TEXT UNIQUE NOT NULL
                );

                CREATE TABLE IF NOT EXISTS tags (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    slug TEXT UNIQUE NOT NULL
                );

                CREATE TABLE IF NOT EXISTS posts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    slug TEXT UNIQUE NOT NULL,
                    content TEXT NOT NULL,
                    author_id INTEGER NOT NULL,
                    status TEXT DEFAULT 'draft' CHECK(status IN ('draft','published')),
                    created_at TEXT DEFAULT (datetime('now')),
                    updated_at TEXT DEFAULT (datetime('now')),
                    FOREIGN KEY (author_id) REFERENCES users(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS post_categories (
                    post_id INTEGER NOT NULL,
                    category_id INTEGER NOT NULL,
                    PRIMARY KEY (post_id, category_id),
                    FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE,
                    FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS post_tags (
                    post_id INTEGER NOT NULL,
                    tag_id INTEGER NOT NULL,
                    PRIMARY KEY (post_id, tag_id),
                    FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE,
                    FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS comments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    post_id INTEGER NOT NULL,
                    author_name TEXT NOT NULL,
                    author_email TEXT NOT NULL,
                    content TEXT NOT NULL,
                    is_approved INTEGER DEFAULT 1,
                    created_at TEXT DEFAULT (datetime('now')),
                    FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE
                );
            """)


# ---------------------------------------------------------------------------
# User Management
# ---------------------------------------------------------------------------

class UserManager:
    """Handles user registration, authentication and retrieval."""

    def __init__(self, db: Database) -> None:
        """
        Initialise UserManager with a Database instance.

        Args:
            db: A Database object.
        """
        self.db = db

    def register_user(self, username: str, email: str, password: str, is_admin: bool = False) -> Optional[int]:
        """
        Register a new user with a username, email and password.

        Args:
            username: Unique username.
            email: Unique email address.
            password: Plaintext password.
            is_admin: Whether the user has admin privileges.

        Returns:
            New user ID or None if registration fails.

        Raises:
            ValueError: If input validation fails.
        """
        username = _sanitize_html(username.strip())
        email = email.strip().lower()

        if not username or len(username) < 3:
            raise ValueError("Username must be at least 3 characters.")
        if not _validate_email(email):
            raise ValueError("Invalid email address.")
        if len(password) < 8:
            raise ValueError("Password must be at least 8 characters.")

        hashed, salt = _hash_password(password)

        try:
            with self.db.get_connection() as conn:
                cursor = conn.execute(
                    "INSERT INTO users (username, email, password_hash, password_salt, is_admin) VALUES (?,?,?,?,?)",
                    (username, email, hashed, salt, int(is_admin))
                )
                return cursor.lastrowid
        except sqlite3.IntegrityError:
            raise ValueError("Username or email already exists.")

    def authenticate_user(self, username: str, password: str) -> Optional[User]:
        """
        Authenticate a user by username and password.

        Args:
            username: The username.
            password: The password.

        Returns:
            A User object if credentials are valid, else None.
        """
        with self.db.get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE username = ?",
                (username,)
            ).fetchone()

        if row is None:
            return None

        hashed, _ = _hash_password(password, row["password_salt"])
        if hashed == row["password_hash"]:
            return User(
                id=row["id"],
                username=row["username"],
                email=row["email"],
                is_admin=bool(row["is_admin"]),
                created_at=row["created_at"]
            )
        return None

    def get_user_by_id(self, user_id: int) -> Optional[User]:
        """
        Fetch a user by ID.

        Args:
            user_id: The user ID.

        Returns:
            User object or None.
        """
        with self.db.get_connection() as conn:
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            if row:
                return User(
                    id=row["id"],
                    username=row["username"],
                    email=row["email"],
                    is_admin=bool(row["is_admin"]),
                    created_at=row["created_at"]
                )
        return None


# ---------------------------------------------------------------------------
# Category & Tag Management
# ---------------------------------------------------------------------------

class TaxonomyManager:
    """Manage categories and tags."""

    def __init__(self, db: Database) -> None:
        """
        Initialise TaxonomyManager.

        Args:
            db: A Database instance.
        """
        self.db = db

    def create_category(self, name: str) -> Category:
        """
        Create a new category.

        Args:
            name: Category name.

        Returns:
            The newly created Category.

        Raises:
            ValueError: If category already exists or name is invalid.
        """
        name = _sanitize_html(name.strip())
        if not name:
            raise ValueError("Category name cannot be empty.")
        slug = _sanitize_slug(name)
        with self.db.get_connection() as conn:
            try:
                cursor = conn.execute(
                    "INSERT INTO categories (name, slug) VALUES (?, ?)",
                    (name, slug)
                )
                return Category(id=cursor.lastrowid, name=name, slug=slug)
            except sqlite3.IntegrityError:
                raise ValueError(f"Category '{name}' already exists.")

    def create_tag(self, name: str) -> Tag:
        """
        Create a new tag.

        Args:
            name: Tag name.

        Returns:
            The newly created Tag.

        Raises:
            ValueError: If the tag already exists or name is invalid.
        """
        name = _sanitize_html(name.strip())
        if not name:
            raise ValueError("Tag name cannot be empty.")
        slug = _sanitize_slug(name)
        with self.db.get_connection() as conn:
            try:
                cursor = conn.execute(
                    "INSERT INTO tags (name, slug) VALUES (?, ?)",
                    (name, slug)
                )
                return Tag(id=cursor.lastrowid, name=name, slug=slug)
            except sqlite3.IntegrityError:
                raise ValueError(f"Tag '{name}' already exists.")

    def get_all_categories(self) -> List[Category]:
        """
        Retrieve all categories.

        Returns:
            List of Category objects.
        """
        with self.db.get_connection() as conn:
            rows = conn.execute("SELECT * FROM categories ORDER BY name").fetchall()
            return [Category(id=r["id"], name=r["name"], slug=r["slug"]) for r in rows]

    def get_all_tags(self) -> List[Tag]:
        """
        Retrieve all tags.

        Returns:
            List of Tag objects.
        """
        with self.db.get_connection() as conn:
            rows = conn.execute("SELECT * FROM tags ORDER BY name").fetchall()
            return [Tag(id=r["id"], name=r["name"], slug=r["slug"]) for r in rows]

    def delete_category(self, category_id: int) -> bool:
        """
        Delete a category by ID.

        Args:
            category_id: Category ID.

        Returns:
            True if deleted, False if not found.
        """
        with self.db.get_connection() as conn:
            cursor = conn.execute("DELETE FROM categories WHERE id = ?", (category_id,))
            return cursor.rowcount > 0

    def delete_tag(self, tag_id: int) -> bool:
        """
        Delete a tag by ID.

        Args:
            tag_id: Tag ID.

        Returns:
            True if deleted, False if not found.
        """
        with self.db.get_connection() as conn:
            cursor = conn.execute("DELETE FROM tags WHERE id = ?", (tag_id,))
            return cursor.rowcount > 0


# ---------------------------------------------------------------------------
# Post Management
# ---------------------------------------------------------------------------

class PostManager:
    """Handles CRUD operations for posts."""

    def __init__(self, db: Database) -> None:
        """
        Initialise PostManager.

        Args:
            db: A Database instance.
        """
        self.db = db

    def create_post(self, title: str, content: str, author_id: int,
                    status: str = "draft",
                    category_ids: Optional[List[int]] = None,
                    tag_ids: Optional[List[int]] = None) -> Post:
        """
        Create a new blog post.

        Args:
            title: Post title.
            content: Post body.
            author_id: ID of the author (user).
            status: 'draft' or 'published'.
            category_ids: List of category IDs to associate.
            tag_ids: List of tag IDs to associate.

        Returns:
             The created Post object.

        Raises:
            ValueError: On invalid input.
        """
        title = _sanitize_html(title.strip())
        if not title:
            raise ValueError("Title cannot be empty.")
        if status not in ("draft", "published"):
            raise ValueError("Status must be 'draft' or 'published'.")

        slug = _sanitize_slug(title)
        content = _sanitize_html(content)  # basic sanitisation; consider Markdown in real apps

        with self.db.get_connection() as conn:
            try:
                cursor = conn.execute(
                    "INSERT INTO posts (title, slug, content, author_id, status) VALUES (?,?,?,?,?)",
                    (title, slug, content, author_id, status)
                )
                post_id = cursor.lastrowid

                if category_ids:
                    self._set_post_categories(conn, post_id, category_ids)
                if tag_ids:
                    self._set_post_tags(conn, post_id, tag_ids)

                return self.get_post_by_id(post_id)
            except sqlite3.IntegrityError:
                raise ValueError("A post with this slug already exists.")

    def update_post(self, post_id: int, **kwargs: Any) -> Optional[Post]:
        """
        Update a post's fields.

        Args:
            post_id: ID of the post to update.
            **kwargs: Fields to update: title, content, status,
                      category_ids, tag_ids.

        Returns:
            Updated Post object or None if not found.

        Raises:
            ValueError: If status is invalid.
        """
        allowed_fields = {"title", "content", "status"}
        updates = {}
        for k, v in kwargs.items():
            if k in allowed_fields:
                if k == "status" and v not in ("draft", "published"):
                    raise ValueError("Invalid status")
                if k in ("title", "content"):
                    v = _sanitize_html(v.strip())
                updates[k] = v

        if not updates and "category_ids" not in kwargs and "tag_ids" not in kwargs:
            return self.get_post_by_id(post_id)

        with self.db.get_connection() as conn:
            if updates:
                updates["updated_at"] = datetime.datetime.utcnow().isoformat()
                set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
                values = list(updates.values()) + [post_id]
                conn.execute(
                    f"UPDATE posts SET {set_clause} WHERE id = ?",
                    values
                )

            if "category_ids" in kwargs:
                self._set_post_categories(conn, post_id, kwargs["category_ids"])
            if "tag_ids" in kwargs:
                self._set_post_tags(conn, post_id, kwargs["tag_ids"])

            return self.get_post_by_id(post_id)

    def delete_post(self, post_id: int) -> bool:
        """
        Delete a post by ID.

        Args:
            post_id: Post ID.

        Returns:
            True if deleted, False otherwise.
        """
        with self.db.get_connection() as conn:
            cursor = conn.execute("DELETE FROM posts WHERE id = ?", (post_id,))
            return cursor.rowcount > 0

    def get_post_by_id(self, post_id: int) -> Optional[Post]:
        """
        Retrieve a single post by ID, including categories and tags.

        Args:
            post_id: Post ID.

        Returns:
            Post object or None.
        """
        with self.db.get_connection() as conn:
            row = conn.execute("SELECT * FROM posts WHERE id = ?", (post_id,)).fetchone()
            if not row:
                return None
            return self._row_to_post(conn, row)

    def get_posts(self, status: Optional[str] = None,
                  category_id: Optional[int] = None,
                  tag_id: Optional[int] = None,
                  limit: int = 20, offset: int = 0) -> List[Post]:
        """
        Retrieve a list of posts with optional filtering.

        Args:
            status: Filter by 'draft' or 'published'.
            category_id: Filter by category ID.
            tag_id: Filter by tag ID.