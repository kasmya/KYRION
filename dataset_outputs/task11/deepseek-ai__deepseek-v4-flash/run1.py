import secrets
import string
import urllib.parse
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple

from flask import Flask, request, redirect, jsonify, abort, url_for


class URLShortener:
    """
    A simple URL shortener service with analytics.

    Attributes:
        app: Flask application instance.
        _storage: Dict[str, Tuple[str, int, datetime]] mapping short_code to
            (original_url, click_count, created_at).
    """

    def __init__(self) -> None:
        self.app = Flask(__name__)
        self._storage: Dict[str, Tuple[str, int, datetime]] = {}

        # Register routes
        self.app.add_url_rule('/encode', 'encode', self.encode, methods=['POST'])
        self.app.add_url_rule('/decode', 'decode', self.decode, methods=['POST'])
        self.app.add_url_rule('/<short_code>', 'redirect_to_url', self.redirect_to_url)
        self.app.add_url_rule('/analytics/<short_code>', 'analytics', self.analytics)

    def _generate_short_code(self) -> str:
        """Generate a cryptographically secure random short code (6 characters)."""
        alphabet = string.ascii_letters + string.digits
        return ''.join(secrets.choice(alphabet) for _ in range(6))

    def _is_valid_url(self, url: str) -> bool:
        """Validate URL structure using urllib.parse."""
        try:
            parsed = urllib.parse.urlparse(url)
            # Must have scheme and netloc (e.g., http://example.com)
            return all([parsed.scheme, parsed.netloc])
        except Exception:
            return False

    def encode(self) -> Dict[str, str]:
        """
        Encode a long URL to a short code.

        Request JSON: {"url": "https://example.com/very/long/url"}
        Response JSON: {"short_url": "http://localhost:5000/abc123"}
        """
        data = request.get_json(silent=True)
        if not data or 'url' not in data:
            abort(400, description="Missing 'url' in request body")

        long_url = data['url'].strip()

        if not self._is_valid_url(long_url):
            abort(400, description="Invalid URL provided")

        # Ensure uniqueness (collision unlikely with 62^6 combinations)
        while True:
            short_code = self._generate_short_code()
            if short_code not in self._storage:
                break

        self._storage[short_code] = (long_url, 0, datetime.now(timezone.utc))
        short_url = url_for('redirect_to_url', short_code=short_code, _external=True)
        return {'short_url': short_url}

    def decode(self) -> Dict[str, str]:
        """
        Decode a short code to the original URL.

        Request JSON: {"short_url": "http://localhost:5000/abc123"}
        Response JSON: {"original_url": "https://example.com/very/long/url"}
        """
        data = request.get_json(silent=True)
        if not data or 'short_url' not in data:
            abort(400, description="Missing 'short_url' in request body")

        short_url = data['short_url'].strip()
        # Extract short code from the URL
        parsed = urllib.parse.urlparse(short_url)
        path = parsed.path.strip('/')
        if not path:
            abort(400, description="Invalid short URL format")

        short_code = path

        entry = self._storage.get(short_code)
        if not entry:
            abort(404, description="Short code not found")

        original_url = entry[0]
        return {'original_url': original_url}

    def redirect_to_url(self, short_code: str) -> redirect:
        """Redirect to the original URL corresponding to the short code."""
        entry = self._storage.get(short_code)
        if not entry:
            abort(404, description="Short code not found")

        original_url, click_count, _ = entry
        # Increment click count
        self._storage[short_code] = (original_url, click_count + 1, _)
        return redirect(original_code, code=302)

    def analytics(self, short_code: str) -> Dict[str, object]:
        """Return analytics for a given short code."""
        entry = self._storage.get(short_code)
        if not entry:
            abort(404, description="Short code not found")

        original_url, click_count, created_at = entry
        return {
            'original_url': original_url,
            'click_count': click_count,
            'created_at': created_at.isoformat()
        }

    def run(self, host: str = '0.0.0.0', port: int = 5000) -> None:
        """Run the Flask development server."""
        self.app.run(host=host, port=port, debug=True)


if __name__ == '__main__':
    shortener = URLShortener()
    shortener.run()