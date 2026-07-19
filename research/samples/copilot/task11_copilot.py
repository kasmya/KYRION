"""
URL Shortener using Flask and Redis.
Features:
- Generate short codes (base62)
- Store mapping in Redis with TTL
- Redirect to original URL
- Click tracking
- API for create/delete
"""

from flask import Flask, request, redirect, jsonify
import redis
import string
import random
import logging

app = Flask(__name__)
r = redis.Redis(host="localhost", port=6379, db=0)
logging.basicConfig(level=logging.INFO)


def generate_code(length: int = 6) -> str:
    chars = string.ascii_letters + string.digits
    return "".join(random.choice(chars) for _ in range(length))


@app.route("/shorten", methods=["POST"])
def shorten():
    url = request.json.get("url")
    if not url:
        return jsonify({"error": "URL required"}), 400
    code = generate_code()
    r.setex(f"url:{code}", 3600, url)
    r.set(f"clicks:{code}", 0)
    return jsonify({"short_url": f"http://localhost:5000/{code}"})


@app.route("/<code>")
def redirect_url(code: str):
    url = r.get(f"url:{code}")
    if url:
        r.incr(f"clicks:{code}")
        return redirect(url.decode())
    return jsonify({"error": "Invalid code"}), 404


@app.route("/stats/<code>")
def stats(code: str):
    clicks = r.get(f"clicks:{code}")
    return jsonify({"clicks": int(clicks) if clicks else 0})


@app.route("/delete/<code>", methods=["DELETE"])
def delete(code: str):
    r.delete(f"url:{code}")
    r.delete(f"clicks:{code}")
    return jsonify({"msg": "Deleted"})


if __name__ == "__main__":
    app.run(debug=True)

