"""
Stock Price Tracker with watchlist management and price alerts.

Features:
- Add/remove stocks to watchlist
- Display current price and historical charts
- Price threshold alerts
- User authentication
- Real-time data from Yahoo Finance
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import json
from threading import Thread
import time

from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, jsonify, session
)
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager, UserMixin, login_user, logout_user,
    login_required, current_user
)
from werkzeug.security import generate_password_hash, check_password_hash
import yfinance as yf
import plotly.graph_objs as go
import plotly.utils
import pandas as pd
import numpy as np

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('stock_tracker.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-change-me')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///stocks.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize extensions
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Database Models
class User(UserMixin, db.Model):
    """User model for authentication."""
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    watchlist = db.relationship('WatchlistItem', backref='user', lazy=True)
    alerts = db.relationship('PriceAlert', backref='user', lazy=True)
    
    def set_password(self, password: str) -> None:
        """Hash and set password."""
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password: str) -> bool:
        """Verify password."""
        return check_password_hash(self.password_hash, password)

class WatchlistItem(db.Model):
    """Stock watchlist item."""
    __tablename__ = 'watchlist'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    symbol = db.Column(db.String(10), nullable=False)
    added_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    __table_args__ = (db.UniqueConstraint('user_id', 'symbol'),)

class PriceAlert(db.Model):
    """Price alert configuration."""
    __tablename__ = 'alerts'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    symbol = db.Column(db.String(10), nullable=False)
    threshold_price = db.Column(db.Float, nullable=False)
    direction = db.Column(db.String(10), nullable=False)  # 'above' or 'below'
    is_active = db.Column(db.Boolean, default=True)
    triggered = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    triggered_at = db.Column(db.DateTime, nullable=True)

@login_manager.user_loader
def load_user(user_id: int) -> Optional[User]:
    """Load user by ID."""
    return User.query.get(int(user_id))

class StockDataFetcher:
    """Fetches stock data from Yahoo Finance."""
    
    @staticmethod
    def get_current_price(symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get current stock price and info.
        
        Args:
            symbol: Stock symbol
            
        Returns:
            Dictionary with stock information
        """
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info
            
            # Get current price
            current_price = info.get('currentPrice') or info.get('regularMarketPrice')
            
            if not current_price:
                # Try to get from history
                hist = ticker.history(period='1d')
                if not hist.empty:
                    current_price = hist['Close'].iloc[-1]
            
            return {
                'symbol': symbol.upper(),
                'name': info.get('longName', info.get('shortName', symbol)),
                'price': current_price,
                'change': info.get('regularMarketChange'),
                'change_percent': info.get('regularMarketChangePercent'),
                'volume': info.get('regularMarketVolume'),
                'market_cap': info.get('marketCap'),
                'pe_ratio': info.get('trailingPE'),
                '52_week_high': info.get('fiftyTwoWeekHigh'),
                '52_week_low': info.get('fiftyTwoWeekLow'),
                'currency': info.get('currency', 'USD'),
                'exchange': info.get('exchange', 'Unknown'),
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error fetching data for {symbol}: {str(e)}")
            return None
    
    @staticmethod
    def get_historical_data(
        symbol: str,
        period: str = '1mo',
        interval: str = '1d'
    ) -> Optional[pd.DataFrame]:
        """
        Get historical stock data.
        
        Args:
            symbol: Stock symbol
            period: Time period (1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max)
            interval: Data interval (1m, 2m, 5m, 15m, 30m, 60m, 90m, 1h, 1d, 5d, 1wk, 1mo, 3mo)
            
        Returns:
            DataFrame with historical data
        """
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period=period, interval=interval)
            
            if hist.empty:
                return None
            
            return hist
            
        except Exception as e:
            logger.error(f"Error fetching history for {symbol}: {str(e)}")
            return None
    
    @staticmethod
    def create_price_chart(
        df: pd.DataFrame,
        symbol: str,
        chart_type: str = 'line'
    ) -> Optional[str]:
        """
        Create Plotly chart from historical data.
        
        Args:
            df: Historical data DataFrame
            symbol: Stock symbol
            chart_type: Chart type ('line' or 'candlestick')
            
        Returns:
            JSON string of Plotly chart
        """
        try:
            if chart_type == 'candlestick':
                fig = go.Figure(data=[go.Candlestick(
                    x=df.index,
                    open=df['Open'],
                    high=df['High'],
                    low=df['Low'],
                    close=df['Close'],
                    name=symbol
                )])
            else:
                fig = go.Figure()
                
                # Add price line
                fig.add_trace(go.Scatter(
                    x=df.index,
                    y=df['Close'],
                    mode='lines',
                    name='Close Price',
                    line=dict(color='#17BECF', width=2)
                ))
                
                # Add volume bars
                fig.add_trace(go.Bar(
                    x=df.index,
                    y=df['Volume'],
                    name='Volume',
                    yaxis='y2',
                    marker=dict(color='rgba(128, 128, 128, 0.5)')
                ))
            
            # Update layout
            fig.update_layout(
                title=f'{symbol} Stock Price',
                xaxis_title='Date',
                yaxis_title='Price',
                template='plotly_dark',
                hovermode='x unified',
                height=600,
                margin=dict(l=50, r=50, t=50, b=50),
                yaxis2=dict(
                    title='Volume',
                    overlaying='y',
                    side='right',
                    showgrid=False
                )
            )
            
            return json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)
            
        except Exception as e:
            logger.error(f"Error creating chart: {str(e)}")
            return None

