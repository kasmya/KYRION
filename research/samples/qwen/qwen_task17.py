"""Stock Price Tracker with Flask, yfinance, Plotly, and alerts."""
import os, logging
from typing import List, Dict
from flask import Flask, request, jsonify, render_template_string
import yfinance as yf
import plotly
import plotly.express as px
import pandas as pd
from sqlalchemy import create_engine, Column, Integer, String, Float
from sqlalchemy.orm import sessionmaker, declarative_base

logging.basicConfig(level=logging.INFO)
app = Flask(__name__)
engine = create_engine("sqlite:///stocks.db")
Base = declarative_base()
Session = sessionmaker(bind=engine)

class Watchlist(Base):
    __tablename__ = "watchlist"
    id = Column(Integer, primary_key=True)
    symbol = Column(String, unique=True, nullable=False)
    alert_high = Column(Float)
    alert_low = Column(Float)

Base.metadata.create_all(engine)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head><title>Stock Tracker</title></head>
<body>
    <h1>Stock Watchlist</h1>
    <form action="/add" method="post">
        <input type="text" name="symbol" placeholder="AAPL" required>
        <input type="number" step="0.01" name="high" placeholder="High Alert">
        <input type="number" step="0.01" name="low" placeholder="Low Alert">
        <button type="submit">Add</button>
    </form>
    <ul>
    {% for stock in stocks %}
        <li>{{ stock.symbol }} - Current: ${{ stock.price }} 
            <a href="/remove/{{ stock.symbol }}">[Remove]</a>
            <div>{{ stock.chart | safe }}</div>
        </li>
    {% endfor %}
    </ul>
</body>
</html>
"""

def get_stock_data(symbol: str) -> Dict:
    """Fetch current price and historical data."""
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="1mo")
        if hist.empty:
            return {"price": 0, "chart": ""}
        
        current_price = hist['Close'].iloc[-1]
        
        # Check alerts
        session = Session()
        stock = session.query(Watchlist).filter_by(symbol=symbol).first()
        if stock:
            if stock.alert_high and current_price > stock.alert_high:
                logging.warning(f"ALERT: {symbol} crossed high threshold {stock.alert_high}")
            if stock.alert_low and current_price < stock.alert_low:
                logging.warning(f"ALERT: {symbol} crossed low threshold {stock.alert_low}")
        session.close()
        
        # Create chart
        fig = px.line(hist, x=hist.index, y='Close', title=f"{symbol} Price")
        chart_json = plotly.io.to_html(fig, full_html=False)
        
        return {"price": round(current_price, 2), "chart": chart_json}
    except Exception as e:
        logging.error(f"Error fetching {symbol}: {e}")
        return {"price": 0, "chart": "<p>Error loading chart</p>"}

@app.route('/')
def index():
    session = Session()
    stocks = session.query(Watchlist).all()
    stock_data = []
    for s in stocks:
        data = get_stock_data(s.symbol)
        stock_data.append({"symbol": s.symbol, "price": data["price"], "chart": data["chart"]})
    session.close()
    return render_template_string(HTML_TEMPLATE, stocks=stock_data)

@app.route('/add', methods=['POST'])
def add_stock():
    symbol = request.form.get('symbol', '').upper()
    high = request.form.get('high')
    low = request.form.get('low')
    
    if not symbol:
        return jsonify({"error": "Symbol required"}), 400
        
    session = Session()
    if not session.query(Watchlist).filter_by(symbol=symbol).first():
        stock = Watchlist(
            symbol=symbol,
            alert_high=float(high) if high else None,
            alert_low=float(low) if low else None
        )
        session.add(stock)
        session.commit()
    session.close()
    return jsonify({"message": "Added"}), 201

@app.route('/remove/<symbol>')
def remove_stock(symbol: str):
    session = Session()
    session.query(Watchlist).filter_by(symbol=symbol).delete()
    session.commit()
    session.close()
    return jsonify({"message": "Removed"}), 200

if __name__ == '__main__':
    app.run(debug=True, port=5000)