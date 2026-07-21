"""
forum.py

A lightweight forum implementation supporting user registration and login,
post creation/editing/deletion, comments, voting, and full‑text search.
Data is persisted in a SQLite database; passwords are stored using
bcrypt hashing via ``passlib``. The module is self‑contained and relies only
on the Python standard library and the widely‑used ``passlib`` package.

Typical usage::

    from forum import Forum, ForumError

    forum = Forum(db_path="forum.db")
    user_id = forum.register_user("alice", "s3cr3t")
    token = forum.login_user("alice", "s3cr3t")
    post_id = forum.create_post(token, "Hello", "First post!")
    forum.upvote_post(token, post_id)
    results = forum.search_posts("first")
"""

from __future__ import annotations

import datetime
import sqlite3
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from passlib.context import CryptContext

# --------------------------------------------------------------------------- #
# Exceptions
# --------------------------------------------------------------------------- #


class ForumError(Exception):
    """Base exception for all forum related errors."""


class AuthenticationError(ForumError):
    """Raised when authentication fails."""


class AuthorizationError(ForumError):
    """Raised when a user attempts an operation they are not allowed to."""


class NotFoundError(ForumError):
    """Raised when a requested entity does not exist."""


# --------------------------------------------------------------------------- #
# Data structures
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class User:
    """Immutable representation of a forum user."""

    id: int
    username: str
    created_at: datetime.datetime


@dataclass(frozen=True)
class Post:
    """Immutable representation of a forum post."""

    id: int
    author_id: int
    title: str
    body: str
    created_at: datetime.datetime
    updated_at: datetime.datetime
    score: int


@dataclass(frozen=True)
class Comment:
    """Immutable representation of a comment on a post."""

    id: int
    post_id: int
    author_id: int
    body: str
    created_at: datetime.datetime
    updated_at: datetime.datetime
    score: int


# --------------------------------------------------------------------------- #
# Core forum class
# --------------------------------------------------------------------------- #


