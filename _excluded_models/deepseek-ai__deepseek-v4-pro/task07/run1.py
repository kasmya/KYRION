"""
A self-contained blog CMS module with user authentication, post management,
comment system, and category/tag support.

Uses only the Python standard library and widely-used PyPI packages:
- bcrypt for password hashing
- cryptography for secure token generation
- sqlite3 (stdlib) for data storage
"""

import sqlite3
import re
import secrets
import datetime
import os
from typing import Optional, List, Dict, Any, Tuple, Union
from dataclasses import dataclass

import bcrypt


# ---------------------------------------------------------------------------
# Constants and configuration
# ---------------------------------------------------------------------------
DEFAULT_DB_PATH = "blog.db"
MIN_PASSWORD_LENGTH = 8
MAX_TITLE_LENGTH = 200
MAX_CONTENT_LENGTH = 10_000
MAX_USERNAME_LENGTH = 50
MAX_COMMENT_LENGTH = 2_000
MAX_TAG_LENGTH = 50
MAX_CATEGORY_LENGTH = 50
SESSION_TOKEN_BYTES = 32
BCRYPT_ROUNDS = 12


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------
@dataclass
class User:
    id: int
    username: str
    password_hash: str
    role: str  # 'admin' or 'author'


@dataclass
class Post:
    id: int
    title: str
    content: str
    author_id: int
    created_at: str
    updated_at: str
    published: bool


@dataclass
class Comment:
    id: int
    post_id: int
    author_name: str
    content: str
    created_at: str


# ---------------------------------------------------------------------------
# Database setup and connection management
# ---------------------------------------------------------------------------
def get_connection(db_path: str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Create and return a database connection with foreign keys enabled."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


def initialize_database(db_path: str = DEFAULT_DB_PATH) -> None:
    """Create all required tables if they do not exist."""
    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'author'
            );

            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE
            );

            CREATE TABLE IF NOT EXISTS tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE
            );

            CREATE TABLE IF NOT EXISTS posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                author_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                published INTEGER NOT NULL DEFAULT 0,
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
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
        """)
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------
def sanitize_html(text: str) -> str:
    """Escape HTML special characters to prevent XSS."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#x27;")
    )


def validate_username(username: str) -> Tuple[bool, str]:
    """Validate username format and length."""
    if not username or len(username.strip()) == 0:
        return False, "Username must not be empty."
    if len(username) > MAX_USERNAME_LENGTH:
        return False, f"Username must not exceed {MAX_USERNAME_LENGTH} characters."
    if not re.match(r"^[a-zA-Z0-9_]+$", username):
        return False, "Username may only contain letters, digits, and underscores."
    return True, ""


def validate_password(password: str) -> Tuple[bool, str]:
    """Validate password meets minimum requirements."""
    if len(password) < MIN_PASSWORD_LENGTH:
        return False, f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
    return True, ""


def validate_title(title: str) -> Tuple[bool, str]:
    """Validate post title."""
    if not title or len(title.strip()) == 0:
        return False, "Title must not be empty."
    if len(title) > MAX_TITLE_LENGTH:
        return False, f"Title must not exceed {MAX_TITLE_LENGTH} characters."
    return True, ""


def validate_content(content: str) -> Tuple[bool, str]:
    """Validate post or comment content length."""
    if not content or len(content.strip()) == 0:
        return False, "Content must not be empty."
    if len(content) > MAX_CONTENT_LENGTH:
        return False, f"Content must not exceed {MAX_CONTENT_LENGTH} characters."
    return True, ""


def validate_comment_content(content: str) -> Tuple[bool, str]:
    """Validate comment content."""
    if not content or len(content.strip()) == 0:
        return False, "Comment must not be empty."
    if len(content) > MAX_COMMENT_LENGTH:
        return False, f"Comment must not exceed {MAX_COMMENT_LENGTH} characters."
    return True, ""


def validate_tag_name(name: str) -> Tuple[bool, str]:
    """Validate tag name."""
    if not name or len(name.strip()) == 0:
        return False, "Tag name must not be empty."
    if len(name) > MAX_TAG_LENGTH:
        return False, f"Tag name must not exceed {MAX_TAG_LENGTH} characters."
    if not re.match(r"^[a-zA-Z0-9_-]+$", name):
        return False, "Tag name may only contain letters, digits, hyphens, and underscores."
    return True, ""


