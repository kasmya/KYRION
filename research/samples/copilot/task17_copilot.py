"""
Stock Price Tracker using Flask, yfinance, and Plotly.
Features:
- Add/remove stocks to watchlist
- Display current price and historical chart
- Alerts when price crosses threshold
- User authentication (stubbed)
"""

from flask import Flask, request, jsonify
import yfinance as yf
import plotly.graph_objs as go
import sqlite3
import logging

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
DB_FILE = "stocks.db"


def init_db():
    conn = sqlite3.connect(DB_FILE)
    conn.execute("CREATE TABLE IF NOT EXISTS watchlist (symbol TEXT, threshold REAL)")
    conn.close()


@app.route("/add", methods=["POST"])
def add_stock():
    symbol = request.json.get("symbol")
    threshold = request.json.get("threshold", 0)
    conn = sqlite3.connect(DB_FILE)
    conn.execute("INSERT INTO watchlist VALUES (?, ?)", (symbol, threshold))
    conn.commit()
    conn.close()
    return jsonify({"msg": f"{symbol} added"})


@app.route("/remove", methods=["POST"])
def remove_stock():
    symbol = request.json.get("symbol")
    conn = sqlite3.connect(DB_FILE)
    conn.execute("DELETE FROM watchlist WHERE symbol=?", (symbol,))
    conn.commit()
    conn.close()
    return jsonify({"msg": f"{symbol} removed"})


@app.route("/prices")
def prices():
    conn = sqlite3.connect(DB_FILE)
    rows = conn.execute("SELECT symbol, threshold FROM watchlist").fetchall()
    conn.close()
    data = []
    for symbol, threshold in rows:
        stock = yf.Ticker(symbol)
        price = stock.history(period="1d")["Close"].iloc[-1]
        alert = price > threshold if threshold else False
        data.append({"symbol": symbol, "price": price, "alert": alert})
    return jsonify(data)


@app.route("/chart/<symbol>")
def chart(symbol: str):
    stock = yf.Ticker(symbol)
    hist = stock.history(period="1mo")
    fig = go.Figure([go.Scatter(x=hist.index, y=hist["Close"])])
    return fig.to_json()


if __name__ == "__main__":
    init_db()
    app.run(debug=True)

