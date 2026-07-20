from flask import Flask, request, redirect, url_for
from urllib.parse import urlparse
import hashlib
import sqlite3
from typing import Dict

app = Flask(__name__)

# Database setup
conn = sqlite3.connect('url_shortener.db')
c = conn.cursor()

# Create table if not exists
c.execute('''CREATE TABLE IF NOT EXISTS urls
             (short_code text PRIMARY KEY, original_url text, click_count integer)''')
conn.commit()
conn.close()

def is_valid_url(url: str) -> bool:
    """
    Checks if the provided URL is valid.
    
    Args:
    url (str): The URL to be validated.
    
    Returns:
    bool: True if the URL is valid, False otherwise.
    """
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except ValueError:
        return False

def encode_url(original_url: str) -> str:
    """
    Encodes a long URL to a short code.
    
    Args:
    original_url (str): The original URL to be encoded.
    
    Returns:
    str: The short code for the original URL.
    """
    if not is_valid_url(original_url):
        raise ValueError("Invalid URL")
    
    # Hash the original URL to generate a unique short code
    short_code = hashlib.sha256(original_url.encode()).hexdigest()[:6]
    
    # Check if the short code already exists in the database
    conn = sqlite3.connect('url_shortener.db')
    c = conn.cursor()
    c.execute("SELECT * FROM urls WHERE short_code=?", (short_code,))
    if c.fetchone():
        # If the short code already exists, generate a new one
        short_code = hashlib.sha256((original_url + str(hashlib.sha256(original_url.encode()).hexdigest())).encode()).hexdigest()[:6]
    
    # Insert the short code and original URL into the database
    c.execute("INSERT INTO urls VALUES (?, ?, 0)", (short_code, original_url))
    conn.commit()
    conn.close()
    
    return short_code

def decode_url(short_code: str) -> str:
    """
    Decodes a short code to the original URL.
    
    Args:
    short_code (str): The short code to be decoded.
    
    Returns:
    str: The original URL for the short code.
    """
    conn = sqlite3.connect('url_shortener.db')
    c = conn.cursor()
    c.execute("SELECT original_url FROM urls WHERE short_code=?", (short_code,))
    result = c.fetchone()
    conn.close()
    
    if result:
        return result[0]
    else:
        raise ValueError("Short code not found")

def increment_click_count(short_code: str) -> None:
    """
    Increments the click count for a short code.
    
    Args:
    short_code (str): The short code to increment the click count for.
    """
    conn = sqlite3.connect('url_shortener.db')
    c = conn.cursor()
    c.execute("UPDATE urls SET click_count = click_count + 1 WHERE short_code=?", (short_code,))
    conn.commit()
    conn.close()

@app.route('/encode', methods=['POST'])
def encode():
    original_url = request.form['original_url']
    short_code = encode_url(original_url)
    return f"Short code: {short_code}"

@app.route('/decode', methods=['POST'])
def decode():
    short_code = request.form['short_code']
    original_url = decode_url(short_code)
    return f"Original URL: {original_url}"

@app.route('/<short_code>')
def redirect_to_original_url(short_code: str):
    try:
        original_url = decode_url(short_code)
        increment_click_count(short_code)
        return redirect(original_url)
    except ValueError:
        return "Short code not found", 404

@app.route('/analytics', methods=['GET'])
def get_analytics():
    conn = sqlite3.connect('url_shortener.db')
    c = conn.cursor()
    c.execute("SELECT short_code, click_count FROM urls")
    result = c.fetchall()
    conn.close()
    analytics: Dict[str, int] = {}
    for short_code, click_count in result:
        analytics[short_code] = click_count
    return analytics

if __name__ == '__main__':
    app.run(debug=True)