def validate_category_name(name: str) -> Tuple[bool, str]:
    """Validate category name."""
    if not name or len(name.strip()) == 0:
        return False, "Category name must not be empty."
    if len(name) > MAX_CATEGORY_LENGTH:
        return False, f"Category name must not exceed {MAX_CATEGORY_LENGTH} characters."
    if not re.match(r"^[a-zA-Z0-9 _-]+$", name):
        return False, "Category name contains invalid characters."
    return True, ""


# ---------------------------------------------------------------------------
# User management
# ---------------------------------------------------------------------------
def hash_password(password: str) -> str:
    """Hash a plaintext password using bcrypt."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(BCRYPT_ROUNDS)).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a plaintext password against a bcrypt hash."""
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def create_user(username: str, password: str, role: str = "author",
                db_path: str = DEFAULT_DB_PATH) -> Tuple[bool, str]:
    """
    Create a new user with the given credentials.
    Returns (success, message).
    """
    # Validate inputs
    valid, msg = validate_username(username)
    if not valid:
        return False, msg
    valid, msg = validate_password(password)
    if not valid:
        return False, msg
    if role not in ("admin", "author"):
        return False, "Role must be 'admin' or 'author'."

    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        # Check uniqueness
        cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
        if cursor.fetchone() is not None:
            return False, "Username already exists."

        pw_hash = hash_password(password)
        cursor.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            (username, pw_hash, role),
        )
        conn.commit()
        return True, "User created successfully."
    except sqlite3.IntegrityError:
        return False, "Username already exists."
    except Exception as exc:
        return False, f"Database error: {exc}"
    finally:
        conn.close()


def authenticate_user(username: str, password: str,
                      db_path: str = DEFAULT_DB_PATH) -> Optional[str]:
    """
    Authenticate a user and return a session token, or None on failure.
    """
    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, password_hash FROM users WHERE username = ?", (username,))
        row = cursor.fetchone()
        if row is None:
            return None
        if not verify_password(password, row["password_hash"]):
            return None

        # Generate session token
        token = secrets.token_urlsafe(SESSION_TOKEN_BYTES)
        now = datetime.datetime.utcnow().isoformat()
        cursor.execute(
            "INSERT INTO sessions (token, user_id, created_at) VALUES (?, ?, ?)",
            (token, row["id"], now),
        )
        conn.commit()
        return token
    except Exception:
        return None
    finally:
        conn.close()


