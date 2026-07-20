import sqlite3
import string
import random
from flask import Flask, request, redirect, jsonify, abort
from urllib.parse import urlparse, urlunparse
from typing import Optional, Tuple

app = Flask(__name__)

# Database setup
DATABASE = 'shortener.db'

def get_db() -> sqlite3.Connection:
    """Get a database connection."""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db() -> None:
    """Initialize the database and create tables if not exists."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS urls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            original_url TEXT NOT NULL,
            short_code TEXT UNIQUE NOT NULL,
            click_count INTEGER DEFAULT 0
        )
    ''')
    conn.commit()
    conn.close()

# Base62 encoding
BASE62_ALPHABET = string.digits + string.ascii_lowercase + string.ascii_uppercase

def encode_base62(num: int) -> str:
    """Convert a positive integer to a base62 string."""
    if num == 0:
        return BASE62_ALPHABET[0]
    chars = []
    while num > 0:
        remainder = num % 62
        chars.append(BASE62_ALPHABET[remainder])
        num //= 62
    return ''.join(reversed(chars))

def is_valid_url(url: str) -> bool:
    """
    Validate URL format and return True if valid.
    Only allows http and https schemes.
    """
    try:
        parsed = urlparse(url)
        return all((parsed.scheme in ('http', 'https'), parsed.netloc))
    except Exception:
        return False

@app.route('/shorten', methods=['POST'])
def shorten_url() -> Tuple[dict, int]:
    """
    Encode a long URL into a short code.
    Expects JSON with 'url' key.
    Returns JSON with original_url, short_code, and short_url.
    """
    data = request.get_json(silent=True)
    if not data or 'url' not in data:
        abort(400, description="Missing 'url' in request body")
    
    original_url = data['url'].strip()
    if not is_valid_url(original_url):
        abort(400, description="Invalid URL: must be absolute http/https URL")

    conn = get_db()
    cursor = conn.cursor()
    
    # Check if URL already exists
    cursor.execute('SELECT short_code FROM urls WHERE original_url = ?', (original_url,))
    existing = cursor.fetchone()
    if existing:
        short_code = existing['short_code']
    else:
        # Insert new URL and get ID
        cursor.execute('INSERT INTO urls (original_url, short_code) VALUES (?, ?)',
                       (original_url, ''))  # Placeholder
        conn.commit()
        url_id = cursor.lastrowid
        short_code = encode_base62(url_id)
        # Update with actual short code
        cursor.execute('UPDATE urls SET short_code = ? WHERE id = ?', (short_code, url_id))
        conn.commit()
    
    conn.close()
    
    short_url = f"{request.host_url}{short_code}"
    return jsonify({
        'original_url': original_url,
        'short_code': short_code,
        'short_url': short_url
    }), 201

@app.route('/<short_code>', methods=['GET'])
def redirect_to_original(short_code: str) -> redirect:
    """
    Redirect to the original URL associated with the short code.
    Increments click count for analytics.
    """
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT original_url FROM urls WHERE short_code = ?', (short_code,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        abort(404, description="Short code not found")
    
    original_url = row['original_url']
    
    # Update click count
    cursor.execute('UPDATE urls SET click_count = click_count + 1 WHERE short_code = ?', (short_code,))
    conn.commit()
    conn.close()
    
    return redirect(original_url, code=302)

@app.route('/analytics/<short_code>', methods=['GET'])
def get_analytics(short_code: str) -> Tuple[dict, int]:
    """
    Get analytics for a specific short code.
    Returns JSON with short_code, original_url, and click_count.
    """
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT original_url, click_count FROM urls WHERE short_code = ?', (short_code,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        abort(404, description="Short code not found")
    
    return jsonify({
        'short_code': short_code,
        'original_url': row['original_url'],
        'click_count': row['click_count']
    }), 200

# Error handlers
@app.errorhandler(400)
def bad_request(error):
    return jsonify({'error': str(error.description)}), 400

@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': str(error.description)}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Internal server error'}), 500

# Main entry point
if __name__ == '__main__':
    init_db()
    app.run(debug=True)  # Disable debug in production