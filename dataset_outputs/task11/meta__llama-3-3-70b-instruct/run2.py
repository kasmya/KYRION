from flask import Flask, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from urllib.parse import urlparse
import uuid
import logging
from typing import Dict

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///url_shortener.db"
db = SQLAlchemy(app)

class URL(db.Model):
    """Represents a shortened URL."""
    id = db.Column(db.Integer, primary_key=True)
    original_url = db.Column(db.String(200), nullable=False)
    short_code = db.Column(db.String(10), unique=True, nullable=False)
    click_count = db.Column(db.Integer, default=0)

    def __init__(self, original_url: str):
        """Initializes a new URL object."""
        self.original_url = original_url
        self.short_code = str(uuid.uuid4().int)[:6]

    def __repr__(self):
        """Returns a string representation of the URL object."""
        return f"URL('{self.original_url}', '{self.short_code}')"

def is_valid_url(url: str) -> bool:
    """Checks if a URL is valid."""
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except ValueError:
        return False

@app.route("/encode", methods=["POST"])
def encode_url() -> Dict[str, str]:
    """Encodes a long URL to a short code."""
    data = request.json
    if "url" not in data:
        return {"error": "Missing URL parameter"}, 400
    original_url = data["url"]
    if not is_valid_url(original_url):
        return {"error": "Invalid URL"}, 400
    existing_url = URL.query.filter_by(original_url=original_url).first()
    if existing_url:
        return {"short_code": existing_url.short_code}
    new_url = URL(original_url)
    db.session.add(new_url)
    db.session.commit()
    return {"short_code": new_url.short_code}

@app.route("/decode/<short_code>", methods=["GET"])
def decode_url(short_code: str) -> Dict[str, str]:
    """Decodes a short code to the original URL."""
    url = URL.query.filter_by(short_code=short_code).first()
    if not url:
        return {"error": "Invalid short code"}, 404
    return {"original_url": url.original_url}

@app.route("/<short_code>", methods=["GET"])
def redirect_url(short_code: str) -> None:
    """Redirects to the original URL."""
    url = URL.query.filter_by(short_code=short_code).first()
    if not url:
        return {"error": "Invalid short code"}, 404
    url.click_count += 1
    db.session.commit()
    return redirect(url.original_url)

@app.route("/analytics/<short_code>", methods=["GET"])
def get_analytics(short_code: str) -> Dict[str, int]:
    """Returns the click count for a short code."""
    url = URL.query.filter_by(short_code=short_code).first()
    if not url:
        return {"error": "Invalid short code"}, 404
    return {"click_count": url.click_count}

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    app.run(debug=True)