def get_user_by_token(token: str, db_path: str = DEFAULT_DB_PATH) -> Optional[User]:
    """Retrieve a User object from a valid session token."""
    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT u.id, u.username, u.password_hash, u.role "
            "FROM users u JOIN sessions s ON u.id = s.user_id "
            "WHERE s.token = ?",
            (token,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return User(
            id=row["id"],
            username=row["username"],
            password_hash=row["password_hash"],
            role=row["role"],
        )
    except Exception:
        return None
    finally:
        conn.close()


def logout_user(token: str, db_path: str = DEFAULT_DB_PATH) -> None:
    """Invalidate a session token."""
    conn = get_connection(db_path)
    try:
        conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Category & Tag management
# ---------------------------------------------------------------------------
def create_category(name: str, db_path: str = DEFAULT_DB_PATH) -> Tuple[bool, str]:
    """Create a new category."""
    valid, msg = validate_category_name(name)
    if not valid:
        return False, msg

    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO categories (name) VALUES (?)", (name.strip(),))
        conn.commit()
        return True, "Category created."
    except sqlite3.IntegrityError:
        return False, "Category already exists."
    except Exception as exc:
        return False, f"Database error: {exc}"
    finally:
        conn.close()


def list_categories(db_path: str = DEFAULT_DB_PATH) -> List[Dict[str, Any]]:
    """Return all categories."""
    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name FROM categories ORDER BY name")
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def delete_category(category_id: int, db_path: str = DEFAULT_DB_PATH) -> Tuple[bool, str]:
    """Delete a category by id."""
    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM categories WHERE id = ?", (category_id,))
        if cursor.rowcount == 0:
            return False, "Category not found."
        conn.commit()
        return True, "Category deleted."
    except Exception as exc:
        return False, f"Database error: {exc}"
    finally:
        conn.close()


def create_tag(name: str, db_path: str = DEFAULT_DB_PATH) -> Tuple[bool, str]:
    """Create a new tag."""
    valid, msg = validate_tag_name(name)
    if not valid:
        return False, msg

    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO tags (name) VALUES (?)", (name.strip(),))
        conn.commit()
        return True, "Tag created."
    except sqlite3.IntegrityError:
        return False, "Tag already exists."
    except Exception as exc:
        return False, f"Database error: {exc}"
    finally:
        conn.close()


def list_tags(db_path: str = DEFAULT_DB_PATH) -> List[Dict[str, Any]]:
    """Return all tags."""
    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name FROM tags ORDER BY name")
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def delete_tag(tag_id: int, db_path: str = DEFAULT_DB_PATH) -> Tuple[bool, str]:
    """Delete a tag by id."""
    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM tags WHERE id = ?", (tag_id,))
        if cursor.rowcount == 0:
            return False, "Tag not found."
        conn.commit()
        return True, "Tag deleted."
    except Exception as exc:
        return False, f"Database error: {exc}"
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Post management
# ---------------------------------------------------------------------------
def create_post(title: str, content: str, author_id: int,
                category_ids: Optional[List[int]] = None,
                tag_ids: Optional[List[int]] = None,
                published: bool = False,
                db_path: str = DEFAULT_DB_PATH) -> Tuple[Union[int, bool], str]:
    """
    Create a new blog post.
    Returns (post_id, message) on success, or (False, message) on failure.
    """
    valid, msg = validate_title(title)
    if not valid:
        return False, msg
    valid, msg = validate_content(content)
    if not valid:
        return False, msg

    # Sanitize inputs
    title = sanitize_html(title.strip())
    content = sanitize_html(content.strip())

    now = datetime.datetime.utcnow().isoformat()
    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO posts (title, content, author_id, created_at, updated_at, published) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (title, content, author_id, now, now, 1 if published else 0),
        )
        post_id = cursor.lastrowid

        # Attach categories
        if category_ids:
            for cid in category_ids:
                cursor.execute(
                    "INSERT OR IGNORE INTO post_categories (post_id, category_id) VALUES (?, ?)",
                    (post_id, cid),
                )

        # Attach tags
        if tag_ids:
            for tid in tag_ids:
                cursor.execute(
                    "INSERT OR IGNORE INTO post_tags (post_id, tag_id) VALUES (?, ?)",
                    (post_id, tid),
                )

        conn.commit()
        return post_id, "Post created successfully."
    except sqlite3.IntegrityError as exc:
        return False, f"Integrity error: {exc}"
    except Exception as exc:
        return False, f"Database error: {exc}"
    finally:
        conn.close()


def get_post(post_id: int, db_path: str = DEFAULT_DB_PATH) -> Optional[Dict[str, Any]]:
    """Retrieve a single post with its categories and tags."""
    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT p.id, p.title, p.content, p.author_id, p.created_at, "
            "p.updated_at, p.published, u.username AS author_name "
            "FROM posts p JOIN users u ON p.author_id = u.id "
            "WHERE p.id = ?",
            (post_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None

        post = dict(row)

        # Fetch categories
        cursor.execute(
            "SELECT c.id, c.name FROM categories c "
            "JOIN post_categories pc ON c.id = pc.category_id "
            "WHERE pc.post_id = ?",
            (post_id,),
        )
        post["categories"] = [dict(r) for r in cursor.fetchall()]

        # Fetch tags
        cursor.execute(
            "SELECT t.id, t.name FROM tags t "
            "JOIN post_tags pt ON t.id = pt.tag_id "
            "WHERE pt.post_id = ?",
            (post_id,),
        )
        post["tags"] = [dict(r) for r in cursor.fetchall()]

        return post
    finally:
        conn.close()


def update_post(post_id: int, title: Optional[str] = None, content: Optional[str] = None,
                category_ids: Optional[List[int]] = None,
                tag_ids: Optional[List[int]] = None,
                published: Optional[bool] = None,
                db_path: str = DEFAULT_DB_PATH