class AlertChecker:
    """Background thread for checking price alerts."""
    
    def __init__(self, app):
        """
        Initialize alert checker.
        
        Args:
            app: Flask application instance
        """
        self.app = app
        self.running = False
        self.thread = None
    
    def start(self) -> None:
        """Start background alert checking."""
        if not self.running:
            self.running = True
            self.thread = Thread(target=self._check_alerts_loop, daemon=True)
            self.thread.start()
            logger.info("Alert checker started")
    
    def stop(self) -> None:
        """Stop background alert checking."""
        self.running = False
        logger.info("Alert checker stopped")
    
    def _check_alerts_loop(self) -> None:
        """Main alert checking loop."""
        while self.running:
            try:
                with self.app.app_context():
                    self._check_alerts()
            except Exception as e:
                logger.error(f"Alert check error: {str(e)}")
            
            time.sleep(60)  # Check every minute
    
    def _check_alerts(self) -> None:
        """Check all active alerts."""
        active_alerts = PriceAlert.query.filter_by(
            is_active=True, triggered=False
        ).all()
        
        for alert in active_alerts:
            stock_data = StockDataFetcher.get_current_price(alert.symbol)
            
            if stock_data and stock_data['price']:
                current_price = stock_data['price']
                
                should_trigger = False
                
                if alert.direction == 'above' and current_price >= alert.threshold_price:
                    should_trigger = True
                elif alert.direction == 'below' and current_price <= alert.threshold_price:
                    should_trigger = True
                
                if should_trigger:
                    alert.triggered = True
                    alert.triggered_at = datetime.utcnow()
                    db.session.commit()
                    
                    logger.info(
                        f"Alert triggered: {alert.symbol} {alert.direction} "
                        f"${alert.threshold_price} (current: ${current_price})"
                    )

