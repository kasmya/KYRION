import sqlite3
import re
from datetime import datetime
from functools import wraps
from typing import Optional, Tuple, Union
from werkzeug.security import generate_password_hash, check_password_hash
from flask import Flask, render_template, request, redirect, url_for, flash, session, g, jsonify

app = Flask(__name__)
app.secret_key = 'change-this-to-a-secure-random-key'  # In production, use environment variable

DATABASE = 'forum.db'

def get_db() -> sqlite3.Connection:
    """Get or create a database connection for the current request."""
    if 'db' not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db

@app.teardown_appcontext
def close_db(error: Optional[Exception]) -> None:
    """Close database connection after request."""
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_db() -> None:
    """Initialize the database schema."""
    with app.app_context():
        db = get_db()
        db.executescript('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                author_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (author_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS comments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                post_id INTEGER NOT NULL,
                author_id INTEGER NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE,
                FOREIGN KEY (author_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS votes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                post_id INTEGER NOT NULL,
                value INTEGER NOT NULL CHECK(value IN (-1, 1)),
                UNIQUE(user_id, post_id),
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE
            );
        ''')
        db.commit()

def login_required(f):
    """Decorator to require login for a route."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def get_current_user() -> Optional[sqlite3.Row]:
    """Return the current logged-in user row or None."""
    if 'user_id' in session:
        db = get_db()
        return db.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    return None

def csrf_token() -> str:
    """Generate and store a CSRF token in session."""
    import secrets
    if 'csrf_token' not in session:
        session['csrf_token'] = secrets.token_hex(16)
    return session['csrf_token']

def validate_csrf(token: str) -> bool:
    """Validate CSRF token from form."""
    return token == session.get('csrf_token', '')

def get_post_score(post_id: int) -> int:
    """Calculate the net score (upvotes - downvotes) for a post."""
    db = get_db()
    up = db.execute('SELECT COUNT(*) FROM votes WHERE post_id = ? AND value = 1', (post_id,)).fetchone()[0]
    down = db.execute('SELECT COUNT(*) FROM votes WHERE post_id = ? AND value = -1', (post_id,)).fetchone()[0]
    return up - down

def get_user_vote(user_id: int, post_id: int) -> Optional[int]:
    """Get the user's vote value for a post, if any."""
    db = get_db()
    row = db.execute('SELECT value FROM votes WHERE user_id = ? AND post_id = ?', (user_id, post_id)).fetchone()
    return row[0] if row else None

# ========== Routes ==========

@app.route('/')
def index() -> str:
    """Display all posts sorted by newest first, with search support."""
    db = get_db()
    search_query = request.args.get('q', '').strip()
    if search_query:
        # Simple search: match title or content (case-insensitive)
        liked_search = f"%{search_query}%"
        posts = db.execute(
            '''SELECT posts.*, users.username 
               FROM posts JOIN users ON posts.author_id = users.id 
               WHERE posts.title LIKE ? OR posts.content LIKE ?
               ORDER BY posts.created_at DESC''',
            (liked_search, liked_search)
        ).fetchall()
    else:
        posts = db.execute(
            '''SELECT posts.*, users.username 
               FROM posts JOIN users ON posts.author_id = users.id 
               ORDER BY posts.created_at DESC'''
        ).fetchall()

    user = get_current_user()
    return render_template('index.html', posts=posts, user=user, search_query=search_query)

@app.route('/register', methods=['GET', 'POST'])
def register() -> Union[str, redirect]:
    """Register a new user."""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        confirm = request.form.get('confirm', '')

        if not username or not email or not password:
            flash('All fields are required.', 'error')
            return render_template('register.html')

        if password != confirm:
            flash('Passwords do not match.', 'error')
            return render_template('register.html')

        if len(username) < 3 or len(password) < 6:
            flash('Username must be at least 3 characters and password at least 6 characters.', 'error')
            return render_template('register.html')

        # Check unique username and email
        db = get_db()
        existing = db.execute('SELECT id FROM users WHERE username = ? OR email = ?', (username, email)).fetchone()
        if existing:
            flash('Username or email already taken.', 'error')
            return render_template('register.html')

        password_hash = generate_password_hash(password)
        try:
            db.execute('INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)',
                       (username, email, password_hash))
            db.commit()
            flash('Registration successful! Please log in.', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            flash('An error occurred. Please try again.', 'error')
            return render_template('register.html')

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login() -> Union[str, redirect]:
    """Log in an existing user."""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        if not username or not password:
            flash('Please fill in all fields.', 'error')
            return render_template('login.html')

        db = get_db()
        user = db.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        if user is None or not check_password_hash(user['password_hash'], password):
            flash('Invalid username or password.', 'error')
            return render_template('login.html')

        session['user_id'] = user['id']
        session['username'] = user['username']
        flash('Logged in successfully.', 'success')
        return redirect(url_for('index'))

    return render_template('login.html')

@app.route('/logout')
def logout() -> redirect:
    """Log out the current user."""
    session.clear()
    flash('You have been logged out.', 'success')
    return redirect(url_for('index'))

@app.route('/create', methods=['GET', 'POST'])
@login_required
def create_post() -> Union[str, redirect]:
    """Create a new post."""
    if request.method == 'POST':
        # CSRF protection
        if not validate_csrf(request.form.get('csrf_token', '')):
            flash('Invalid CSRF token.', 'error')
            return redirect(url_for('index'))

        title = request.form.get('title', '').strip()
        content = request.form.get('content', '').strip()
        if not title or not content:
            flash('Title and content are required.', 'error')
            return render_template('create.html', csrf_token=csrf_token())

        db = get_db()
        try:
            db.execute('INSERT INTO posts (author_id, title, content) VALUES (?, ?, ?)',
                       (session['user_id'], title, content))
            db.commit()
            flash('Post created successfully!', 'success')
            return redirect(url_for('index'))
        except Exception as e:
            flash('Failed to create post. Please try again.', 'error')
            return render_template('create.html', csrf_token=csrf_token())

    return render_template('create.html', csrf_token=csrf_token())

@app.route('/edit/<int:post_id>', methods=['GET', 'POST'])
@login_required
def edit_post(post_id: int) -> Union[str, redirect]:
    """Edit an existing post (only by author)."""
    db = get_db()
    post = db.execute('SELECT * FROM posts WHERE id = ?', (post_id,)).fetchone()
    if not post:
        flash('Post not found.', 'error')
        return redirect(url_for('index'))

    if post['author_id'] != session['user_id']:
        flash('You are not authorized to edit this post.', 'error')
        return redirect(url_for('index'))

    if request.method == 'POST':
        if not validate_csrf(request.form.get('csrf_token', '')):
            flash('Invalid CSRF token.', 'error')
            return redirect(url_for('index'))

        title = request.form.get('title', '').strip()
        content = request.form.get('content', '').strip()
        if not title or not content:
            flash('Title and content are required.', 'error')
            return render_template('edit.html', post=post, csrf_token=csrf_token())

        try:
            db.execute('UPDATE posts SET title = ?, content = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?',
                       (title, content, post_id))
            db.commit()
            flash('Post updated!', 'success')
            return redirect(url_for('view_post', post_id=post_id))
        except Exception:
            flash('Failed to update post.', 'error')
            return render_template('edit.html', post=post, csrf_token=csrf_token())

    return render_template('edit.html', post=post, csrf_token=csrf_token())

@app.route('/delete/<int:post_id>', methods=['POST'])
@login_required
def delete_post(post_id: int) -> redirect:
    """Delete a post (only by author)."""
    if not validate_csrf(request.form.get('csrf_token', '')):
        flash('Invalid CSRF token.', 'error')
        return redirect(url_for('index'))

    db = get_db()
    post = db.execute('SELECT * FROM posts WHERE id = ?', (post_id,)).fetchone()
    if not post:
        flash('Post not found.', 'error')
        return redirect(url_for('index'))

    if post['author_id'] != session['user_id']:
        flash('You are not authorized to delete this post.', 'error')
        return redirect(url_for('index'))

    try:
        db.execute('DELETE FROM posts WHERE id = ?', (post_id,))
        db.commit()
        flash('Post deleted.', 'success')
    except Exception:
        flash('Failed to delete post.', 'error')
    return redirect(url_for('index'))

@app.route('/post/<int:post_id>', methods=['GET', 'POST'])
def view_post(post_id: int) -> Union[str, redirect]:
    """View a single post with its comments and voting information."""
    db = get_db()
    post = db.execute(
        '''SELECT posts.*, users.username 
           FROM posts JOIN users ON posts.author_id = users.id 
           WHERE posts.id = ?''', (post_id,)
    ).fetchone()
    if not post:
        flash('Post not found.', 'error')
        return redirect(url_for('index'))

    comments = db.execute(
        '''SELECT comments.*, users.username 
           FROM comments JOIN users ON comments.author_id = users.id 
           WHERE comments.post_id = ? 
           ORDER BY comments.created_at ASC''', (post_id,)
    ).fetchall()

    user = get_current_user()
    vote = None
    score = get_post_score(post_id)
    if user:
        vote = get_user_vote(user['id'], post_id)

    if request.method == 'POST':
        # Handle comment submission
        if not user:
            flash('Please log in to comment.', 'error')
            return redirect(url_for('login'))

        if not validate_csrf(request.form.get('csrf_token', '')):
            flash('Invalid CSRF token.', 'error')
            return redirect(url_for('view_post', post_id=post_id))

        content = request.form.get('content', '').strip()
        if not content:
            flash('Comment cannot be empty.', 'error')
            return redirect(url_for('view_post', post_id=post_id))

        try:
            db.execute('INSERT INTO comments (post_id, author_id, content) VALUES (?, ?, ?)',
                       (post_id, user['id'], content))
            db.commit()
            flash('Comment added!', 'success')
        except Exception:
            flash('Failed to add comment.', 'error')

        return redirect(url_for('view_post', post_id=post_id))

    return render_template('post.html', post=post, comments=comments, user=user, vote=vote, score=score, csrf_token=csrf_token())

@app.route('/vote/<int:post_id>/<action>', methods=['POST'])
@login_required
def vote(post_id: int, action: str) -> Union[str, redirect]:
    """Upvote (action='up') or downvote (action='down') a post."""
    if action not in ('up', 'down'):
        flash('Invalid vote action.', 'error')
        return redirect(request.referrer or url_for('index'))

    if not validate_csrf(request.form.get('csrf_token', '')):
        flash('Invalid CSRF token.', 'error')
        return redirect(request.referrer or url_for('index'))

    value = 1 if action == 'up' else -1
    user_id = session['user_id']
    db = get_db()

    # Check if post exists
    post = db.execute('SELECT id FROM posts WHERE id = ?', (post_id,)).fetchone()
    if not post:
        flash('Post not found.', 'error')
        return redirect(url_for('index'))

    # Cannot vote on own post (optional)
    # if post['author_id'] == user_id:
    #     flash('You cannot vote on your own post.', 'error')
    #     return redirect(url_for('view_post', post_id=post_id))

    try:
        # Insert or replace vote (unique constraint ensures one vote per user per post)
        db.execute(
            '''INSERT INTO votes (user_id, post_id, value) VALUES (?, ?, ?)
               ON CONFLICT(user_id, post_id) DO UPDATE SET value = excluded.value''',
            (user_id, post_id, value)
        )
        db.commit()
        flash('Vote recorded!', 'success')
    except Exception:
        flash('Failed to process vote.', 'error')

    return redirect(request.referrer or url_for('view_post', post_id=post_id))

@app.route('/search')
def search() -> Union[str, redirect]:
    """Redirect to index with search query parameter."""
    q = request.args.get('q', '').strip()
    if not q:
        return redirect(url_for('index'))
    return redirect(url_for('index', q=q))

# ========== Run ==========

if __name__ == '__main__':
    init_db()
    app.run(debug=True)  # disable debug in production