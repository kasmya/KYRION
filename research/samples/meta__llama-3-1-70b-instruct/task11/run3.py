from flask import Flask, request, redirect, url_for, jsonify
from urllib.parse import urlparse, urlunparse
from hashlib import sha256
from base64 import b64encode
from typing import Optional

app = Flask(__name__)

# In-memory storage for demonstration purposes only
# Use a proper database in production
storage = {}

def is_valid_url(url: str) -> bool:
    """Check if a URL is valid."""
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except ValueError:
        return False

def encode_url(long_url: str) -> str:
    """Encode a long URL to a short code."""
    if not is_valid_url(long_url):
        raise ValueError("Invalid URL")
    
    # Use a secure hash function to generate a short code
    short_code = b64encode(sha256(long_url.encode()).digest()).decode()
    short_code = short_code.replace('+', '-').replace('/', '_').rstrip('=')
    
    return short_code

def decode_url(short_code: str) -> Optional[str]:
    """Decode a short code to the original URL."""
    return storage.get(short_code)

@app.route('/shorten', methods=['POST'])
def shorten_url():
    """Encode a long URL to a short code."""
    data = request.get_json()
    if not data or 'url' not in data:
        return jsonify({'error': 'Invalid request'}), 400
    
    long_url = data['url']
    try:
        short_code = encode_url(long_url)
        storage[short_code] = long_url
        return jsonify({'short_code': short_code}), 201
    except ValueError as e:
        return jsonify({'error': str(e)}), 400

@app.route('/<short_code>', methods=['GET'])
def redirect_url(short_code: str):
    """Redirect a short code to the original URL."""
    long_url = decode_url(short_code)
    if not long_url:
        return jsonify({'error': 'Invalid short code'}), 404
    
    # Track click count
    storage[short_code + '_clicks'] = storage.get(short_code + '_clicks', 0) + 1
    return redirect(long_url, code=301)

@app.route('/analytics/<short_code>', methods=['GET'])
def get_analytics(short_code: str):
    """Get click count for a short code."""
    clicks = storage.get(short_code + '_clicks', 0)
    return jsonify({'clicks': clicks}), 200

if __name__ == '__main__':
    app.run(debug=True)