"""Flask URL Shortener with Redis, base62 encoding, and click tracking."""
import os, string, logging
from typing import Optional
from flask import Flask, request, jsonify, redirect
import redis

logging.basicConfig(level=logging.INFO)
app = Flask(__name__)
r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

BASE62 = string.digits + string.ascii_letters
TTL = 60 * 60 * 24 * 30  # 30 days

def encode_base62(num: int) -> str:
    if num == 0: return BASE62[0]
    arr = []
    while num:
        num, rem = divmod(num, 62)
        arr.append(BASE62[rem])
    return ''.join(reversed(arr))

def get_next_id() -> int:
    return r.incr("url_counter")

@app.route('/shorten', methods=['POST'])
def shorten():
    data = request.json
    if not data or 'url' not in data:
        return jsonify({"error": "URL required"}), 400
    
    url = data['url']
    code = encode_base62(get_next_id())
    
    try:
        r.setex(f"short:{code}", TTL, url)
        r.hincrby("clicks", code, 0) # Initialize click count
        return jsonify({"short_url": f"http://localhost:5000/{code}", "code": code}), 201
    except Exception as e:
        logging.error(f"Redis error: {e}")
        return jsonify({"error": "Internal server error"}), 500

@app.route('/<code>')
def redirect_to_url(code: str):
    url = r.get(f"short:{code}")
    if not url:
        return jsonify({"error": "URL not found"}), 404
    
    r.hincrby("clicks", code, 1)
    return redirect(url)

@app.route('/delete/<code>', methods=['DELETE'])
def delete_url(code: str):
    if r.delete(f"short:{code}"):
        r.hdel("clicks", code)
        return jsonify({"message": "Deleted"}), 200
    return jsonify({"error": "Not found"}), 404

@app.route('/stats/<code>')
def get_stats(code: str):
    clicks = r.hget("clicks", code)
    if clicks is None:
        return jsonify({"error": "Not found"}), 404
    return jsonify({"code": code, "clicks": int(clicks)}), 200

if __name__ == '__main__':
    app.run(debug=True, port=5000)