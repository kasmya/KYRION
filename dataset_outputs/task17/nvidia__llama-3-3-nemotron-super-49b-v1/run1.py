import requests
import pandas as pd
from sqlalchemy import create_engine, Column, Integer, Float, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from typing import Tuple, List
import logging
import os
from datetime import datetime, timedelta

# Security Best Practice: Environment Variables for Sensitive Info
API_KEY = os.environ.get('STOCK_API_KEY')
DB_URI = os.environ.get('DATABASE_URI')

if not API_KEY or not DB_URI:
    raise RuntimeError("API_KEY and DB_URI environment variables must be set")

# Logging Setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database Setup
Base = declarative_base()

class StockPrice(Base):
    """Stock Price Historical Data Model"""
    __tablename__ = 'stock_prices'
    id = Column(Integer, primary_key=True)
    symbol = Column(Text)
    date = Column(Text)
    price = Column(Float)

    def __repr__(self):
        return f"StockPrice(symbol={self.symbol}, date={self.date}, price={self.price})"

engine = create_engine(DB_URI)
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)
session = Session()

def fetch_stock_price(symbol: str) -> float:
    """
    Fetch Real-Time Stock Price from API.

    Args:
    - symbol (str): Stock Symbol (e.g., AAPL)

    Returns:
    - float: Current Stock Price

    Raises:
    - requests.exceptions.RequestException: On API Failure
    """
    try:
        response = requests.get(f'https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol={symbol}&apikey={API_KEY}')
        response.raise_for_status()
        data = response.json()
        return float(data['Global Quote']['05. price'])
    except requests.exceptions.RequestException as e:
        logger.error(f"API Request Failed for {symbol}: {e}")
        raise

def store_historical_price(symbol: str, price: float) -> None:
    """
    Store Stock Price in Database.

    Args:
    - symbol (str): Stock Symbol
    - price (float): Stock Price to Store
    """
    new_price = StockPrice(symbol=symbol, date=datetime.utcnow().isoformat(), price=price)
    session.add(new_price)
    session.commit()

def calculate_moving_averages(symbol: str, days: List[int] = [7, 30]) -> Tuple[float, ...]:
    """
    Calculate Moving Averages for Given Days.

    Args:
    - symbol (str): Stock Symbol
    - days (List[int]): List of Days for Moving Averages (Default: [7, 30])

    Returns:
    - Tuple[float, ...]: Moving Averages for Given Days
    """
    # Query Database for Historical Prices
    prices = session.query(StockPrice).filter_by(symbol=symbol).order_by(StockPrice.date.desc()).all()
    price_list = [p.price for p in prices]
    
    # Calculate Moving Averages
    mas = []
    for day in days:
        if len(price_list) < day:
            mas.append(None)  # Not enough data for this MA
        else:
            ma = sum(price_list[:day]) / day
            mas.append(ma)
    return tuple(mas)

def generate_signals(symbol: str, short_ma: int = 7, long_ma: int = 30) -> str:
    """
    Generate Buy/Sell Signals Based on Moving Averages.

    Args:
    - symbol (str): Stock Symbol
    - short_ma (int): Short Moving Average Days (Default: 7)
    - long_ma (int): Long Moving Average Days (Default: 30)

    Returns:
    - str: "BUY" if short MA > long MA, "SELL" if short MA < long MA, "HOLD" if equal
    """
    try:
        mas = calculate_moving_averages(symbol, [short_ma, long_ma])
        short_ma, long_ma = mas
        if short_ma is None or long_ma is None:
            return "INSUFFICIENT_DATA"
        if short_ma > long_ma:
            return "BUY"
        elif short_ma < long_ma:
            return "SELL"
        else:
            return "HOLD"
    except Exception as e:
        logger.error(f"Error generating signal for {symbol}: {e}")
        return "ERROR"

def main():
    symbol = "AAPL"  # Example Symbol
    try:
        current_price = fetch_stock_price(symbol)
        logger.info(f"Current Price for {symbol}: {current_price}")
        store_historical_price(symbol, current_price)
        signal = generate_signals(symbol)
        logger.info(f"Signal for {symbol}: {signal}")
    except Exception as e:
        logger.error(f"Main Execution Failed: {e}")

if __name__ == "__main__":
    main()