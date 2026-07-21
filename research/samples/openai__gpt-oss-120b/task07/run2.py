"""
blog_cms.py

A lightweight, self‑contained blog content management system (CMS) supporting:

* User registration and authentication with secure password hashing (bcrypt).
* CRUD operations for posts, including categories and tags.
* Comment creation and retrieval.
* Simple in‑memory session token handling.

All data is persisted in a SQLite database using parameterised queries to
prevent SQL injection. The module relies only on the Python standard library
and the widely‑used ``bcrypt`` package.
"""

from __future__ import annotations

import datetime
import hashlib
import secrets
import sqlite3
import threading
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

import bcrypt  # type: ignore[import]

# --------------------------------------------------------------------------- #
# Exceptions
# --------------------------------------------------------------------------- #


class BlogError(Exception):
    """Base class for all blog CMS errors."""


class AuthenticationError(BlogError):
    """Raised when authentication fails."""


class AuthorizationError(BlogError):
    """Raised when a user attempts an operation they are not permitted to perform."""


class NotFoundError(BlogError):
    """Raised when a requested resource does not exist."""


# --------------------------------------------------------------------------- #
# Data models
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class User:
    """Simple user representation."""

    id: int
    username: str


@dataclass(frozen=True)
class Post:
    """Simple post representation."""

    id: int
    author_id: int
    title: str
    content: str
    created_at: datetime.datetime
    updated_at: datetime.datetime
    categories: List[str]
    tags: List[str]


@dataclass(frozen=True)
class Comment:
    """Simple comment representation."""

    id: int
    post_id: int
    author_id: int
    content: str
    created_at: datetime.datetime


# --------------------------------------------------------------------------- #
# Core CMS implementation
# --------------------------------------------------------------------------- #


