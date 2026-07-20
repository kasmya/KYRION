from flask import Flask, request, redirect, url_for
from urllib.parse import urlparse
from uuid import uuid4
from typing import Dict, Optional

app = Flask(__name__)
# In-memory storage for simplicity; use a database in production
url_store: Dict[str, str] = {}
analytics: Dict[str, int] = {}

def is_valid_url(url: str) -> bool:
    """Check if a URL is valid."""
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except ValueError:
        return False

@app.route('/encode', methods=['POST'])
def encode_url() -> str:
    """Encode a long URL to a short code."""
    long_url = request.form.get('long_url')
    if not long_url or not is_valid_url(long_url):
        return "Invalid URL", 400
    
    # Generate a unique short code
    short_code = str(uuid4())[:6]  # Use first 6 chars for simplicity
    # Ensure uniqueness (simplified, might not be efficient for large scales)
    while short_code in url_store:
        short_code = str(uuid4())[:6]
    
    url_store[short_code] = long_url
    analytics[short_code] = 0  # Initialize click count
    return short_code

@app.route('/decode/<string:short_code>', methods=['GET'])
def decode_url(short_code: str) -> Optional[str]:
    """Decode a short code to the original URL."""
    if short_code not in url_store:
        return "Short code not found", 404
    return url_store[short_code]

@app.route('/<string:short_code>', methods=['GET'])
def redirect_url(short_code: str) -> str:
    """Redirect to the original URL and track clicks."""
    if short_code not in url_store:
        return "Short code not found", 404
    analytics[short_code] += 1  # Increment click count
    return redirect(url_store[short_code], code=301)

@app.route('/analytics/<string:short_code>', methods=['GET'])
def get_analytics(short_code: str) -> str:
    """Retrieve click count for a short code."""
    if short_code not in analytics:
        return "Short code not found", 404
    return str(analytics[short_code])

@app.route('/healthcheck', methods=['GET'])
def healthcheck() -> str:
    """Simple health check endpoint."""
    return "Service is running"

if __name__ == '__main__':
    app.run(debug=True)