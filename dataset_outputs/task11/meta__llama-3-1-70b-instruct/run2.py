from flask import Flask, request, redirect, abort
from hashlib import sha256
from base64 import b64encode, b64decode
from sqlite3 import connect
from urllib.parse import urlparse
from typing import Optional

app = Flask(__name__)

# Create a database connection
conn = connect('url_shortener.db')
cursor = conn.cursor()

# Create tables if not exist
cursor.execute('''
    CREATE TABLE IF NOT EXISTS urls (
        short_code TEXT PRIMARY KEY,
        long_url TEXT NOT NULL,
        click_count INTEGER NOT NULL DEFAULT 0
    );
''')
conn.commit()

def is_valid_url(long_url: str) -> bool:
    """Check if a URL is valid."""
    try:
        result = urlparse(long_url)
        return all([result.scheme, result.netloc])
    except ValueError:
        return False

def encode_url(long_url: str) -> str:
    """Encode a long URL to a short code."""
    if not is_valid_url(long_url):
        raise ValueError("Invalid URL")

    # Use the first 6 characters of the SHA-256 hash of the URL as the short code
    short_code = b64encode(sha256(long_url.encode()).digest()[:6]).decode()
    return short_code

def decode_url(short_code: str) -> Optional[str]:
    """Decode a short code to a long URL."""
    cursor.execute('SELECT long_url FROM urls WHERE short_code = ?', (short_code,))
    row = cursor.fetchone()
    if row:
        return row[0]
    else:
        return None

def track_click(short_code: str) -> None:
    """Track a click on a short URL."""
    cursor.execute('UPDATE urls SET click_count = click_count + 1 WHERE short_code = ?', (short_code,))
    conn.commit()

@app.route('/shorten', methods=['POST'])
def shorten_url() -> str:
    """Shorten a long URL."""
    long_url = request.json['long_url']
    short_code = encode_url(long_url)
    cursor.execute('INSERT INTO urls (short_code, long_url) VALUES (?, ?)', (short_code, long_url))
    conn.commit()
    return {'short_code': short_code}

@app.route('/<short_code>', methods=['GET'])
def redirect_url(short_code: str) -> str:
    """Redirect a short URL to the original URL."""
    long_url = decode_url(short_code)
    if long_url:
        track_click(short_code)
        return redirect(long_url)
    else:
        abort(404)

@app.route('/stats/<short_code>', methods=['GET'])
def get_stats(short_code: str) -> str:
    """Get the click count of a short URL."""
    cursor.execute('SELECT click_count FROM urls WHERE short_code = ?', (short_code,))
    row = cursor.fetchone()
    if row:
        return {'click_count': row[0]}
    else:
        abort(404)

if __name__ == '__main__':
    app.run(debug=True)