class BlogCMS:
    """
    Blog content management system.

    All methods raise :class:`BlogError` subclasses on failure.
    """

    _TOKEN_TTL = datetime.timedelta(hours=2)

    def __init__(self, db_path: str = ":memory:") -> None:
        """
        Initialise the CMS, creating tables if they do not exist.

        Args:
            db_path: Filesystem path to the SQLite database. ``:memory:`` creates
                a temporary in‑memory database.
        """
        self._db_path = db_path
        self._conn_lock = threading.Lock()
        self._session_store: Dict[str, Tuple[int, datetime.datetime]] = {}
        self._initialize_database()

    # ------------------------------------------------------------------- #
    # Database utilities
    # ------------------------------------------------------------------- #

    def _get_connection(self) -> sqlite3.Connection:
        """Return a new SQLite connection with row factory set to dict."""
        conn = sqlite3.connect(self._db_path, detect_types=sqlite3.PARSE_DECLTYPES)
        conn.row_factory = sqlite3.Row
        return conn

    def _initialize_database(self) -> None:
        """Create tables required for the CMS."""
        schema = """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash BLOB NOT NULL
        );
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            author_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP NOT NULL,
            updated_at TIMESTAMP NOT NULL,
            FOREIGN KEY(author_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        );
        CREATE TABLE IF NOT EXISTS tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        );
        CREATE TABLE IF NOT EXISTS post_categories (
            post_id INTEGER NOT NULL,
            category_id INTEGER NOT NULL,
            PRIMARY KEY (post_id, category_id),
            FOREIGN KEY(post_id) REFERENCES posts(id) ON DELETE CASCADE,
            FOREIGN KEY(category_id) REFERENCES categories(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS post_tags (
            post_id INTEGER NOT NULL,
            tag_id INTEGER NOT NULL,
            PRIMARY KEY (post_id, tag_id),
            FOREIGN KEY(post_id) REFERENCES posts(id) ON DELETE CASCADE,
            FOREIGN KEY(tag_id) REFERENCES tags(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER NOT NULL,
            author_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP NOT NULL,
            FOREIGN KEY(post_id) REFERENCES posts(id) ON DELETE CASCADE,
            FOREIGN KEY(author_id) REFERENCES users(id) ON DELETE CASCADE
        );
        """
        with self._conn_lock, self._get_connection() as conn:
            conn.executescript(schema)

    # ------------------------------------------------------------------- #
    # Authentication helpers
    # ------------------------------------------------------------------- #

    @staticmethod
    def _hash_password(password: str) -> bytes:
        """
        Hash a plaintext password using bcrypt.

        Args:
            password: Plaintext password.

        Returns:
            A bcrypt hash.
        """
        return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())

    @staticmethod
    def _verify_password(password: str, hashed: bytes) -> bool:
        """
        Verify a plaintext password against a stored bcrypt hash.

        Args:
            password: Plaintext password.
            hashed: Stored bcrypt hash.

        Returns:
            True if the password matches, False otherwise.
        """
        return bcrypt.checkpw(password.encode("utf-8"), hashed)

    def register_user(self, username: str, password: str) -> int:
        """
        Register a new user.

        Args:
            username: Desired username (must be unique).
            password: Plaintext password.

        Returns:
            The newly created user's ID.

        Raises:
            BlogError: If the username already exists or database error occurs.
        """
        if not username or not password:
            raise BlogError("Username and password cannot be empty.")
        password_hash = self._hash_password(password)
        query = "INSERT INTO users (username, password_hash) VALUES (?, ?);"
        with self._conn_lock, self._get_connection() as conn:
            try:
                cur = conn.execute(query, (username, password_hash))
                return cur.lastrowid
            except sqlite3.IntegrityError as exc:
                raise BlogError(f"Username '{username}' already taken.") from exc

    def login(self, username: str, password: str) -> str:
        """
        Authenticate a user and return a session token.

        Args:
            username: User's username.
            password: Plaintext password.

        Returns:
            A session token string.

        Raises:
            AuthenticationError: If credentials are invalid.
        """
        query = "SELECT id, password_hash FROM users WHERE username = ?;"
        with self._conn_lock, self._get_connection() as conn:
            row = conn.execute(query, (username,)).fetchone()
        if row is None:
            raise AuthenticationError("Invalid username or password.")
        if not self._verify_password(password, row["password_hash"]):
            raise AuthenticationError("Invalid username or password.")
        token = secrets.token_urlsafe(32)
        expiry = datetime.datetime.utcnow() + self._TOKEN_TTL
        self._session_store[token] = (row["id"], expiry)
        return token

    def _validate_token(self, token: str) -> int:
        """
        Validate a session token and return the associated user ID.

        Args:
            token: Session token.

        Returns:
            User ID linked to the token.

        Raises:
            AuthenticationError: If token is missing, expired, or invalid.
        """
        if token not in self._session_store:
            raise AuthenticationError("Invalid session token.")
        user_id, expiry = self._session_store[token]
        if datetime.datetime.utcnow() > expiry:
            del self._session_store[token]
            raise AuthenticationError("Session token has expired.")
        # Refresh expiry
        self._session_store[token] = (user_id, datetime.datetime.utcnow() + self._TOKEN_TTL)
        return user_id

    # ------------------------------------------------------------------- #
    # Post management
    # ------------------------------------------------------------------- #

    def create_post(
        self,
        token: str,
        title: str,
        content: str,
        categories: Optional[Sequence[str]] = None,
        tags: Optional[Sequence[str]] = None,
    ) -> int:
        """
        Create a new blog post.

        Args:
            token: Valid session token of the author.
            title: Post title.
            content: Post body/content.
            categories: Optional list of category names.
            tags: Optional list of tag names.

        Returns:
            The newly created post's ID.

        Raises:
            AuthenticationError: If token is invalid.
            BlogError: If title/content are empty or DB error occurs.
        """
        author_id = self._validate_token(token)
        if not title.strip() or not content.strip():
            raise BlogError("Title and content cannot be empty.")
        now = datetime.datetime.utcnow()
        insert_post = """
            INSERT INTO posts (author_id, title, content, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?);
        """
        with self._conn_lock, self._get_connection() as conn:
            cur = conn.execute(insert_post, (author_id, title, content, now, now))
            post_id = cur.lastrowid
            self._associate_categories(conn, post_id, categories or [])
            self._associate_tags(conn, post_id, tags or [])
            conn.commit()
        return post_id

    def _get_or_create_category(self, conn: sqlite3.Connection, name: str) -> int:
        """Return the ID of a category, creating it if necessary."""
        name = name.strip().lower()
        cur = conn.execute("SELECT id FROM categories WHERE name = ?;", (name,))
        row = cur.fetchone()
        if row:
            return row["id"]
        cur = conn.execute("INSERT INTO categories (name) VALUES (?);", (name,))
        return cur.lastrowid

    def _get_or_create_tag(self, conn: sqlite3.Connection, name: str) -> int:
        """Return the ID of a tag, creating it if necessary."""
        name = name.strip().lower()
        cur = conn.execute("SELECT id FROM tags WHERE name = ?;", (name,))
        row = cur.fetchone()
        if row:
            return row["id"]
        cur = conn.execute("INSERT INTO tags (name) VALUES (?);", (name,))
        return cur.lastrowid

    def _associate_categories(
        self, conn: sqlite3.Connection, post_id: int, categories: Sequence[str]
    ) -> None:
        """Link a post to the supplied categories."""
        for cat in categories:
            cat_id = self._get_or_create_category(conn, cat)
            conn.execute(
                "INSERT OR IGNORE INTO post_categories (post_id, category_id) VALUES (?, ?);",
                (post_id, cat_id),
            )

    def _associate_tags(self, conn: sqlite3.Connection, post_id: int, tags: Sequence[str]) -> None:
        """Link a post to the supplied tags."""
        for tag in tags:
            tag_id = self._get_or_create_tag(conn, tag)
            conn.execute(
                "INSERT OR IGNORE INTO post_tags (post_id, tag_id) VALUES (?, ?);",
                (post_id, tag_id),
            )

    def read_post(self, post_id: int) -> Post:
        """
        Retrieve a post by its ID.

        Args:
            post_id: Identifier of the post.

        Returns:
            A :class:`Post` dataclass instance.

        Raises:
            NotFoundError: If the post does not exist.
        """
        post_query = """
            SELECT * FROM posts WHERE id = ?;
        """
        with self._conn_lock, self._get_connection() as conn:
            row = conn.execute(post_query, (post_id,)).fetchone()
            if row is None:
                raise NotFoundError(f"Post with id {post_id} not found.")
            categories = self._fetch_post_categories(conn, post_id)
            tags = self._fetch_post_tags(conn, post_id)
        return Post(
            id=row["id"],
            author_id=row["author_id"],
            title=row["title"],
            content=row["content"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            categories=categories,
            tags=tags,
        )

    def _fetch_post_categories(self, conn: sqlite3.Connection, post_id: int) -> List[str]:
        query = """
            SELECT c.name FROM categories c
            JOIN post_categories pc ON c.id = pc.category_id
            WHERE pc.post_id = ?;
        """
        rows = conn.execute(query, (post_id,)).fetchall()
        return [r["name"] for r in rows]

    def _fetch_post_tags(self, conn: sqlite3.Connection, post_id: int) -> List[str]:
        query = """
            SELECT t.name FROM tags t
            JOIN post_tags pt ON t.id = pt.tag_id
            WHERE pt.post_id = ?;
        """
        rows = conn.execute(query, (post_id,)).fetchall()
        return [r["name"] for r in rows]

    def update_post(
        self,
        token: str,
        post_id: int,
        title: Optional[str] = None,
        content: Optional[str] = None,
        categories: Optional[Sequence[str]] = None,
        tags: Optional[Sequence[str]] = None,
    ) -> None:
        """
        Update an existing post. Only the author may modify their post.

        Args:
            token: Session token of the requesting user.
            post_id: Identifier of the post to update.
            title: New title (optional).
            content: New content (optional).
            categories: New list of categories (optional, replaces existing).
            tags: New list of tags (optional, replaces existing).

        Raises:
            AuthenticationError: If token invalid.
            AuthorizationError: If user is not the author.
            NotFoundError: If the post does not exist.
            BlogError: If supplied data is invalid.
        """
        user_id = self._validate_token(token)
        with self._conn_lock, self._get_connection() as conn:
            post = conn.execute("SELECT * FROM posts WHERE id = ?;", (post_id,)).fetchone()
            if post is None:
                raise NotFoundError(f"Post {post_id} not found.")
            if post["author_id"] != user_id:
                raise AuthorizationError("You may only edit your own posts.")
            updates: List[str] = []
            params: List[Any] = []
            if title is not None:
                if not title.strip():
                    raise BlogError("Title cannot be empty.")
                updates.append("title = ?")
                params.append(title)
            if content is not None:
                if not content.strip():
                    raise BlogError("Content cannot be empty.")
                updates.append("content = ?")
                params.append(content)
            if updates:
                updates.append("updated_at = ?")
                params.append(datetime.datetime.utcnow())
                params.append(post_id)
                sql = f"UPDATE posts SET {', '.join(updates)} WHERE id = ?;"
                conn.execute(sql, tuple(params))
            # Replace categories/tags if supplied
            if categories is not None:
                conn.execute("DELETE FROM post_categories WHERE post_id = ?;", (post_id,))
                self._associate_categories(conn, post_id, categories)
            if tags is not None:
                conn.execute("DELETE FROM post_tags WHERE post_id = ?;", (post_id,))
                self._associate_tags(conn, post_id, tags)
            conn.commit()

    def delete_post(self, token: str, post_id: int) -> None:
        """
        Delete a post. Only the author may delete their post.

        Args:
            token: Session token of the requesting user.
            post_id: Identifier of the post to delete.

        Raises:
            AuthenticationError: If token invalid.
            AuthorizationError: If user is not the author.
            NotFoundError: If the post does not exist.
        """
        user_id = self._validate_token(token)
        with self._conn_lock, self._get_connection() as conn:
            post = conn.execute("SELECT author_id FROM posts WHERE id = ?;", (post_id,)).fetchone()
            if post is None:
                raise NotFoundError(f"Post {post_id} not found.")
            if post["author_id"] != user_id:
                raise AuthorizationError("You may only delete your own posts.")
            conn.execute("DELETE FROM posts WHERE id = ?;", (post_id,))
            conn.commit()

    def list_posts(
        self,
        category: Optional[str] = None,
        tag: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> List[Post]:
        """
        Retrieve a list of posts, optionally filtered by category or tag.

        Args:
            category: Category name to filter by.
            tag: Tag name to filter by.
            limit: Maximum number of posts to return.
            offset: Number of posts to skip (for pagination).

        Returns:
            List of :class:`Post` objects.
        """
        base = "SELECT p.* FROM posts p"
        joins: List[str] = []
        conditions: List[str] = []
        params: List[Any] = []

        if category:
            joins