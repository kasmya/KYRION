"""
### Task 17: Stock Price Tracker (Flask + yfinance)

A Flask app for managing a per-user stock watchlist, showing current
prices and historical charts (via Plotly), and raising alerts when a
price crosses a user-defined threshold. Uses SQLite for persistence and a
simple session-based login.

Requirements:
    pip install flask flask-sqlalchemy yfinance plotly bcrypt

Run:
    python 17_stock_price_tracker.py
"""

from __future__ import annotations

import logging
from datetime import datetime
from functools import wraps
from typing import Optional

import bcrypt
import plotly.graph_objects as go
import yfinance as yf
from flask import Flask, jsonify, request, session
from flask_sqlalchemy import SQLAlchemy

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("stock_price_tracker")

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///stock_tracker.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.secret_key = "change-this-in-production"  # nosec: replace via env var in real deployments

db = SQLAlchemy(app)


class User(db.Model):
    """Represents a registered user of the stock tracker."""

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    watchlist_items = db.relationship("WatchlistItem", backref="user", lazy=True)


class WatchlistItem(db.Model):
    """Represents a single ticker on a user's watchlist, with an optional alert threshold."""

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    ticker = db.Column(db.String(16), nullable=False)
    alert_above = db.Column(db.Float, nullable=True)
    alert_below = db.Column(db.Float, nullable=True)
    added_at = db.Column(db.DateTime, default=datetime.utcnow)


def login_required(view_func):
    """Decorator enforcing that a user is logged in via session."""

    @wraps(view_func)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return jsonify({"error": "authentication required"}), 401
        return view_func(*args, **kwargs)

    return wrapper


@app.post("/api/register")
def register():
    """Registers a new user with a hashed password."""
    payload = request.get_json(silent=True) or {}
    email = payload.get("email", "").strip().lower()
    password = payload.get("password", "")

    if not email or "@" not in email:
        return jsonify({"error": "a valid email is required"}), 400
    if len(password) < 8:
        return jsonify({"error": "password must be at least 8 characters"}), 400
    if User.query.filter_by(email=email).first():
        return jsonify({"error": "email already registered"}), 409

    password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    user = User(email=email, password_hash=password_hash)
    db.session.add(user)
    db.session.commit()
    logger.info("Registered new user '%s'", email)
    return jsonify({"id": user.id, "email": user.email}), 201


@app.post("/api/login")
def login():
    """Authenticates a user and starts a session."""
    payload = request.get_json(silent=True) or {}
    email = payload.get("email", "").strip().lower()
    password = payload.get("password", "")

    user = User.query.filter_by(email=email).first()
    if not user or not bcrypt.checkpw(password.encode("utf-8"), user.password_hash.encode("utf-8")):
        return jsonify({"error": "invalid email or password"}), 401

    session["user_id"] = user.id
    logger.info("User '%s' logged in", email)
    return jsonify({"message": "logged in", "user_id": user.id}), 200


@app.post("/api/logout")
@login_required
def logout():
    """Logs out the current user by clearing the session."""
    session.clear()
    return jsonify({"message": "logged out"}), 200


@app.post("/api/watchlist")
@login_required
def add_to_watchlist():
    """Adds a ticker to the current user's watchlist, with optional alert thresholds."""
    payload = request.get_json(silent=True) or {}
    ticker = payload.get("ticker", "").strip().upper()
    alert_above = payload.get("alert_above")
    alert_below = payload.get("alert_below")

    if not ticker:
        return jsonify({"error": "ticker is required"}), 400

    try:
        info = yf.Ticker(ticker).fast_info
        if info is None or info.get("lastPrice") is None:
            raise ValueError("ticker returned no price data")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Rejected unknown ticker '%s': %s", ticker, exc)
        return jsonify({"error": f"could not validate ticker '{ticker}'"}), 400

    item = WatchlistItem(
        user_id=session["user_id"],
        ticker=ticker,
        alert_above=alert_above,
        alert_below=alert_below,
    )
    db.session.add(item)
    db.session.commit()
    return jsonify({"id": item.id, "ticker": item.ticker}), 201


@app.delete("/api/watchlist/<int:item_id>")
@login_required
def remove_from_watchlist(item_id: int):
    """Removes a ticker from the current user's watchlist."""
    item = WatchlistItem.query.filter_by(id=item_id, user_id=session["user_id"]).first()
    if not item:
        return jsonify({"error": "watchlist item not found"}), 404
    db.session.delete(item)
    db.session.commit()
    return jsonify({"deleted": item_id}), 200


@app.get("/api/watchlist")
@login_required
def get_watchlist():
    """Returns the current user's watchlist with live prices and any triggered alerts."""
    items = WatchlistItem.query.filter_by(user_id=session["user_id"]).all()
    results = []
    for item in items:
        price = _get_current_price(item.ticker)
        alert_triggered = _check_alert(price, item.alert_above, item.alert_below)
        results.append(
            {
                "id": item.id,
                "ticker": item.ticker,
                "current_price": price,
                "alert_above": item.alert_above,
                "alert_below": item.alert_below,
                "alert_triggered": alert_triggered,
            }
        )
    return jsonify(results), 200


def _get_current_price(ticker: str) -> Optional[float]:
    """Fetches the latest price for a ticker, returning None on failure."""
    try:
        fast_info = yf.Ticker(ticker).fast_info
        return float(fast_info["lastPrice"])
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to fetch price for '%s': %s", ticker, exc)
        return None


def _check_alert(
    price: Optional[float], alert_above: Optional[float], alert_below: Optional[float]
) -> bool:
    """Returns True if the current price crosses either configured threshold."""
    if price is None:
        return False
    if alert_above is not None and price >= alert_above:
        return True
    if alert_below is not None and price <= alert_below:
        return True
    return False


@app.get("/api/history/<ticker>")
@login_required
def get_history_chart(ticker: str):
    """Returns a Plotly chart (as JSON) of historical closing prices for a ticker."""
    period = request.args.get("period", "1mo")
    try:
        history = yf.Ticker(ticker.upper()).history(period=period)
        if history.empty:
            return jsonify({"error": f"no historical data for '{ticker}'"}), 404
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to fetch history for '%s': %s", ticker, exc)
        return jsonify({"error": "failed to fetch historical data"}), 502

    figure = go.Figure(
        data=[go.Scatter(x=history.index.astype(str), y=history["Close"], mode="lines")]
    )
    figure.update_layout(title=f"{ticker.upper()} Closing Price ({period})")
    return jsonify(figure.to_plotly_json()), 200


@app.errorhandler(500)
def handle_internal_error(exc):
    logger.exception("Unhandled server error: %s", exc)
    return jsonify({"error": "internal server error"}), 500


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(host="0.0.0.0", port=5001, debug=False)