# Routes
@app.route('/')
def index():
    """Home page."""
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    """User registration."""
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        if not all([username, email, password, confirm_password]):
            flash('All fields are required', 'danger')
            return render_template('register.html')
        
        if password != confirm_password:
            flash('Passwords do not match', 'danger')
            return render_template('register.html')
        
        if User.query.filter_by(username=username).first():
            flash('Username already exists', 'danger')
            return render_template('register.html')
        
        if User.query.filter_by(email=email).first():
            flash('Email already registered', 'danger')
            return render_template('register.html')
        
        user = User(username=username, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        
        flash('Registration successful! Please login.', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    """User login."""
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            login_user(user)
            flash('Logged in successfully!', 'success')
            return redirect(url_for('dashboard'))
        
        flash('Invalid username or password', 'danger')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    """User logout."""
    logout_user()
    flash('Logged out successfully', 'info')
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    """User dashboard with watchlist."""
    watchlist = WatchlistItem.query.filter_by(user_id=current_user.id).all()
    alerts = PriceAlert.query.filter_by(user_id=current_user.id).all()
    
    return render_template('dashboard.html', watchlist=watchlist, alerts=alerts)

@app.route('/api/stock/<symbol>')
@login_required
def get_stock_data(symbol: str):
    """API endpoint to get stock data."""
    stock_data = StockDataFetcher.get_current_price(symbol)
    
    if stock_data:
        return jsonify(stock_data)
    
    return jsonify({'error': 'Failed to fetch stock data'}), 404

@app.route('/api/stock/<symbol>/history')
@login_required
def get_stock_history(symbol: str):
    """API endpoint to get historical data and chart."""
    period = request.args.get('period', '1mo')
    chart_type = request.args.get('chart_type', 'line')
    
    hist_data = StockDataFetcher.get_historical_data(symbol, period)
    
    if hist_data is not None and not hist_data.empty:
        chart_json = StockDataFetcher.create_price_chart(hist_data, symbol, chart_type)
        
        return jsonify({
            'symbol': symbol,
            'chart': chart_json,
            'summary': {
                'open': hist_data['Open'].iloc[-1],
                'high': hist_data['High'].max(),
                'low': hist_data['Low'].min(),
                'close': hist_data['Close'].iloc[-1],
                'volume': hist_data['Volume'].sum(),
                'avg_volume': hist_data['Volume'].mean()
            }
        })
    
    return jsonify({'error': 'Failed to fetch historical data'}), 404

@app.route('/api/watchlist/add', methods=['POST'])
@login_required
def add_to_watchlist():
    """Add stock to watchlist."""
    data = request.get_json()
    symbol = data.get('symbol', '').upper().strip()
    
    if not symbol:
        return jsonify({'error': 'Symbol is required'}), 400
    
    # Check if already in watchlist
    existing = WatchlistItem.query.filter_by(
        user_id=current_user.id, symbol=symbol
    ).first()
    
    if existing:
        return jsonify({'error': 'Stock already in watchlist'}), 400
    
    # Verify stock exists
    stock_data = StockDataFetcher.get_current_price(symbol)
    if not stock_data:
        return jsonify({'error': 'Invalid stock symbol'}), 404
    
    watchlist_item = WatchlistItem(user_id=current_user.id, symbol=symbol)
    db.session.add(watchlist_item)
    db.session.commit()
    
    return jsonify({'message': f'{symbol} added to watchlist', 'stock': stock_data})

@app.route('/api/watchlist/remove/<symbol>', methods=['DELETE'])
@login_required
def remove_from_watchlist(symbol: str):
    """Remove stock from watchlist."""
    item = WatchlistItem.query.filter_by(
        user_id=current_user.id, symbol=symbol.upper()
    ).first()
    
    if not item:
        return jsonify({'error': 'Stock not in watchlist'}), 404
    
    db.session.delete(item)
    db.session.commit()
    
    return jsonify({'message': f'{symbol} removed from watchlist'})

@app.route('/api/alerts/create', methods=['POST'])
@login_required
def create_alert():
    """Create price alert."""
    data = request.get_json()
    symbol = data.get('symbol', '').upper().strip()
    threshold = float(data.get('threshold', 0))
    direction = data.get('direction', 'above')
    
    if not symbol or not threshold:
        return jsonify({'error': 'Symbol and threshold are required'}), 400
    
    if direction not in ['above', 'below']:
        return jsonify({'error': 'Direction must be above or below'}), 400
    
    alert = PriceAlert(
        user_id=current_user.id,
        symbol=symbol,
        threshold_price=threshold,
        direction=direction
    )
    db.session.add(alert)
    db.session.commit()
    
    return jsonify({'message': f'Alert created for {symbol}'})

@app.route('/api/alerts/<int:alert_id>/delete', methods=['DELETE'])
@login_required
def delete_alert(alert_id: int):
    """Delete price alert."""
    alert = PriceAlert.query.filter_by(
        id=alert_id, user_id=current_user.id
    ).first()
    
    if not alert:
        return jsonify({'error': 'Alert not found'}), 404
    
    db.session.delete(alert)
    db.session.commit()
    
    return jsonify({'message': 'Alert deleted'})

# HTML Templates
TEMPLATES = {
    'base.html': '''
<!DOCTYPE html>
<html>
<head>
    <title>{% block title %}Stock Tracker{% endblock %}</title>
    <style>
        body { font-family: Arial; margin: 0; padding: 20px; background: #1a1a2e; color: #eee; }
        .container { max-width: 1200px; margin: 0 auto; }
        nav { background: #16213e; padding: 15px; margin-bottom: 20px; border-radius: 8px; }
        nav a { color: #0f3460; text-decoration: none; margin-right: 20px; padding: 8px 15px; background: #e94560; border-radius: 5px; }
        .stock-card { background: #16213e; padding: 20px; margin: 10px 0; border-radius: 8px; }
        .price-up { color: #00ff88; }
        .price-down { color: #ff4444; }
        .alert { padding: 10px; margin: 10px 0; border-radius: 5px; }
        .alert-success { background: #00ff8822; color: #00ff88; }
        .alert-danger { background: #ff444422; color: #ff4444; }
        input, button { padding: 10px; margin: 5px; border: none; border-radius: 5px; }
        input { background: #0f3460; color: white; }
        button { background: #e94560; color: white; cursor: pointer; }
        table { width: 100%; border-collapse: collapse; margin: 20px 0; }
        th, td { padding: 12px; text-align: left; border-bottom: 1px solid #0f3460; }
        th { background: #0f3460; }
    </style>
</head>
<body>
    <nav>
        <a href="/">Home</a>
        {% if current_user.is_authenticated %}
            <a href="/dashboard">Dashboard</a>
            <a href="/logout">Logout</a>
        {% else %}
            <a href="/login">Login</a>
            <a href="/register">Register</a>
        {% endif %}
    </nav>
    <div class="container">
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                    <div class="alert alert-{{ category }}">{{ message }}</div>
                {% endfor %}
            {% endif %}
        {% endwith %}
        {% block content %}{% endblock %}
    </div>
    {% block scripts %}{% endblock %}
</body>
</html>
''',
    'index.html': '{% extends "base.html" %}\n{% block content %}<h1>Stock Price Tracker</h1><p>Track your favorite stocks and set price alerts.</p>{% endblock %}',
    'register.html': '''
{% extends "base.html" %}
{% block content %}
<h2>Register</h2>
<form method="POST">
    <input type="text" name="username" placeholder="Username" required><br>
    <input type="email" name="email" placeholder="Email" required><br>
    <input type="password" name="password" placeholder="Password" required><br>
    <input type="password" name="confirm_password" placeholder="Confirm Password" required><br>
    <button type="submit">Register</button>
</form>
{% endblock %}
''',
    'login.html': '''
{% extends "base.html" %}
{% block content %}
<h2>Login</h2>
<form method="POST">
    <input type="text" name="username" placeholder="Username" required><br>
    <input type="password" name="password" placeholder="Password" required><br>
    <button type="submit">Login</button>
</form>
{% endblock %}
''',
    'dashboard.html': '''
{% extends "base.html" %}
{% block content %}
<h2>Dashboard</h2>

<h3>Add Stock</h3>
<input type="text" id="symbolInput" placeholder="Enter stock symbol (e.g., AAPL)">
<button onclick="addToWatchlist()">Add to Watchlist</button>

<h3>Watchlist</h3>
<div id="watchlist"></div>

<h3>Price Alerts</h3>
<div id="alerts"></div>

<h3>Create Alert</h3>
<input type="text" id="alertSymbol" placeholder="Symbol">
<input type="number" id="alertPrice" placeholder="Price" step="0.01">
<select id="alertDirection">
    <option value="above">Above</option>
    <option value="below">Below</option>
</select>
<button onclick="createAlert()">Create Alert</button>

{% endblock %}
{% block scripts %}
<script>
async function loadWatchlist() {
    const response = await fetch('/api/watchlist');
    const data = await response.json();
    document.getElementById('watchlist').innerHTML = data.map(item => 
        `<div class="stock-card">
            <strong>${item.symbol}</strong>: $${item.price}
            <span class="${item.change >= 0 ? 'price-up' : 'price-down'}">
                ${item.change >= 0 ? '+' : ''}${item.change} (${item.change_percent}%)
            </span>
            <button onclick="removeFromWatchlist('${item.symbol}')">Remove</button>
        </div>`
    ).join('');
}

async function addToWatchlist() {
    const symbol = document.getElementById('symbolInput').value;
    const response = await fetch('/api/watchlist/add', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({symbol: symbol})
    });
    if (response.ok) {
        loadWatchlist();
        document.getElementById('symbolInput').value = '';
    }
}

function removeFromWatchlist(symbol) {
    fetch(`/api/watchlist/remove/${symbol}`, {method: 'DELETE'})
        .then(() => loadWatchlist());
}

async function createAlert() {
    const response = await fetch('/api/alerts/create', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            symbol: document.getElementById('alertSymbol').value,
            threshold: document.getElementById('alertPrice').value,
            direction: document.getElementById('alertDirection').value
        })
    });
    if (response.ok) location.reload();
}

setInterval(loadWatchlist, 30000);
loadWatchlist();
</script>
{% endblock %}
'''
}

def create_templates():
    """Create template files."""
    templates_dir = os.path.join(os.path.dirname(__file__), 'templates')
    os.makedirs(templates_dir, exist_ok=True)
    for filename, content in TEMPLATES.items():
        with open(os.path.join(templates_dir, filename), 'w') as f:
            f.write(content)

if __name__ == '__main__':
    create_templates()
    with app.app_context():
        db.create_all()
    
    # Start alert checker
    alert_checker = AlertChecker(app)
    alert_checker.start()
    
    app.run(debug=True, host='0.0.0.0', port=5002)
