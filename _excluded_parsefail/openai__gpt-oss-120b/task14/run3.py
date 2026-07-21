"""forum.py
A lightweight forum implementation with user registration, authentication, posting,
commenting, voting, and search functionalities.

Features
--------
- Secure password storage using PBKDF2-HMAC.
- Session management with cryptographically‑secure tokens.
- SQLite persistence (standard library only).
- Explicit error handling via custom exception hierarchy.
- Type‑annotated public API and comprehensive docstrings.

The module is self‑contained and can be imported directly.
"""

from __future__ import annotations

import datetime
import hashlib
import os
import secrets
import sqlite3
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

# --------------------------------------------------------------------------- #
# Exceptions
# --------------------------------------------------------------------------- #


class ForumError(Exception):
    """Base class for all forum‑related errors."""


class AuthenticationError(ForumError):
    """Raised when authentication fails (e.g., bad credentials, expired token)."""


class AuthorizationError(ForumError):
    """Raised when a user attempts an action they are not permitted to perform."""


class NotFoundError(ForumError):
    """Raised when a requested resource (user, post, comment) does not exist."""


# --------------------------------------------------------------------------- #
# Data models
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class User:
    """Simple data container for a forum user."""
    id: int
    username: str
    created_at: datetime.datetime


@dataclass(frozen=True)
class Post:
    """Simple data container for a forum post."""
    id: int
    author_id: int
    title: str
    body: str
    created_at: datetime.datetime
    updated_at: datetime.datetime
    score: int


@dataclass(frozen=True)
class Comment:
    """Simple data container for a comment on a post."""
    id: int
    post_id: int
    author_id: int
    body: str
    created_at: datetime.datetime
    updated_at: datetime.datetime
    score: int


# --------------------------------------------------------------------------- #
# Helper functions for password handling
# --------------------------------------------------------------------------- #


_HASH_NAME = "sha256"
_ITERATIONS = 100_000
_SALT_SIZE = 16
_TOKEN_BYTES = 32
_SESSION_TIMEOUT = datetime.timedelta(hours=2)


def _hash_password(password: str, salt: bytes) -> bytes:
    """
    Derive a cryptographic hash from ``password`` and ``salt`` using PBKDF2‑HMAC.

    Parameters
    ----------
    password: str
        The plaintext password.
    salt: bytes
        Randomly generated salt.

    Returns
    -------
    bytes
        The derived key (hash) to store.
    """
    password_bytes = password.encode("utf-8")
    return hashlib.pbkdf2_hmac(_HASH_NAME, password_bytes, salt, _ITERATIONS)


def _verify_password(stored_hash: bytes, stored_salt: bytes, password: str) -> bool:
    """
    Verify that ``password`` matches the stored hash/salt pair.

    Returns
    -------
    bool
        ``True`` if the password is correct, else ``False``.
    """
    return stored_hash == _hash_password(password, stored_salt)


# --------------------------------------------------------------------------- #
# Forum core class
# --------------------------------------------------------------------------- #


