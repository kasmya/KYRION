"""
Blog CMS Module

A self-contained blog content management system with:
- User authentication (register, login, logout, session management)
- Post CRUD operations with categories and tags
- Comment system
- Security best practices (password hashing, CSRF protection, SQL injection prevention)

Dependencies:
- Flask (web framework)
- Flask-Login (user session management)
- Flask-WTF (form handling and CSRF protection)
- bcrypt (password hashing)
- SQLite3 (database, standard library)

All database operations use parameterized queries to prevent SQL injection.
Passwords are hashed using bcrypt.
CSRF protection is enabled for all forms.
"""

import os
import sqlite3
import secrets
from datetime import datetime
from functools import wraps
from typing import Optional, List, Tuple, Dict, Any, Union

from flask import (
    Flask, render_template_string, request, redirect, url_for,
    flash, session, g, abort
)
from flask_login import (
    LoginManager, UserMixin, login_user, logout_user,
    login_required, current_user
)
from flask_wtf.csrf import CSRFProtect
from wtforms import StringField, PasswordField, TextAreaField, SelectMultipleField
from wtforms.validators import DataRequired, Length, Email, EqualTo, ValidationError
from wtforms import Form
import bcrypt

# Configuration
DATABASE = 'blog.db'
SECRET_KEY = os.environ.get('SECRET_KEY', secrets.token_hex(32))
BCRYPT_ROUNDS = 12

app = Flask(__name__)
app.config.update(
    SECRET_KEY=SECRET_KEY,
    WTF_CSRF_SECRET_KEY=secrets.token_hex(32),
    DATABASE=DATABASE
)

csrf = CSRFProtect(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message_category = 'info'

# =============================================================================
# Database Helpers
# =============================================================================

def get_db() -> sqlite3.Connection:
    """Get database connection for current request."""
    if 'db' not in g:
        g.db = sqlite3.connect(
            app.config['DATABASE'],
            detect_types=sqlite3.PARSE_DECLTYPES
        )
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(error: Optional[BaseException]) -> None:
    """Close database connection at end of request."""
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_db() -> None:
    """Initialize database schema."""
    db = get_db()
    with app.open_resource('schema.sql', mode='r') as f:
        db.cursor().executescript(f.read())
    db.commit()

def query_db(query: str, args: Tuple = (), one: bool = False) -> Union[List[sqlite3.Row], sqlite3.Row, None]:
    """Execute parameterized query and return results."""
    cur = get_db().execute(query, args)
    rv = cur.fetchall()
    cur.close()
    return (rv[0] if rv else None) if one else rv

def execute_db(query: str, args: Tuple = ()) -> int:
    """Execute parameterized write query and return last row ID."""
    db = get_db()
    cur = db.execute(query, args)
    db.commit()
    last_id = cur.lastrowid
    cur.close()
    return last_id

# =============================================================================
# Data Models
# =============================================================================

class User(UserMixin):
    """User model with authentication."""
    def __init__(self, id: int, username: str, email: str, password_hash: str, created_at: datetime):
        self.id = id
        self.username = username
        self.email = email
        self.password_hash = password_hash
        self.created_at = created_at

    @staticmethod
    def get_by_id(user_id: int) -> Optional['User']:
        """Retrieve user by ID."""
        row = query_db('SELECT * FROM users WHERE id = ?', (user_id,), one=True)
        if row:
            return User(row['id'], row['username'], row['email'], row['password_hash'], row['created_at'])
        return None

    @staticmethod
    def get_by_username(username: str) -> Optional['User']:
        """Retrieve user by username."""
        row = query_db('SELECT * FROM users WHERE username = ?', (username,), one=True)
        if row:
            return User(row['id'], row['username'], row['email'], row['password_hash'], row['created_at'])
        return None

    @staticmethod
    def get_by_email(email: str) -> Optional['User']:
        """Retrieve user by email."""
        row = query_db('SELECT * FROM users WHERE email = ?', (email,), one=True)
        if row:
            return User(row['id'], row['username'], row['email'], row['password_hash'], row['created_at'])
        return None

    @staticmethod
    def create(username: str, email: str, password: str) -> 'User':
        """Create new user with hashed password."""
        password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt(BCRYPT_ROUNDS))
        user_id = execute_db(
            'INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)',
            (username, email, password_hash.decode('utf-8'))
        )
        return User.get_by_id(user_id)

    def check_password(self, password: str) -> bool:
        """Verify password against hash."""
        return bcrypt.checkpw(password.encode('utf-8'), self.password_hash.encode('utf-8'))

