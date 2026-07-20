from flask import Flask, request, redirect, abort
from urllib.parse import urlparse
import uuid
import hashlib
from typing import Dict, Optional

app = Flask(__name__)

# In-memory storage for simplicity (not recommended for production)
storage: Dict[str, Dict[str, str]] = {}

def is_valid_url(url: str) -> bool:
    """
    Validate if the URL is valid.

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

def encode_url(long_url: str) -> Optional[str]:
    """
    Encode a long URL to a short code.

    Args:
    long_url (str): The long URL to be encoded.

    Returns:
    str: The short code if successful, None otherwise.
    """
    if not is_valid_url(long_url):
        return None
    # Use a combination of hash and UUID to generate a unique short code
    short_code = hashlib.sha256(str(uuid.uuid4()).encode()).hexdigest()[:6]
    storage[short_code] = {"long_url": long_url, "click_count": 0}
    return short_code

def decode_url(short_code: str) -> Optional[str]:
    """
    Decode a short code to the original URL.

    Args:
    short_code (str): The short code to be decoded.

    Returns:
    str: The original URL if successful, None otherwise.
    """
    return storage.get(short_code, {}).get("long_url")

def track_click(short_code: str) -> None:
    """
    Track a click on the short code.

    Args:
    short_code (str): The short code to track.
    """
    if short_code in storage:
        storage[short_code]["click_count"] += 1

@app.route("/shorten", methods=["POST"])
def shorten_url():
    """
    Shorten a URL.

    Returns:
    str: The short code.
    """
    long_url = request.get_json().get("url")
    if not long_url:
        abort(400)
    short_code = encode_url(long_url)
    if not short_code:
        abort(400)
    return {"short_code": short_code}

@app.route("/<short_code>", methods=["GET"])
def redirect_to_long_url(short_code: str):
    """
    Redirect to the original URL.

    Args:
    short_code (str): The short code to redirect.
    """
    long_url = decode_url(short_code)
    if not long_url:
        abort(404)
    track_click(short_code)
    return redirect(long_url, code=301)

@app.route("/analytics/<short_code>", methods=["GET"])
def get_analytics(short_code: str):
    """
    Get the click count for the short code.

    Args:
    short_code (str): The short code to get analytics.

    Returns:
    int: The click count.
    """
    if short_code not in storage:
        abort(404)
    return {"click_count": storage[short_code]["click_count"]}

if __name__ == "__main__":
    app.run(debug=True)