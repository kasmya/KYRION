"""
forum.py – A minimal, self‑contained forum implementation.

Features
--------
- User registration with bcrypt password hashing.
- Login returning a UUID‑based session token.
- CRUD operations for posts and comments.
- Upvote/downvote system for posts and comments.
- Full‑text search on post titles and bodies.
- Explicit error handling via custom exception hierarchy.
- All public functions are type‑annotated and documented.

The module uses only the Python standard library and the widely‑used
``passlib`` package for secure password hashing.
"""

from __future__ import annotations

import datetime as _dt
import sqlite3
import threading
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

from passlib.hash import bcrypt

# --------------------------------------------------------------------------- #
# Exceptions
# --------------------------------------------------------------------------- #


class ForumError(Exception):
    """Base class for all forum‑related errors."""


class AuthenticationError(ForumError):
    """Raised when authentication fails (e.g., bad credentials)."""


class AuthorizationError(ForumError):
    """Raised when a user attempts an operation they are not permitted to perform."""


class NotFoundError(ForumError):
    """Raised when a requested resource (user, post, comment) does not exist."""


class ValidationError(ForumError):
    """Raised when input data violates validation rules."""


# --------------------------------------------------------------------------- #
# Data models (simple containers)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class User:
    """Immutable representation of a forum user."""
    id: int
    username: str
    created_at: _dt.datetime


@dataclass(frozen=True, slots=True)
class Post:
    """Immutable representation of a forum post."""
    id: int
    author_id: int
    title: str
    body: str
    created_at: _dt.datetime
    updated_at: _dt.datetime
    score: int


@dataclass(frozen=True, slots=True)
class Comment:
    """Immutable representation of a comment."""
    id: int
    post_id: int
    author_id: int
    body: str
    created_at: _dt.datetime
    updated_at: _dt.datetime
    score: int


# --------------------------------------------------------------------------- #
# Core forum class
# --------------------------------------------------------------------------- #