class Forum:
    """
    Core class providing forum operations.

    All public methods raise :class:`ForumError` subclasses on failure.
    """

    def __init__(self, db_path: str = ":memory:") -> None:
        """
        Initialise the forum, creating the SQLite schema if necessary.

        Parameters
        ----------
        db_path: str, optional
            Path to the SQLite database file. ``":memory:"`` creates a transient
            in‑memory database.
        """
        self._db = sqlite3.connect(db_path, detect_types=sqlite3.PARSE_DECLTYPES)
        self._db.row_factory = sqlite3.Row
        self._create_schema()
        self._sessions: Dict[str, Tuple[int, datetime.datetime]] = {}

    # ------------------------------------------------------------------- #
    # Schema
    # ------------------------------------------------------------------- #

    def _create_schema(self) -> None:
        """Create tables required for the forum if they do not already exist."""
        try:
            cur = self._db.cursor()
            cur.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash BLOB NOT NULL,
                    salt BLOB NOT NULL,
                    created_at TIMESTAMP NOT NULL
                );

                CREATE TABLE IF NOT EXISTS posts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    author_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    body TEXT NOT NULL,
                    created_at TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP NOT NULL,
                    score INTEGER NOT NULL DEFAULT 0,
                    FOREIGN KEY(author_id) REFERENCES users(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS comments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    post_id INTEGER NOT NULL,
                    author_id INTEGER NOT NULL,
                    body TEXT NOT NULL,
                    created_at TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP NOT NULL,
                    score INTEGER NOT NULL DEFAULT 0,
                    FOREIGN KEY(post_id) REFERENCES posts(id) ON DELETE CASCADE,
                    FOREIGN KEY(author_id) REFERENCES users(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS votes (
                    user_id INTEGER NOT NULL,
                    target_type TEXT NOT NULL CHECK(target_type IN ('post','comment')),
                    target_id INTEGER NOT NULL,
                    vote INTEGER NOT NULL CHECK(vote IN (-1,0,1)),
                    PRIMARY KEY(user_id, target_type, target_id),
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                );
                """
            )
            self._db.commit()
        except sqlite3.Error as exc:
            raise ForumError(f"Failed to initialise database schema: {exc}") from exc

    # ------------------------------------------------------------------- #
    # Session handling
    # ------------------------------------------------------------------- #

    def _generate_token(self) -> str:
        """Generate a cryptographically‑secure session token."""
        return secrets.token_urlsafe(_TOKEN_BYTES)

    def _store_session(self, user_id: int) -> str:
        """Create a new session token for ``user_id`` and store it."""
        token = self._generate_token()
        expiry = datetime.datetime.utcnow() + _SESSION_TIMEOUT
        self._sessions[token] = (user_id, expiry)
        return token

    def _validate_token(self, token: str) -> int:
        """
        Validate ``token`` and return the associated user id.

        Raises
        ------
        AuthenticationError
            If the token is unknown or expired.
        """
        try:
            user_id, expiry = self._sessions[token]
        except KeyError:
            raise AuthenticationError("Invalid session token.") from None
        if datetime.datetime.utcnow() > expiry:
            del self._sessions[token]
            raise AuthenticationError("Session token has expired.")
        # Refresh expiry
        self._sessions[token] = (user_id, datetime.datetime.utcnow() + _SESSION_TIMEOUT)
        return user_id

    def logout(self, token: str) -> None:
        """
        Invalidate a session token.

        Parameters
        ----------
        token: str
            The session token to invalidate.
        """
        self._sessions.pop(token, None)

    # ------------------------------------------------------------------- #
    # User management
    # ------------------------------------------------------------------- #

    def register(self, username: str, password: str) -> User:
        """
        Register a new user.

        Parameters
        ----------
        username: str
            Desired unique username.
        password: str
            Plain‑text password (will be hashed).

        Returns
        -------
        User
            The newly created user record.

        Raises
        ------
        ForumError
            If the username already exists or a database error occurs.
        """
        if not username or not password:
            raise ForumError("Username and password cannot be empty.")
        salt = os.urandom(_SALT_SIZE)
        pwd_hash = _hash_password(password, salt)
        created_at = datetime.datetime.utcnow()
        try:
            cur = self._db.cursor()
            cur.execute(
                """
                INSERT INTO users (username, password_hash, salt, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (username, pwd_hash, salt, created_at),
            )
            self._db.commit()
            user_id = cur.lastrowid
            return User(id=user_id, username=username, created_at=created_at)
        except sqlite3.IntegrityError as exc:
            raise ForumError(f"Username '{username}' is already taken.") from exc
        except sqlite3.Error as exc:
            raise ForumError(f"Database error during registration: {exc}") from exc

    def login(self, username: str, password: str) -> str:
        """
        Authenticate a user and obtain a session token.

        Parameters
        ----------
        username: str
        password: str

        Returns
        -------
        str
            Session token to be used with subsequent calls.

        Raises
        ------
        AuthenticationError
            If credentials are invalid.
        """
        try:
            cur = self._db.cursor()
            cur.execute(
                "SELECT id, password_hash, salt FROM users WHERE username = ?",
                (username,),
            )
            row = cur.fetchone()
            if row is None:
                raise AuthenticationError("Invalid username or password.")
            if not _verify_password(row["password_hash"], row["salt"], password):
                raise AuthenticationError("Invalid username or password.")
            token = self._store_session(row["id"])
            return token
        except sqlite3.Error as exc:
            raise ForumError(f"Database error during login: {exc}") from exc

    # ------------------------------------------------------------------- #
    # Post management
    # ------------------------------------------------------------------- #

    def create_post(self, token: str, title: str, body: str) -> Post:
        """
        Create a new post.

        Parameters
        ----------
        token: str
            Valid session token.
        title: str
        body: str

        Returns
        -------
        Post
            The newly created post.

        Raises
        ------
        AuthenticationError
            If token is invalid.
        ForumError
            On validation or database errors.
        """
        if not title or not body:
            raise ForumError("Title and body cannot be empty.")
        author_id = self._validate_token(token)
        now = datetime.datetime.utcnow()
        try:
            cur = self._db.cursor()
            cur.execute(
                """
                INSERT INTO posts (author_id, title, body, created_at, updated_at, score)
                VALUES (?, ?, ?, ?, ?, 0)
                """,
                (author_id, title, body, now, now),
            )
            self._db.commit()
            post_id = cur.lastrowid
            return Post(
                id=post_id,
                author_id=author_id,
                title=title,
                body=body,
                created_at=now,
                updated_at=now,
                score=0,
            )
        except sqlite3.Error as exc:
            raise ForumError(f"Failed to create post: {exc}") from exc

    def edit_post(self, token: str, post_id: int, title: Optional[str] = None,
                  body: Optional[str] = None) -> Post:
        """
        Edit an existing post. Only the author may edit.

        Parameters
        ----------
        token: str
            Valid session token.
        post_id: int
        title: Optional[str]
            New title (if provided).
        body: Optional[str]
            New body (if provided).

        Returns
        -------
        Post
            Updated post object.

        Raises
        ------
        AuthenticationError, AuthorizationError, NotFoundError, ForumError
        """
        user_id = self._validate_token(token)
        if title is None and body is None:
            raise ForumError("No changes supplied for edit.")
        try:
            cur = self._db.cursor()
            cur.execute("SELECT * FROM posts WHERE id = ?", (post_id,))
            row = cur.fetchone()
            if row is None:
                raise NotFoundError("Post not found.")
            if row["author_id"] != user_id:
                raise AuthorizationError("Only the author can edit this post.")
            new_title = title if title is not None else row["title"]
            new_body = body if body is not None else row["body"]
            updated_at = datetime.datetime.utcnow()
            cur.execute(
                """
                UPDATE posts SET title = ?, body = ?, updated_at = ?
                WHERE id = ?
                """,
                (new_title, new_body, updated_at, post_id),
            )
            self._db.commit()
            return Post(
                id=post_id,
                author_id=user_id,
                title=new_title,
                body=new_body,
                created_at=row["created_at"],
                updated_at=updated_at,
                score=row["score"],
            )
        except sqlite3.Error as exc:
            raise ForumError(f"Failed to edit post: {exc}") from exc

    def delete_post(self, token: str, post_id: int) -> None:
        """
        Delete a post and its associated comments/votes. Only the author may delete.

        Parameters
        ----------
        token: str
        post_id: int

        Raises
        ------
        AuthenticationError, AuthorizationError, NotFoundError, ForumError
        """
        user_id = self._validate_token(token)
        try:
            cur = self._db.cursor()
            cur.execute("SELECT author_id FROM posts WHERE id = ?", (post_id,))
            row = cur.fetchone()
            if row is None:
                raise NotFoundError("Post not found.")
            if row["author_id"] != user_id:
                raise AuthorizationError("Only the author can delete this post.")
            cur.execute("DELETE FROM posts WHERE id = ?", (post_id,))
            self._db.commit()
        except sqlite3.Error as exc:
            raise ForumError(f"Failed to delete post: {exc}") from exc

    def get_post(self, post_id: int) -> Post:
        """
        Retrieve a post by its identifier.

        Parameters
        ----------
        post_id: int

        Returns
        -------
        Post

        Raises
        ------
        NotFoundError, ForumError
        """
        try:
            cur = self._db.cursor()
            cur.execute("SELECT * FROM posts WHERE id = ?", (post_id,))
            row = cur.fetchone()
            if row is None:
                raise NotFoundError("Post not found.")
            return Post(
                id=row["id"],
                author_id=row["author_id"],
                title=row["title"],
                body=row["body"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                score=row["score"],
            )
        except sqlite3.Error as exc:
            raise ForumError(f"Database error while fetching post: {exc}") from exc

    # ------------------------------------------------------------------- #
    # Comment management
    # ------------------------------------------------------------------- #

    def add_comment(self, token: str, post_id: int, body: str) -> Comment:
        """
        Add a comment to a post.

        Parameters
        ----------
        token: str
        post_id: int
        body: str

        Returns
        -------
        Comment

        Raises
        ------
        AuthenticationError, NotFoundError, ForumError
        """
        if not body:
            raise ForumError("Comment body cannot be empty.")
        author_id = self._validate_token(token)
        now = datetime.datetime.utcnow()
        try:
            cur = self._db.cursor()
            cur.execute("SELECT id FROM posts WHERE id = ?", (post_id,))
            if cur.fetchone() is None:
                raise NotFoundError("Post not found.")
            cur.execute(
                """
                INSERT INTO comments (post_id, author_id, body, created_at, updated_at, score)
                VALUES (?, ?, ?, ?, ?, 0)
                """,
                (post_id, author_id, body, now, now),
            )
            self._db.commit()
            comment_id = cur.lastrowid
            return Comment(
                id=comment_id,
                post_id=post_id,
                author_id=author_id,
                body=body,
                created_at=now,
                updated_at=now,
                score=0,
            )
        except sqlite3.Error as exc:
            raise ForumError(f"Failed to add comment: {exc}") from exc

    def edit_comment(self, token: str, comment_id: int, body: str) -> Comment:
        """
        Edit an existing comment. Only the author may edit.

        Parameters
        ----------
        token: str
        comment_id: int
        body: str

        Returns
        -------
        Comment

        Raises
        ------
        AuthenticationError, AuthorizationError, NotFoundError, ForumError
        """
        if not body:
            raise ForumError("Comment body cannot be empty.")
        user_id = self._validate_token(token)
        try:
            cur = self._db.cursor()
            cur.execute("SELECT * FROM comments WHERE id = ?", (comment_id,))
            row = cur.fetchone()
            if row is None:
                raise NotFoundError("Comment not found.")
            if row["author_id"] != user_id:
                raise AuthorizationError("Only the author can edit this comment.")
            updated_at = datetime.datetime.utcnow()
            cur.execute(
                """
                UPDATE comments SET body = ?, updated_at = ?
                WHERE id = ?
                """,
                (body, updated_at, comment_id),
            )
            self._db.commit()
            return Comment(
                id=comment_id,
                post_id=row["post_id"],