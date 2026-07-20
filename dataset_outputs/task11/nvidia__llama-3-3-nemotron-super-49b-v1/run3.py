from flask import Flask, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from urllib.parse import urlparse
from uuid import uuid4
from typing import Optional

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///url_shortener.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)


class URL(db.Model):
    """Database Model for Storing URLs"""
    id = db.Column(db.String(36), primary_key=True)
    original_url = db.Column(db.String(1024), nullable=False)
    clicks = db.Column(db.Integer, default=0)

    def __repr__(self):
        return f"URL('{self.id}', '{self.original_url}', {self.clicks})"


def validate_url(url: str) -> bool:
    """
    Validate if a URL is valid.

    :param url: URL to validate
    :return: True if valid, False otherwise
    """
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except ValueError:
        return False


@app.route("/encode", methods=["POST"])
def encode_url() -> dict:
    """
    Endpoint to encode a long URL to a short code.

    :return: JSON response with short code or error
    """
    data = request.json
    if not data or "url" not in data:
        return {"error": "Missing URL in request"}, 400

    original_url = data["url"]
    if not validate_url(original_url):
        return {"error": "Invalid URL"}, 400

    # Check if URL already exists
    existing_url = URL.query.filter_by(original_url=original_url).first()
    if existing_url:
        short_code = existing_url.id
    else:
        short_code = str(uuid4())[:6]  # Generate a 6-character short code
        new_url = URL(id=short_code, original_url=original_url)
        db.session.add(new_url)
        db.session.commit()

    return {"short_code": short_code}, 201


@app.route("/decode/<string:short_code>", methods=["GET"])
def decode_url(short_code: str) -> dict:
    """
    Endpoint to decode a short code to the original URL.

    :param short_code: Short code to decode
    :return: JSON response with original URL or error
    """
    url = URL.query.filter_by(id=short_code).first()
    if not url:
        return {"error": "Short code not found"}, 404
    return {"original_url": url.original_url}, 200


@app.route("/<string:short_code>", methods=["GET"])
def redirect_url(short_code: str) -> str:
    """
    Endpoint to handle redirection and track clicks.

    :param short_code: Short code to redirect
    :return: Redirect response or error page
    """
    url = URL.query.filter_by(id=short_code).first()
    if not url:
        return "Short code not found", 404

    url.clicks += 1
    db.session.commit()
    return redirect(url.original_url)


@app.route("/analytics/<string:short_code>", methods=["GET"])
def get_analytics(short_code: str) -> dict:
    """
    Endpoint to retrieve click analytics for a short code.

    :param short_code: Short code to get analytics for
    :return: JSON response with click count or error
    """
    url = URL.query.filter_by(id=short_code).first()
    if not url:
        return {"error": "Short code not found"}, 404
    return {"clicks": url.clicks}, 200


@app.errorhandler(404)
def page_not_found(error) -> str:
    return "Page not found", 404


@app.errorhandler(500)
def internal_server_error(error) -> str:
    return "Internal server error", 500


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)