from flask import Flask, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from urllib.parse import urlparse
from uuid import uuid4
import logging
from typing import Optional

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:////tmp/url_shortener.db"
db = SQLAlchemy(app)

class URL(db.Model):
    id = db.Column(db.String(8), primary_key=True)
    original_url = db.Column(db.String(2048), nullable=False)
    clicks = db.Column(db.Integer, default=0)

    def __init__(self, original_url: str, id: Optional[str] = None):
        if id is None:
            id = str(uuid4().int)[:8]  # Generate an 8-char ID
        self.id = id
        self.original_url = original_url

    def __repr__(self):
        return f"<URL {self.id} -> {self.original_url}>"

def validate_url(url: str) -> bool:
    """Validate if a URL is properly formatted."""
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except ValueError:
        return False

@app.route("/shorten", methods=["POST"])
def shorten_url():
    """Endpoint to shorten a URL."""
    data = request.get_json()
    if not data or "url" not in data:
        return {"error": "Missing URL in request"}, 400
    
    original_url = data["url"]
    if not validate_url(original_url):
        return {"error": "Invalid URL"}, 400

    # Check if URL already exists
    existing_url = URL.query.filter_by(original_url=original_url).first()
    if existing_url:
        return {"short_code": existing_url.id}, 200

    new_url = URL(original_url)
    db.session.add(new_url)
    db.session.commit()
    return {"short_code": new_url.id}, 201

@app.route("/<string:short_code>", methods=["GET"])
def redirect_to_original(short_code: str):
    """Redirects the short code to the original URL and tracks clicks."""
    url = URL.query.get(short_code)
    if not url:
        return {"error": "Short code not found"}, 404

    url.clicks += 1
    db.session.commit()
    return redirect(url.original_url, code=301)

@app.route("/analytics/<string:short_code>", methods=["GET"])
def get_clicks(short_code: str):
    """Retrieve click count for a short code."""
    url = URL.query.get(short_code)
    if not url:
        return {"error": "Short code not found"}, 404
    return {"clicks": url.clicks}, 200

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    logging.basicConfig(level=logging.INFO)
    app.run(debug=True)