import sqlite3
import string
import random
from urllib.parse import urlparse
from flask import Flask, request, jsonify, redirect, abort

app = Flask(__name__)
DATABASE = 'url_shortener.db'

def get_db():
    """Get a database connection to the SQLite database."""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialize the database with the urls table."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS urls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            original_url TEXT NOT NULL,
            short_code TEXT NOT NULL UNIQUE,
            clicks INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def is_valid_url(url: str) -> bool:
    """
    Validate that the given string is a proper URL (http or https scheme).

    Args:
        url: The URL string to validate.

    Returns:
        True if the URL has a valid scheme and netloc, otherwise False.
    """
    if not url or not isinstance(url, str):
        return False
    parsed = urlparse(url)
    return parsed.scheme in ('http', 'https') and bool(parsed.netloc)

def generate_short_code(length: int = 6) -> str:
    """
    Generate a random alphanumeric short code of the given length.

    Args:
        length: Length of the short code (default 6).

    Returns:
        A random string of uppercase/lowercase letters and digits.
    """
    chars = string.ascii_letters + string.digits
    return ''.join(random.choices(chars, k=length))

def insert_url(original_url: str) -> str:
    """
    Insert a new URL into the database and return its short code.
    If the URL already exists, return the existing short code.

    Args:
        original_url: The original long URL.

    Returns:
        The short code associated with the URL.
    """
    conn = get_db()
    cursor = conn.cursor()
    # Check if URL already exists
    cursor.execute('SELECT short_code FROM urls WHERE original_url = ?', (original_url,))
    row = cursor.fetchone()
    if row:
        conn.close()
        return row['short_code']
    # Generate a unique short code
    while True:
        short_code = generate_short_code()
        cursor.execute('SELECT id FROM urls WHERE short_code = ?', (short_code,))
        if not cursor.fetchone():
            break
    cursor.execute(
        'INSERT INTO urls (original_url, short_code) VALUES (?, ?)',
        (original_url, short_code)
    )
    conn.commit()
    conn.close()
    return short_code

def get_url_by_code(short_code: str) -> sqlite3.Row | None:
    """
    Retrieve the URL record for a given short code.

    Args:
        short_code: The short code to look up.

    Returns:
        A sqlite3.Row object with keys id, original_url, short_code, clicks,
        or None if not found.
    """
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM urls WHERE short_code = ?', (short_code,))
    row = cursor.fetchone()
    conn.close()
    return row

def increment_clicks(short_code: str) -> None:
    """Increment the click count for the given short code."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        'UPDATE urls SET clicks = clicks + 1 WHERE short_code = ?',
        (short_code,)
    )
    conn.commit()
    conn.close()

@app.route('/encode', methods=['POST'])
def encode_url():
    """
    Encode a long URL to a short code.

    Expects JSON: {"url": "https://example.com/very/long/url"}
    Returns JSON: {"short_url": "http://short.est/abc123", "original_url": "..."}
    """
    data = request.get_json(silent=True)
    if not data or 'url' not in data:
        abort(400, description="Missing 'url' in request body")
    original_url = data['url'].strip()
    if not is_valid_url(original_url):
        abort(400, description="Invalid URL: must start with http:// or https://")
    try:
        short_code = insert_url(original_url)
    except Exception as e:
        abort(500, description=f"Database error: {str(e)}")
    short_url = request.host_url + short_code
    return jsonify({'short_url': short_url, 'original_url': original_url}), 201

@app.route('/decode', methods=['POST'])
def decode_url():
    """
    Decode a short code to its original URL.

    Expects JSON: {"short_code": "abc123"} or {"short_url": "http://short.est/abc123"}
    Returns JSON: {"original_url": "..."} or error 404 if not found.
    """
    data = request.get_json(silent=True)
    if not data:
        abort(400, description="Request body missing")
    # Accept either 'short_code' or 'short_url'
    short_code = data.get('short_code', '') or data.get('short_url', '')
    if not short_code:
        abort(400, description="Missing 'short_code' or 'short_url' in request body")
    # Extract code from URL if full URL was given
    if '/' in short_code:
        short_code = short_code.rstrip('/').rsplit('/', 1)[-1]
    # Validate short_code format (alphanumeric)
    if not short_code.isalnum():
        abort(400, description="Invalid short code format")
    row = get_url_by_code(short_code)
    if not row:
        abort(404, description="Short code not found")
    return jsonify({'original_url': row['original_url']})

@app.route('/<short_code>')
def redirect_to_url(short_code: str):
    """
    Redirect a short code to its original URL and track the click.

    Args:
        short_code: The short code from the URL path.

    Returns:
        A 302 redirect to the original URL.
    """
    if not short_code.isalnum():
        abort(400, description="Invalid short code format")
    row = get_url_by_code(short_code)
    if not row:
        abort(404, description="Short code not found")
    increment_clicks(short_code)
    return redirect(row['original_url'], code=302)

@app.route('/stats/<short_code>')
def get_stats(short_code: str):
    """
    Retrieve analytics for a given short code.

    Args:
        short_code: The short code to get stats for.

    Returns:
        JSON with short_code, original_url, clicks.
    """
    if not short_code.isalnum():
        abort(400, description="Invalid short code format")
    row = get_url_by_code(short_code)
    if not row:
        abort(404, description="Short code not found")
    return jsonify({
        'short_code': row['short_code'],
        'original_url': row['original_url'],
        'clicks': row['clicks']
    })

# Initialize the database when the app starts
with app.app_context():
    init_db()

if __name__ == '__main__':
    app.run(debug=False)