class Forum:
    """
    Central class managing users, posts, comments and sessions.

    The constructor creates (or connects to) an SQLite database file.
    All mutating operations are protected by a thread‑level lock to
    guarantee consistency in multi‑threaded environments.
    """

    def __init__(self, db_path: str = ":memory:") -> None:
        """
        Initialise the forum database.

        Parameters
        ----------
        db_path:
            Path to the SQLite file. ``\":memory:\"`` creates an in‑memory DB.
        """
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._sessions: Dict[str, Tuple[int, _dt.datetime]] = {}
        self._session_ttl = _dt.timedelta(hours=2)
        self._create_schema()

    # ------------------------------------------------------------------- #
    # Schema creation
    # ------------------------------------------------------------------- #

    def _create_schema(self) -> None:
        """Create database tables if they do not already exist."""
        with self._lock, self._conn:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    created_at TIMESTAMP NOT NULL
                );

                CREATE TABLE IF NOT EXISTS posts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    author_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    title TEXT NOT NULL,
                    body TEXT NOT NULL,
                    created_at TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP NOT NULL,
                    score INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS comments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    post_id INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
                    author_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    body TEXT NOT NULL,
                    created_at TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP NOT NULL,
                    score INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS post_votes (
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    post_id INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
                    vote INTEGER NOT NULL,
                    PRIMARY KEY (user_id, post_id)
                );

                CREATE TABLE IF NOT EXISTS comment_votes (
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    comment_id INTEGER NOT NULL REFERENCES comments(id) ON DELETE CASCADE,
                    vote INTEGER NOT NULL,
                    PRIMARY KEY (user_id, comment_id)
                );

                CREATE VIRTUAL TABLE IF NOT EXISTS post_fts USING fts5(title, body, content='posts', content_rowid='id');
                """
            )
            # Keep FTS index in sync via triggers
            self._conn.executescript(
                """
                CREATE TRIGGER IF NOT EXISTS post_ai AFTER INSERT ON posts BEGIN
                    INSERT INTO post_fts(rowid, title, body) VALUES (new.id, new.title, new.body);
                END;
                CREATE TRIGGER IF NOT EXISTS post_au AFTER UPDATE ON posts BEGIN
                    UPDATE post_fts SET title = new.title, body = new.body WHERE rowid = new.id;
                END;
                CREATE TRIGGER IF NOT EXISTS post_ad AFTER DELETE ON posts BEGIN
                    DELETE FROM post_fts WHERE rowid = old.id;
                END;
                """
            )

    # ------------------------------------------------------------------- #
    # Session handling
    # ------------------------------------------------------------------- #

    def _generate_token(self) -> str:
        """Return a new, cryptographically‑secure session token."""
        return uuid.uuid4().hex

    def _validate_token(self, token: str) -> int:
        """
        Validate a session token and return the associated user ID.

        Raises
        ------
        AuthenticationError
            If the token is missing, expired, or unknown.
        """
        if token not in self._sessions:
            raise AuthenticationError("Invalid session token.")
        user_id, expiry = self._sessions[token]
        if _dt.datetime.utcnow() > expiry:
            del self._sessions[token]
            raise AuthenticationError("Session token has expired.")
        # Refresh expiry on successful use
        self._sessions[token] = (user_id, _dt.datetime.utcnow() + self._session_ttl)
        return user_id

    # ------------------------------------------------------------------- #
    # User management
    # ------------------------------------------------------------------- #

    def register_user(self, username: str, password: str) -> User:
        """
        Register a new user.

        Parameters
        ----------
        username:
            Desired unique username (alphanumeric, 3‑30 chars).
        password:
            Plain‑text password (minimum 8 characters).

        Returns
        -------
        User
            The created user record.

        Raises
        ------
        ValidationError
            If username or password do not meet criteria.
        ForumError
            If the username already exists.
        """
        username = username.strip()
        if not (3 <= len(username) <= 30) or not username.isalnum():
            raise ValidationError("Username must be 3‑30 alphanumeric characters.")
        if len(password) < 8:
            raise ValidationError("Password must be at least 8 characters long.")
        password_hash = bcrypt.hash(password)

        with self._lock, self._conn:
            try:
                cur = self._conn.execute(
                    "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
                    (username, password_hash, _dt.datetime.utcnow()),
                )
                user_id = cur.lastrowid
            except sqlite3.IntegrityError as exc:
                raise ForumError(f"Username '{username}' is already taken.") from exc

        return User(id=user_id, username=username, created_at=_dt.datetime.utcnow())

    def login_user(self, username: str, password: str) -> str:
        """
        Authenticate a user and create a session token.

        Parameters
        ----------
        username:
            The user's username.
        password:
            The user's plain‑text password.

        Returns
        -------
        str
            A session token to be used with subsequent calls.

        Raises
        ------
        AuthenticationError
            If credentials are invalid.
        """
        with self._lock, self._conn:
            cur = self._conn.execute(
                "SELECT id, password_hash FROM users WHERE username = ?", (username,)
            )
            row = cur.fetchone()
            if row is None or not bcrypt.verify(password, row["password_hash"]):
                raise AuthenticationError("Invalid username or password.")
            user_id = row["id"]

        token = self._generate_token()
        self._sessions[token] = (user_id, _dt.datetime.utcnow() + self._session_ttl)
        return token

    # ------------------------------------------------------------------- #
    # Helper methods
    # ------------------------------------------------------------------- #

    def _get_user(self, user_id: int) -> User:
        """Return a User object for the given ID or raise NotFoundError."""
        cur = self._conn.execute(
            "SELECT id, username, created_at FROM users WHERE id = ?", (user_id,)
        )
        row = cur.fetchone()
        if row is None:
            raise NotFoundError(f"User with id {user_id} not found.")
        return User(id=row["id"], username=row["username"], created_at=row["created_at"])

    def _get_post(self, post_id: int) -> Post:
        """Return a Post object for the given ID or raise NotFoundError."""
        cur = self._conn.execute(
            """
            SELECT id, author_id, title, body, created_at, updated_at, score
            FROM posts WHERE id = ?
            """,
            (post_id,),
        )
        row = cur.fetchone()
        if row is None:
            raise NotFoundError(f"Post with id {post_id} not found.")
        return Post(
            id=row["id"],
            author_id=row["author_id"],
            title=row["title"],
            body=row["body"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            score=row["score"],
        )

    def _get_comment(self, comment_id: int) -> Comment:
        """Return a Comment object for the given ID or raise NotFoundError."""
        cur = self._conn.execute(
            """
            SELECT id, post_id, author_id, body, created_at, updated_at, score
            FROM comments WHERE id = ?
            """,
            (comment_id,),
        )
        row = cur.fetchone()
        if row is None:
            raise NotFoundError(f"Comment with id {comment_id} not found.")
        return Comment(
            id=row["id"],
            post_id=row["post_id"],
            author_id=row["author_id"],
            body=row["body"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            score=row["score"],
        )

    # ------------------------------------------------------------------- #
    # Post CRUD
    # ------------------------------------------------------------------- #

    def create_post(self, token: str, title: str, body: str) -> Post:
        """
        Create a new post.

        Parameters
        ----------
        token:
            Valid session token.
        title:
            Title of the post (1‑200 characters).
        body:
            Body content.

        Returns
        -------
        Post
            The newly created post.

        Raises
        ------
        ValidationError
            If the title is empty or too long.
        AuthenticationError
            If the token is invalid.
        """
        user_id = self._validate_token(token)
        title = title.strip()
        if not (1 <= len(title) <= 200):
            raise ValidationError("Title must be between 1 and 200 characters.")
        now = _dt.datetime.utcnow()

        with self._lock, self._conn:
            cur = self._conn.execute(
                """
                INSERT INTO posts (author_id, title, body, created_at, updated_at, score)
                VALUES (?, ?, ?, ?, ?, 0)
                """,
                (user_id, title, body, now, now),
            )
            post_id = cur.lastrowid

        return Post(
            id=post_id,
            author_id=user_id,
            title=title,
            body=body,
            created_at=now,
            updated_at=now,
            score=0,
        )

    def edit_post(self, token: str, post_id: int, title: Optional[str] = None, body: Optional[str] = None) -> Post:
        """
        Edit an existing post. Only the author may edit.

        Parameters
        ----------
        token:
            Valid session token.
        post_id:
            Identifier of the post to edit.
        title:
            New title (optional).
        body:
            New body (optional).

        Returns
        -------
        Post
            Updated post instance.

        Raises
        ------
        AuthorizationError
            If the caller is not the author.
        ValidationError
            If provided fields are invalid.
        """
        user_id = self._validate_token(token)
        post = self._get_post(post_id)
        if post.author_id != user_id:
            raise AuthorizationError("Only the author can edit this post.")

        new_title = title.strip() if title is not None else post.title
        new_body = body if body is not None else post.body
        if not (1 <= len(new_title) <= 200):
            raise ValidationError("Title must be between 1 and 200 characters.")
        now = _dt.datetime.utcnow()

        with self._lock, self._conn:
            self._conn.execute(
                """
                UPDATE posts SET title = ?, body = ?, updated_at = ?
                WHERE id = ?
                """,
                (new_title, new_body, now, post_id),
            )

        return Post(
            id=post.id,
            author_id=post.author_id,
            title=new_title,
            body=new_body,
            created_at=post.created_at,
            updated_at=now,
            score=post.score,
        )

    def delete_post(self, token: str, post_id: int) -> None:
        """
        Delete a post and all its comments.

        Parameters
        ----------
        token:
            Valid session token.
        post_id:
            Identifier of the post to delete.

        Raises
        ------
        AuthorizationError
            If the caller is not the author.
        """
        user_id = self._validate_token(token)
        post = self._get_post(post_id)
        if post.author_id != user_id:
            raise AuthorizationError("Only the author can delete this post.")

        with self._lock, self._conn:
            self._conn.execute("DELETE FROM posts WHERE id = ?", (post_id,))

    # ------------------------------------------------------------------- #
    # Comment CRUD
    # ------------------------------------------------------------------- #

    def add_comment(self, token: str, post_id: int, body: str) -> Comment:
        """
        Add a comment to a post.

        Parameters
        ----------
        token:
            Valid session token.
        post_id:
            Identifier of the post to comment on.
        body:
            Comment text (non‑empty).

        Returns
        -------
        Comment
            The created comment.

        Raises
        ------
        ValidationError
            If the comment body is empty.
        NotFoundError
            If the target post does not exist.
        """
        user_id = self._validate_token(token)
        self._get_post(post_id)  # verify existence
        if not body.strip():
            raise ValidationError("Comment body cannot be empty.")
        now = _dt.datetime.utcnow()

        with self._lock, self._conn:
            cur = self._conn.execute(
                """
                INSERT INTO comments (post_id, author_id, body, created_at, updated_at, score)
                VALUES (?, ?, ?, ?, ?, 0)
                """,
                (post_id, user_id, body, now, now),
            )
            comment_id = cur.lastrowid

        return Comment(
            id=comment_id,
            post_id=post_id,
            author_id=user_id,
            body=body,
            created_at=now,
            updated_at=now,
            score=0,
        )

    def edit_comment(self, token: str, comment_id: int, body: str) -> Comment:
        """
        Edit a comment. Only the author may edit.

        Parameters
        ----------
        token:
            Valid session token.
        comment_id:
            Identifier of the comment to edit.
        body:
            New comment text.

        Returns
        -------
        Comment
            Updated comment.

        Raises
        ------
        AuthorizationError
            If the caller is not the author.
        ValidationError
            If the new body is empty.
        """
        user_id = self._validate_token(token)
        comment = self._get_comment(comment_id)
        if comment.author_id != user_id:
            raise AuthorizationError("Only the author can edit this comment.")
        if not body.strip():
            raise ValidationError("Comment body cannot be empty.")
        now = _dt.datetime.utcnow()

        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE comments SET body = ?, updated_at = ? WHERE id = ?",
                (body, now, comment_id),
            )

        return Comment(
            id=comment.id,
            post_id=comment.post_id,
            author_id=comment.author_id,
            body=body,
            created