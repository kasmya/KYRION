from flask import Flask, request, redirect, url_for
from urllib.parse import urlparse
from hashlib import sha256
from typing import Dict

app = Flask(__name__)

# In-memory storage for demonstration purposes only.
# In a real application, use a secure database.
url_map: Dict[str, str] = {}
click_counts: Dict[str, int] = {}

def is_valid_url(url: str) -> bool:
    """
    Check if a URL is valid.

    :param url: The URL to check.
    :return: True if the URL is valid, False otherwise.
    """
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except ValueError:
        return False

def encode_url(long_url: str) -> str:
    """
    Encode a long URL to a short code.

    :param long_url: The long URL to encode.
    :return: The short code.
    """
    if not is_valid_url(long_url):
        raise ValueError("Invalid URL")
    # Use SHA-256 to generate a unique short code
    short_code = sha256(long_url.encode()).hexdigest()[:6]
    url_map[short_code] = long_url
    return short_code

def decode_url(short_code: str) -> str:
    """
    Decode a short code to the original URL.

    :param short_code: The short code to decode.
    :return: The original URL.
    """
    return url_map.get(short_code)

@app.route('/encode', methods=['POST'])
def encode():
    """
    Encode a long URL to a short code.

    :return: The short code.
    """
    long_url = request.form['url']
    try:
        short_code = encode_url(long_url)
        return short_code
    except ValueError as e:
        return str(e), 400

@app.route('/<short_code>')
def redirect_to_long_url(short_code: str):
    """
    Redirect to the original URL.

    :param short_code: The short code.
    :return: A redirect to the original URL.
    """
    long_url = decode_url(short_code)
    if long_url:
        click_counts[short_code] = click_counts.get(short_code, 0) + 1
        return redirect(long_url)
    return "Short code not found", 404

@app.route('/analytics/<short_code>')
def get_analytics(short_code: str):
    """
    Get the click count for a short code.

    :param short_code: The short code.
    :return: The click count.
    """
    click_count = click_counts.get(short_code, 0)
    return str(click_count)

if __name__ == '__main__':
    app.run(debug=True)