class Forum:
    """
    Central class managing users, posts, comments and votes.

    All public methods raise :class:`ForumError` (or subclasses) on failure.
    """

    _pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

    def __init__(self, db_path: str = ":memory:") -> None:
        """
        Initialise the forum, creating required tables if they do not exist.

        Args:
            db_path: Path to the SQLite database file.
        """
        self._db_path = db_path
        self._conn = sqlite3.connect(self._db_path, detect_types=sqlite3.PARSE_DECLTYPES)
        self._conn.row_factory = sqlite3.Row
        self._create_schema()
        # token -> (user_id, expiry)
        self._sessions: Dict[str, Tuple[int, datetime.datetime]] = {}

    # ------------------------------------------------------------------- #
    # Schema creation
    # ------------------------------------------------------------------- #

    def _create_schema(self) -> None:
        """Create database tables if they are missing."""
        try:
            cur = self._conn.cursor()
            cur.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
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

                CREATE TABLE IF NOT EXISTS post_votes (
                    user_id INTEGER NOT NULL,
                    post_id INTEGER NOT NULL,
                    vote INTEGER NOT NULL,
                    PRIMARY KEY(user_id, post_id),
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY(post_id) REFERENCES posts(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS comment_votes (
                    user_id INTEGER NOT NULL,
                    comment_id INTEGER NOT NULL,
                    vote INTEGER NOT NULL,
                    PRIMARY KEY(user_id, comment_id),
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY(comment_id) REFERENCES comments(id) ON DELETE CASCADE
                );

                CREATE VIRTUAL TABLE IF NOT EXISTS post_fts USING fts5(
                    title, body, content='posts', content_rowid='id'
                );

                CREATE VIRTUAL TABLE IF NOT EXISTS comment_fts USING fts5(
                    body, content='comments', content_rowid='id'
                );

                CREATE TRIGGER IF NOT EXISTS post_ai AFTER INSERT ON posts BEGIN
                    INSERT INTO post_fts(rowid, title, body) VALUES (new.id, new.title, new.body);
                END;

                CREATE TRIGGER IF NOT EXISTS post_ad AFTER DELETE ON posts BEGIN
                    INSERT INTO post_fts(post_fts, rowid, title, body) VALUES('delete', old.id, old.title, old.body);
                END;

                CREATE TRIGGER IF NOT EXISTS post_au AFTER UPDATE ON posts BEGIN
                    INSERT INTO post_fts(post_fts, rowid, title, body) VALUES('delete', old.id, old.title, old.body);
                    INSERT INTO post_fts(rowid, title, body) VALUES (new.id, new.title, new.body);
                END;

                CREATE TRIGGER IF NOT EXISTS comment_ai AFTER INSERT ON comments BEGIN
                    INSERT INTO comment_fts(rowid, body) VALUES (new.id, new.body);
                END;

                CREATE TRIGGER IF NOT EXISTS comment_ad AFTER DELETE ON comments BEGIN
                    INSERT INTO comment_fts(comment_fts, rowid, body) VALUES('delete', old.id, old.body);
                END;

                CREATE TRIGGER IF NOT EXISTS comment_au AFTER UPDATE ON comments BEGIN
                    INSERT INTO comment_fts(comment_fts, rowid, body) VALUES('delete', old.id, old.body);
                    INSERT INTO comment_fts(rowid, body) VALUES (new.id, new.body);
                END;
                """
            )
            self._conn.commit()
        except sqlite3.Error as exc:
            raise ForumError(f"Failed to initialise database schema: {exc}") from exc

    # ------------------------------------------------------------------- #
    # Session handling
    # ------------------------------------------------------------------- #

    def _generate_token(self, user_id: int) -> str:
        """Create a new session token for *user_id* valid for 24 hours."""
        token = uuid.uuid4().hex
        expiry = datetime.datetime.utcnow() + datetime.timedelta(hours=24)
        self._sessions[token] = (user_id, expiry)
        return token

    def _validate_token(self, token: str) -> int:
        """
        Validate a session token and return the associated user id.

        Raises:
            AuthenticationError: If token is missing, expired or unknown.
        """
        session = self._sessions.get(token)
        if not session:
            raise AuthenticationError("Invalid session token.")
        user_id, expiry = session
        if datetime.datetime.utcnow() > expiry:
            del self._sessions[token]
            raise AuthenticationError("Session token has expired.")
        return user_id

    # ------------------------------------------------------------------- #
    # User management
    # ------------------------------------------------------------------- #

    def register_user(self, username: str, password: str) -> int:
        """
        Register a new user.

        Args:
            username: Desired unique username.
            password: Plain‑text password.

        Returns:
            The new user's integer id.

        Raises:
            ForumError: If the username already exists or DB error occurs.
        """
        if not username or not password:
            raise ForumError("Username and password cannot be empty.")
        password_hash = self._pwd_context.hash(password)
        created_at = datetime.datetime.utcnow()
        try:
            cur = self._conn.cursor()
            cur.execute(
                "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
                (username, password_hash, created_at),
            )
            self._conn.commit()
            return cur.lastrowid
        except sqlite3.IntegrityError as exc:
            raise ForumError(f"Username '{username}' is already taken.") from exc
        except sqlite3.Error as exc:
            raise ForumError(f"Database error during registration: {exc}") from exc

    def login_user(self, username: str, password: str) -> str:
        """
        Authenticate a user and return a session token.

        Args:
            username: The user's username.
            password: The plain‑text password.

        Returns:
            A session token string.

        Raises:
            AuthenticationError: If credentials are invalid.
            ForumError: On unexpected DB failures.
        """
        try:
            cur = self._conn.cursor()
            cur.execute(
                "SELECT id, password_hash FROM users WHERE username = ?", (username,)
            )
            row = cur.fetchone()
            if not row:
                raise AuthenticationError("Invalid username or password.")
            if not self._pwd_context.verify(password, row["password_hash"]):
                raise AuthenticationError("Invalid username or password.")
            return self._generate_token(row["id"])
        except sqlite3.Error as exc:
            raise ForumError(f"Database error during login: {exc}") from exc

    # ------------------------------------------------------------------- #
    # Post management
    # ------------------------------------------------------------------- #

    def create_post(self, token: str, title: str, body: str) -> int:
        """
        Create a new post.

        Args:
            token: Valid session token.
            title: Post title.
            body: Post body content.

        Returns:
            The new post's integer id.

        Raises:
            AuthenticationError: If token is invalid.
            ForumError: On DB errors or invalid input.
        """
        author_id = self._validate_token(token)
        if not title.strip():
            raise ForumError("Post title cannot be empty.")
        if not body.strip():
            raise ForumError("Post body cannot be empty.")
        now = datetime.datetime.utcnow()
        try:
            cur = self._conn.cursor()
            cur.execute(
                """
                INSERT INTO posts (author_id, title, body, created_at, updated_at, score)
                VALUES (?, ?, ?, ?, ?, 0)
                """,
                (author_id, title, body, now, now),
            )
            self._conn.commit()
            return cur.lastrowid
        except sqlite3.Error as exc:
            raise ForumError(f"Failed to create post: {exc}") from exc

    def edit_post(self, token: str, post_id: int, title: Optional[str] = None, body: Optional[str] = None) -> None:
        """
        Edit an existing post. Only the author may edit.

        Args:
            token: Valid session token.
            post_id: Identifier of the post to edit.
            title: New title (optional).
            body: New body (optional).

        Raises:
            AuthenticationError: If token is invalid.
            AuthorizationError: If user is not the author.
            NotFoundError: If the post does not exist.
            ForumError: On DB errors or if both fields are None.
        """
        user_id = self._validate_token(token)
        if title is None and body is None:
            raise ForumError("At least one of title or body must be provided.")
        try:
            cur = self._conn.cursor()
            cur.execute("SELECT author_id FROM posts WHERE id = ?", (post_id,))
            row = cur.fetchone()
            if not row:
                raise NotFoundError("Post not found.")
            if row["author_id"] != user_id:
                raise AuthorizationError("Only the author may edit this post.")
            updates: List[str] = []
            params: List[Any] = []
            if title is not None:
                updates.append("title = ?")
                params.append(title)
            if body is not None:
                updates.append("body = ?")
                params.append(body)
            updates.append("updated_at = ?")
            params.append(datetime.datetime.utcnow())
            params.append(post_id)
            cur.execute(f"UPDATE posts SET {', '.join(updates)} WHERE id = ?", tuple(params))
            self._conn.commit()
        except sqlite3.Error as exc:
            raise ForumError(f"Failed to edit post: {exc}") from exc

    def delete_post(self, token: str, post_id: int) -> None:
        """
        Delete a post and its associated comments/votes.

        Args:
            token: Valid session token.
            post_id: Identifier of the post to delete.

        Raises:
            AuthenticationError: If token is invalid.
            AuthorizationError: If user is not the author.
            NotFoundError: If post does not exist.
            ForumError: On DB errors.
        """
        user_id = self._validate_token(token)
        try:
            cur = self._conn.cursor()
            cur.execute("SELECT author_id FROM posts WHERE id = ?", (post_id,))
            row = cur.fetchone()
            if not row:
                raise NotFoundError("Post not found.")
            if row["author_id"] != user_id:
                raise AuthorizationError("Only the author may delete this post.")
            cur.execute("DELETE FROM posts WHERE id = ?", (post_id,))
            self._conn.commit()
        except sqlite3.Error as exc:
            raise ForumError(f"Failed to delete post: {exc}") from exc

    def upvote_post(self, token: str, post_id: int) -> None:
        """
        Up‑vote a post. Re‑voting with the same direction has no effect.
        Switching vote direction updates the score accordingly.

        Args:
            token: Valid session token.
            post_id: Identifier of the post.

        Raises:
            AuthenticationError: If token is invalid.
            NotFoundError: If post does not exist.
            ForumError: On DB errors.
        """
        self._vote_entity(token, "post", post_id, 1)

    def downvote_post(self, token: str, post_id: int) -> None:
        """
        Down‑vote a post.

        Args:
            token: Valid session token.
            post_id: Identifier of the post.

        Raises:
            AuthenticationError: If token is invalid.
            NotFoundError: If post does not exist.
            ForumError: On DB errors.
        """
        self._vote_entity(token, "post", post_id, -1)

    # ------------------------------------------------------------------- #
    # Comment management
    # ------------------------------------------------------------------- #

    def add_comment(self, token: str, post_id: int, body: str) -> int:
        """
        Add a comment to a post.

        Args:
            token: Valid session token.
            post_id: Identifier of the post to comment on.
            body: Comment text.

        Returns:
            The new comment's integer id.

        Raises:
            AuthenticationError: If token is invalid.
            NotFoundError: If post does not exist.
            ForumError: On DB errors or empty body.
        """
        user_id = self._validate_token(token)
        if not body.strip():
            raise ForumError("Comment body cannot be empty.")
        now = datetime.datetime.utcnow()
        try:
            cur = self._conn.cursor()
            cur.execute("SELECT id FROM posts WHERE id = ?", (post_id,))
            if not cur.fetchone():
                raise NotFoundError("Post not found.")
            cur.execute(
                """
                INSERT INTO comments (post_id, author_id, body, created_at, updated_at, score)
                VALUES (?, ?, ?, ?, ?, 0)
                """,
                (post_id, user_id, body, now, now),
            )
            self._conn.commit()
            return cur.lastrowid
        except sqlite3.Error as exc:
            raise ForumError(f"Failed to add comment: {exc}") from exc

    def edit_comment(self, token: str, comment_id: int, body: str) -> None:
        """
        Edit a comment's body. Only the author may edit.

        Args:
            token: Valid session token.
            comment_id: Identifier of the comment.
            body: New comment text.

        Raises:
            AuthenticationError: If token is invalid.
            AuthorizationError: If user is not the author.
            NotFoundError: If comment does not exist.
            ForumError: On DB errors or empty body.
        """
        user_id = self._validate_token(token)
        if not body.strip():
            raise ForumError("Comment body cannot be empty.")
        try:
            cur = self._conn.cursor()
            cur.execute("SELECT author_id FROM comments WHERE id = ?", (comment_id,))
            row = cur.fetchone()
            if not row:
                raise NotFoundError("Comment not found.")
            if row["author_id"] != user_id:
                raise AuthorizationError("Only the author may edit this comment.")
            cur.execute(
                "UPDATE comments SET body = ?, updated_at = ? WHERE id = ?",
                (body, datetime.datetime.utcnow(), comment_id),
            )
            self._conn.commit()
        except sqlite3.Error as exc:
            raise ForumError(f"Failed to edit comment: {exc}") from exc

    def delete_comment(self, token: str, comment_id: int) -> None:
        """
        Delete a comment.

        Args:
            token: Valid session token.
            comment_id: Identifier of the comment.

        Raises:
            AuthenticationError: If token is invalid.
            AuthorizationError: If user is not the author.
            NotFoundError: If comment