class Post:
    """Blog post model."""
    def __init__(self, id: int, title: str, content: str, author_id: int,
                 created_at: datetime, updated_at: datetime, published: bool):
        self.id = id
        self.title = title
        self.content = content
        self.author_id = author_id
        self.created_at = created_at
        self.updated_at = updated_at
        self.published = published

    @staticmethod
    def get_by_id(post_id: int) -> Optional['Post']:
        """Retrieve post by ID."""
        row = query_db('SELECT * FROM posts WHERE id = ?', (post_id,), one=True)
        if row:
            return Post(
                row['id'], row['title'], row['content'], row['author_id'],
                row['created_at'], row['updated_at'], bool(row['published'])
            )
        return None

    @staticmethod
    def get_all(published_only: bool = True, category: Optional[str] = None,
                tag: Optional[str] = None, limit: int = 10, offset: int = 0) -> List['Post']:
        """Retrieve posts with optional filtering."""
        query = 'SELECT * FROM posts'
        conditions = []
        args = []

        if published_only:
            conditions.append('published = 1')
        if category:
            conditions.append('''EXISTS (
                SELECT 1 FROM post_categories pc
                JOIN categories c ON pc.category_id = c.id
                WHERE pc.post_id = posts.id AND c.name = ?
            )''')
            args.append(category)
        if tag:
            conditions.append('''EXISTS (
                SELECT 1 FROM post_tags pt
                JOIN tags t ON pt.tag_id = t.id
                WHERE pt.post_id = posts.id AND t.name = ?
            )''')
            args.append(tag)

        if conditions:
            query += ' WHERE ' + ' AND '.join(conditions)
        query += ' ORDER BY created_at DESC LIMIT ? OFFSET ?'
        args.extend([limit, offset])

        rows = query_db(query, tuple(args))
        return [
            Post(r['id'], r['title'], r['content'], r['author_id'],
                 r['created_at'], r['updated_at'], bool(r['published']))
            for r in rows
        ]

    @staticmethod
    def create(title: str, content: str, author_id: int, published: bool = False) -> 'Post':
        """Create new post."""
        now = datetime.utcnow()
        post_id = execute_db(
            '''INSERT INTO posts (title, content, author_id, created_at, updated_at, published)
               VALUES (?, ?, ?, ?, ?, ?)''',
            (title, content, author_id, now, now, published)
        )
        return Post.get_by_id(post_id)

    def update(self, title: str, content: str, published: bool) -> None:
        """Update post content."""
        now = datetime.utcnow()
        execute_db(
            '''UPDATE posts SET title = ?, content = ?, published = ?, updated_at = ?
               WHERE id = ?''',
            (title, content, published, now, self.id)
        )
        self.title = title
        self.content = content
        self.published = published
        self.updated_at = now

    def delete(self) -> None:
        """Delete post and associated relationships."""
        execute_db('DELETE FROM post_categories WHERE post_id = ?', (self.id,))
        execute_db('DELETE FROM post_tags WHERE post_id = ?', (self.id,))
        execute_db('DELETE FROM comments WHERE post_id = ?', (self.id,))
        execute_db('DELETE FROM posts WHERE id = ?', (self.id,))

    def get_categories(self) -> List[str]:
        """Get category names for this post."""
        rows = query_db('''
            SELECT c.name FROM categories c
            JOIN post_categories pc ON c.id = pc.category_id
            WHERE pc.post_id = ?
        ''', (self.id,))
        return [r['name'] for r in rows]

    def get_tags(self) -> List[str]:
        """Get tag names for this post."""
        rows = query_db('''
            SELECT t.name FROM tags t
            JOIN post_tags pt ON t.id = pt.tag_id
            WHERE pt.post_id = ?
        ''', (self.id,))
        return [r['name'] for r in rows]

    def set_categories(self, category_names: List[str]) -> None:
        """Set categories for this post."""
        execute_db('DELETE FROM post_categories WHERE post_id = ?', (self.id,))
        for name in category_names:
            cat = Category.get_or_create(name)
            execute_db(
                'INSERT INTO post_categories (post_id, category_id) VALUES (?, ?)',
                (self.id, cat.id)
            )

    def set_tags(self, tag_names: List[str]) -> None:
        """Set tags for this post."""
        execute_db('DELETE FROM post_tags WHERE post_id = ?', (self.id,))
        for name in tag_names:
            tag = Tag.get_or_create(name)
            execute_db(
                'INSERT INTO post_tags (post_id, tag_id) VALUES (?, ?)',
                (self.id, tag.id)
            )

