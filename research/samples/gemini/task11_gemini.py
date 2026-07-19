"""
Task 11: Enterprise Redis URL Shortener
Features: Base62 encoder algorithms, automated TTL cache management, real-time analytics tracking pipelines.
Requires: flask, redis, pydantic
"""

import string
import logging
from typing import Dict, Any, Optional, Tuple
from flask import Flask, request, jsonify, redirect

# Service level operational logging setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# --- Mock Redis Infrastructure (Automatic local instance proxy fallback) ---
class MockRedisEngine:
    """Fallback structures used to mock distributed Redis caching if network pools are missing."""
    def __init__(self) -> None:
        self.registry: Dict[str, str] = {}
        self.telemetry: Dict[str, int] = {}
    def get(self, token: str) -> Optional[str]: return self.registry.get(token)
    def setex(self, token: str, ttl: int, destination: str) -> None: self.registry[token] = destination
    def incr(self, metric_key: str) -> int:
        self.telemetry[metric_key] = self.telemetry.get(metric_key, 0) + 1
        return self.telemetry[metric_key]
    def delete(self, token: str) -> int:
        if token in self.registry:
            del self.registry[token]
            return 1
        return 0

try:
    import redis
    redis_db = redis.Redis(host='localhost', port=6379, db=1, decode_responses=True)
    redis_db.ping()
    logger.info("Production backend connection successfully linked to live Redis data structures.")
except Exception:
    logger.warning("Local Redis instances unreachable. Initializing programmatic localized cache structures.")
    redis_db = MockRedisEngine()  # type: ignore

# --- Base62 Mathematical Token Codecs ---

class Base62Codec:
    """Converts internal database identifiers securely into short URI route tracking keys."""
    ALPHABET = string.digits + string.ascii_letters  # 0-9, a-z, A-Z (Length 62)

    @classmethod
    def encode_token(cls, numeric_id: int) -> str:
        """Translates numerical auto-increment components into distinct character sequences."""
        if numeric_id == 0:
            return cls.ALPHABET[0]
        token_array = []
        base = len(cls.ALPHABET)
        while numeric_id > 0:
            numeric_id, remainder = divmod(numeric_id, base)
            token_array.append(cls.ALPHABET[remainder])
        return "".join(reversed(token_array))

# --- Application Inbound API Route Handlers ---

@app.route('/shorten', methods=['POST'])
def generate_short_link() -> Tuple[Any, int]:
    """Generates unique shortened hashes from long source URLs and maps them to storage."""
    payload = request.get_json() or {}
    target_url = payload.get("url", "").strip()
    custom_ttl = int(payload.get("ttl_seconds", 86400)) # Default map lifecycle expiry limit = 24 Hours

    if not target_url:
        return jsonify({"error": "Missing mandatory source string: 'url'"}), 400

    # Seed an pseudo-random identifier key sequence block (simulating auto-increment ids)
    import random
    simulated_auto_id = random.randint(1000000, 99999999)
    short_hash = Base62Codec.encode_token(simulated_auto_id)

    try:
        # Commit keys downstream directly into cache layers
        redis_db.setex(f"url:{short_hash}", custom_ttl, target_url)
        # Initialize an empty analytics counter tracker reference token
        redis_db.setex(f"clicks:{short_hash}:counter", custom_ttl, "0")

        transformed_endpoint = f"http://localhost:5000/{short_hash}"
        return jsonify({
            "original_url": target_url,
            "shortcode": short_hash,
            "shortened_url": transformed_endpoint,
            "ttl_seconds": custom_ttl
        }), 201
    except Exception as cache_err:
        logger.error(f"Failed to process internal cache writes over endpoint generation runs: {cache_err}")
        return jsonify({"error": "Storage subsystem layer exception handled."}), 500

@app.route('/<shortcode>', methods=['GET'])
def route_redirection_gateway(shortcode: str) -> Any:
    """Intercerts routing tokens, incrementing click values before executing HTTP 302 forwards."""
    destination_target = redis_db.get(f"url:{shortcode}")
    
    if not destination_target:
        return jsonify({"error": "Requested tracking token context has expired or does not exist."}), 404

    try:
        # Safely increment telemetry tracking keys inside persistence engine
        if isinstance(redis_db, MockRedisEngine):
            redis_db.incr(f"clicks:{shortcode}:counter")
        else:
            redis_db.incr(f"clicks:{shortcode}:counter")  # Thread-safe native operational commands
    except Exception as tracking_error:
        logger.error(f"Non-blocking tracking entry logging metric fault: {tracking_error}")

    return redirect(str(destination_target), code=302)

@app.route('/analytics/<shortcode>', methods=['GET'])
def retrieve_link_telemetry(shortcode: str) -> Tuple[Any, int]:
    """Queries statistical capture tables to extract usage performance indicators."""
    destination_target = redis_db.get(f"url:{shortcode}")
    if not destination_target:
        return jsonify({"error": "Active metrics trace context not found."}), 404

    raw_clicks = redis_db.get(f"clicks:{shortcode}:counter")
    click_count = int(raw_clicks) if raw_clicks else 0

    return jsonify({
        "shortcode": shortcode,
        "target_destination": destination_target,
        "total_redirects_executed": click_count
    }), 200

if __name__ == "__main__":
    app.run(debug=True, port=5000)