class Category:
    """Post category model."""
    def __init__(self, id: int, name: str):
        self.id = id
        self.name = name

    @staticmethod
    def get_by_id(cat_id: int) -> Optional['Category']:
        row = query_db('SELECT * FROM categories WHERE id = ?', (cat_id,), one=True)
        return Category(row['id'], row['name']) if row else None

    @staticmethod
    def get_by_name(name: str) -> Optional['Category']:
        row = query_db('SELECT * FROM categories WHERE name = ?', (name,), one=True)
        return Category(row['id'], row['name']) if row else None

    @staticmethod
    def get_all() -> List['Category']:
        rows = query_db('SELECT * FROM categories ORDER BY name')
        return [Category(r['id'], r['name']) for r in rows]

    @staticmethod
    def get_or_create(name: str) -> 'Category':
        cat = Category.get_by_name(name)
        if cat:
            return cat
        cat_id = execute_db('INSERT INTO categories (name) VALUES (?)', (name,))
        return Category.get_by_id(cat_id)

class Tag:
    """Post tag model."""
    def __init__(self, id: int, name: str):
        self.id = id
        self.name = name

    @staticmethod
    def get_by_id(tag_id: int) -> Optional['Tag']:
        row = query_db('SELECT * FROM tags WHERE id = ?', (tag_id,), one=True)
        return Tag(row['id'], row['name']) if row else None

    @staticmethod
    def get_by_name(name: str) -> Optional['Tag']:
        row = query_db('SELECT * FROM tags WHERE name = ?', (name,), one=True)
        return Tag(row['id'], row['name']) if row else None

    @staticmethod
    def get_all() -> List['Tag']:
        rows = query_db('SELECT * FROM tags ORDER BY name')
        return [Tag(r['id'], r['name']) for r in rows]

    @staticmethod
    def get_or_create(name: str) -> 'Tag':
        tag = Tag.get_by_name(name)
        if tag:
            return tag
        tag_id = execute_db('INSERT INTO tags (name) VALUES (?)', (name,))
        return Tag.get_by_id(tag_id)

class Comment:
    """Post comment model."""
    def __init__(self, id: int, post_id: int, author_id: int, content: str, created_at: datetime):
        self.id = id
        self.post_id = post_id
        self.author_id = author_id
        self.content = content
        self.created_at = created_at

    @staticmethod
    def get_by_id(comment_id: int) -> Optional['Comment']:
        row = query_db('SELECT * FROM comments WHERE id = ?', (comment_id,), one=True)
        if row:
            return Comment(row['id'], row['post_id'], row['author_id'], row['content'], row['created_at'])
        return None

    @staticmethod
    def get_for_post(post_id: int) -> List['Comment']:
        rows = query_db(
            'SELECT * FROM comments WHERE post_id = ? ORDER BY created_at ASC',
            (post_id,)
        )
        return [Comment(r['id'], r['post_id'], r['author_id'], r['content'], r['created_at']) for r in rows]

    @staticmethod
    def create(post_id: int, author_id: int, content: str) -> 'Comment':
        now = datetime.utcnow()
        comment_id = execute_db(
            'INSERT INTO comments (post_id, author_id, content, created_at) VALUES (?, ?, ?, ?)',
            (post_id, author_id, content, now)
        )
        return Comment.get_by_id(comment_id)

    def delete(self) -> None:
        execute_db('DELETE FROM comments WHERE id = ?', (self.id,))

# =============================================================================
# Forms
# =============================================================================

class RegisterForm(Form):
    """User registration form."""
    username = StringField('Username', validators=[
        DataRequired(), Length(min=3, max=50)
    ])
    email = StringField('Email', validators=[
        DataRequired(), Email(), Length(max=100)
    ])
    password = PasswordField('Password', validators=[
        DataRequired(), Length(min=8)
    ])
    confirm = PasswordField('Confirm Password', validators=[
        DataRequired(), EqualTo('password')
    ])

    def validate_username(self, field: StringField) -> None:
        if User.get_by_username(field.data):
            raise ValidationError('Username already taken.')

    def validate_email(self, field: StringField) -> None:
        if User.get_by_email(field.data):
            raise ValidationError('Email already registered.')

class LoginForm(Form):
    """User login form."""
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])

class PostForm(Form):
    """Post creation/edit form."""
    title = StringField('Title', validators=[DataRequired(), Length(max=200)])
    content = TextAreaField('Content', validators=[DataRequired()])
    categories = StringField('Categories (comma separated)')
    tags = StringField('Tags (comma separated)')
    published = StringField('Published')  # Handled as checkbox in template

class CommentForm(Form):
    """Comment form."""
    content = TextAreaField('Comment', validators=[DataRequired(), Length(max=2000)])

# =============================================================================
# Authentication Helpers
# =============================================================================

@login_manager.user_loader
def load_user(user_id: str) -> Optional[User]:
    """Load user for Flask-Login."""
    return User.get_by_id(int(user_id))

def admin_required(f):
    """Decorator to require admin user (first registered user)."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return login_manager.unauthorized()
        # First user (id=1) is admin
        if current_user.id != 1:
            abort(403)
        return f(*args, **kwargs)
    return decorated_function

# =============================================================================