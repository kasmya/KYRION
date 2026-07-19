"""
ETL Pipeline with Apache Airflow for weather and news data processing.

Features:
- Extract from REST APIs (weather, news)
- Transform (clean, aggregate, merge)
- Load into SQLite warehouse
- Scheduled DAG execution
- Error handling and logging
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import json
import sqlite3
from pathlib import Path

import pandas as pd
import numpy as np
import requests
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.email import EmailOperator
from airflow.models import Variable
from airflow.utils.dates import days_ago

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
DATA_DIR = Path(os.getenv('AIRFLOW_DATA_DIR', '/tmp/etl_data'))
DATA_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_URL = os.getenv('WAREHOUSE_URL', 'sqlite:///warehouse.db')

# API Configuration
WEATHER_API_KEY = os.getenv('WEATHER_API_KEY', 'your-api-key')
NEWS_API_KEY = os.getenv('NEWS_API_KEY', 'your-api-key')

class DataExtractor:
    """Handles data extraction from various sources."""
    
    def __init__(self):
        """Initialize extractor with API configurations."""
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'ETL-Pipeline/1.0'
        })
    
    def extract_weather_data(self, cities: List[str]) -> pd.DataFrame:
        """
        Extract weather data for given cities.
        
        Args:
            cities: List of city names
            
        Returns:
            DataFrame with weather data
        """
        weather_data = []
        
        for city in cities:
            try:
                # Using OpenWeatherMap API (stub with sample data)
                # In production, uncomment the API call:
                # response = self.session.get(
                #     f'http://api.openweathermap.org/data/2.5/weather',
                #     params={'q': city, 'appid': WEATHER_API_KEY, 'units': 'metric'}
                # )
                # response.raise_for_status()
                # data = response.json()
                
                # Sample data for demonstration
                data = {
                    'city': city,
                    'temperature': np.random.uniform(-5, 35),
                    'humidity': np.random.uniform(30, 90),
                    'pressure': np.random.uniform(980, 1030),
                    'wind_speed': np.random.uniform(0, 20),
                    'description': np.random.choice(['Clear', 'Cloudy', 'Rain', 'Snow']),
                    'timestamp': datetime.now().isoformat()
                }
                
                weather_data.append(data)
                logger.info(f"Extracted weather data for {city}")
                
            except Exception as e:
                logger.error(f"Failed to extract weather data for {city}: {str(e)}")
                continue
        
        df = pd.DataFrame(weather_data)
        return df
    
    def extract_news_data(self, topics: List[str], num_articles: int = 10) -> pd.DataFrame:
        """
        Extract news articles for given topics.
        
        Args:
            topics: List of news topics
            num_articles: Number of articles per topic
            
        Returns:
            DataFrame with news articles
        """
        news_data = []
        
        for topic in topics:
            try:
                # Sample data for demonstration
                for i in range(num_articles):
                    article = {
                        'title': f"Sample article about {topic} - {i}",
                        'description': f"This is a description for article {i} about {topic}",
                        'source': np.random.choice(['Reuters', 'AP', 'BBC', 'CNN']),
                        'topic': topic,
                        'published_at': (datetime.now() - timedelta(hours=np.random.randint(1, 72))).isoformat(),
                        'url': f'https://example.com/news/{topic}/{i}',
                        'sentiment': np.random.choice(['positive', 'neutral', 'negative'])
                    }
                    news_data.append(article)
                
                logger.info(f"Extracted {num_articles} articles for topic: {topic}")
                
            except Exception as e:
                logger.error(f"Failed to extract news data for {topic}: {str(e)}")
                continue
        
        df = pd.DataFrame(news_data)
        return df

class DataTransformer:
    """Handles data transformation and cleaning."""
    
    @staticmethod
    def clean_weather_data(df: pd.DataFrame) -> pd.DataFrame:
        """
        Clean and transform weather data.
        
        Args:
            df: Raw weather DataFrame
            
        Returns:
            Cleaned DataFrame
        """
        try:
            # Remove duplicates
            df = df.drop_duplicates(subset=['city', 'timestamp'])
            
            # Handle missing values
            numeric_cols = ['temperature', 'humidity', 'pressure', 'wind_speed']
            df[numeric_cols] = df[numeric_cols].fillna(df[numeric_cols].mean())
            
            # Validate ranges
            df = df[
                (df['temperature'].between(-50, 60)) &
                (df['humidity'].between(0, 100)) &
                (df['pressure'].between(800, 1100))
            ]
            
            # Add derived columns
            df['feels_like'] = df['temperature'] - (df['wind_speed'] * 0.2)
            df['weather_category'] = pd.cut(
                df['temperature'],
                bins=[-float('inf'), 0, 10, 20, 30, float('inf')],
                labels=['Freezing', 'Cold', 'Mild', 'Warm', 'Hot']
            )
            
            # Parse timestamp
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df['date'] = df['timestamp'].dt.date
            df['hour'] = df['timestamp'].dt.hour
            
            logger.info(f"Weather data cleaned: {len(df)} records")
            
        except Exception as e:
            logger.error(f"Error cleaning weather data: {str(e)}", exc_info=True)
            raise
        
        return df
    
    @staticmethod
    def clean_news_data(df: pd.DataFrame) -> pd.DataFrame:
        """
        Clean and transform news data.
        
        Args:
            df: Raw news DataFrame
            
        Returns:
            Cleaned DataFrame
        """
        try:
            # Remove duplicates
            df = df.drop_duplicates(subset=['title'])
            
            # Clean text fields
            df['title'] = df['title'].str.strip()
            df['description'] = df['description'].str.strip()
            
            # Parse dates
            df['published_at'] = pd.to_datetime(df['published_at'])
            df['date'] = df['published_at'].dt.date
            df['day_of_week'] = df['published_at'].dt.day_name()
            
            # Add derived columns
            df['title_length'] = df['title'].str.len()
            df['description_length'] = df['description'].str.len()
            
            # Sentiment encoding
            sentiment_map = {'positive': 1, 'neutral': 0, 'negative': -1}
            df['sentiment_score'] = df['sentiment'].map(sentiment_map)
            
            logger.info(f"News data cleaned: {len(df)} records")
            
        except Exception as e:
            logger.error(f"Error cleaning news data: {str(e)}", exc_info=True)
            raise
        
        return df
    
    @staticmethod
    def aggregate_weather_data(df: pd.DataFrame) -> pd.DataFrame:
        """
        Aggregate weather data for reporting.
        
        Args:
            df: Cleaned weather DataFrame
            
        Returns:
            Aggregated DataFrame
        """
        try:
            agg_df = df.groupby(['city', 'date']).agg({
                'temperature': ['mean', 'min', 'max'],
                'humidity': 'mean',
                'wind_speed': 'mean',
                'pressure': 'mean'
            }).round(2)
            
            # Flatten column names
            agg_df.columns = ['_'.join(col).strip() for col in agg_df.columns.values]
            agg_df = agg_df.reset_index()
            
            logger.info(f"Weather data aggregated: {len(agg_df)} groups")
            return agg_df
            
        except Exception as e:
            logger.error(f"Error aggregating weather data: {str(e)}")
            raise

class DataLoader:
    """Handles loading data into the warehouse."""
    
    def __init__(self, database_url: str):
        """
        Initialize loader with database connection.
        
        Args:
            database_url: SQLAlchemy database URL
        """
        self.engine = create_engine(database_url)
        self.Session = sessionmaker(bind=self.engine)
    
    def create_tables(self) -> None:
        """Create warehouse tables if they don't exist."""
        with self.engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS weather_data (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    city TEXT NOT NULL,
                    temperature REAL,
                    humidity REAL,
                    pressure REAL,
                    wind_speed REAL,
                    description TEXT,
                    timestamp DATETIME NOT NULL,
                    date DATE,
                    hour INTEGER,
                    feels_like REAL,
                    weather_category TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(city, timestamp)
                )
            """))
            
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS news_data (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    description TEXT,
                    source TEXT,
                    topic TEXT,
                    published_at DATETIME NOT NULL,
                    url TEXT,
                    sentiment TEXT,
                    date DATE,
                    day_of_week TEXT,
                    title_length INTEGER,
                    description_length INTEGER,
                    sentiment_score INTEGER,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(title, source)
                )
            """))
            
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS weather_aggregations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    city TEXT NOT NULL,
                    date DATE NOT NULL,
                    temperature_mean REAL,
                    temperature_min REAL,
                    temperature_max REAL,
                    humidity_mean REAL,
                    wind_speed_mean REAL,
                    pressure_mean REAL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(city, date)
                )
            """))
            
            conn.commit()
            logger.info("Warehouse tables created")
    
    def load_dataframe(self, df: pd.DataFrame, table_name: str, if_exists: str = 'append') -> None:
        """
        Load DataFrame into warehouse table.
        
        Args:
            df: DataFrame to load
            table_name: Target table name
            if_exists: How to handle existing data
        """
        try:
            df.to_sql(
                table_name,
                self.engine,
                if_exists=if_exists,
                index=False,
                method='multi',
                chunksize=1000
            )
            logger.info(f"Loaded {len(df)} records into {table_name}")
            
        except Exception as e:
            logger.error(f"Error loading data to {table_name}: {str(e)}")
            raise

# Airflow DAG definition
default_args = {
    'owner': 'data_team',
    'depends_on_past': False,
    'email_on_failure': True,
    'email_on_retry': False,
    'email': ['alerts@example.com'],
    'retries': 3,
    'retry_delay': timedelta(minutes=5),
    'start_date': days_ago(1),
}

dag = DAG(
    'etl_pipeline',
    default_args=default_args,
    description='ETL Pipeline for Weather and News Data',
    schedule_interval='0 */6 * * *',  # Every 6 hours
    catchup=False,
    tags=['etl', 'weather', 'news'],
)

def extract_data(**context) -> Dict[str, str]:
    """
    Extract data from APIs.
    
    Returns:
        Dictionary with file paths of extracted data
    """
    extractor = DataExtractor()
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    # Extract weather data
    cities = ['London', 'New York', 'Tokyo', 'Sydney', 'Mumbai']
    weather_df = extractor.extract_weather_data(cities)
    weather_path = DATA_DIR / f'weather_{timestamp}.csv'
    weather_df.to_csv(weather_path, index=False)
    
    # Extract news data
    topics = ['technology', 'business', 'science', 'health', 'sports']
    news_df = extractor.extract_news_data(topics)
    news_path = DATA_DIR / f'news_{timestamp}.csv'
    news_df.to_csv(news_path, index=False)
    
    logger.info(f"Data extracted successfully")
    
    context['task_instance'].xcom_push(key='weather_path', value=str(weather_path))
    context['task_instance'].xcom_push(key='news_path', value=str(news_path))
    
    return {
        'weather_path': str(weather_path),
        'news_path': str(news_path)
    }

def transform_data(**context) -> Dict[str, str]:
    """
    Transform extracted data.
    
    Returns:
        Dictionary with file paths of transformed data
    """
    ti = context['task_instance']
    
    # Get file paths from extraction
    weather_path = ti.xcom_pull(task_ids='extract_data', key='weather_path')
    news_path = ti.xcom_pull(task_ids='extract_data', key='news_path')
    
    transformer = DataTransformer()
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    # Transform weather data
    weather_df = pd.read_csv(weather_path)
    weather_cleaned = transformer.clean_weather_data(weather_df)
    weather_aggregated = transformer.aggregate_weather_data(weather_cleaned)
    
    weather_clean_path = DATA_DIR / f'weather_clean_{timestamp}.csv'
    weather_agg_path = DATA_DIR / f'weather_agg_{timestamp}.csv'
    weather_cleaned.to_csv(weather_clean_path, index=False)
    weather_aggregated.to_csv(weather_agg_path, index=False)
    
    # Transform news data
    news_df = pd.read_csv(news_path)
    news_cleaned = transformer.clean_news_data(news_df)
    news_clean_path = DATA_DIR / f'news_clean_{timestamp}.csv'
    news_cleaned.to_csv(news_clean_path, index=False)
    
    logger.info("Data transformation completed")
    
    ti.xcom_push(key='weather_clean_path', value=str(weather_clean_path))
    ti.xcom_push(key='weather_agg_path', value=str(weather_agg_path))
    ti.xcom_push(key='news_clean_path', value=str(news_clean_path))
    
    return {
        'weather_clean_path': str(weather_clean_path),
        'weather_agg_path': str(weather_agg_path),
        'news_clean_path': str(news_clean_path)
    }

def load_data(**context) -> None:
    """Load transformed data into warehouse."""
    ti = context['task_instance']
    
    # Get file paths from transformation
    weather_clean_path = ti.xcom_pull(task_ids='transform_data', key='weather_clean_path')
    weather_agg_path = ti.xcom_pull(task_ids='transform_data', key='weather_agg_path')
    news_clean_path = ti.xcom_pull(task_ids='transform_data', key='news_clean_path')
    
    loader = DataLoader(DATABASE_URL)
    loader.create_tables()
    
    # Load weather data
    weather_df = pd.read_csv(weather_clean_path)
    loader.load_dataframe(weather_df, 'weather_data')
    
    # Load weather aggregations
    weather_agg_df = pd.read_csv(weather_agg_path)
    loader.load_dataframe(weather_agg_df, 'weather_aggregations')
    
    # Load news data
    news_df = pd.read_csv(news_clean_path)
    loader.load_dataframe(news_df, 'news_data')
    
    logger.info("Data loading completed")

def validate_data(**context) -> Dict[str, Any]:
    """
    Validate loaded data quality.
    
    Returns:
        Validation metrics
    """
    engine = create_engine(DATABASE_URL)
    
    validation_results = {}
    
    with engine.connect() as conn:
        # Check row counts
        weather_count = conn.execute(text("SELECT COUNT(*) FROM weather_data")).scalar()
        news_count = conn.execute(text("SELECT COUNT(*) FROM news_data")).scalar()
        agg_count = conn.execute(text("SELECT COUNT(*) FROM weather_aggregations")).scalar()
        
        validation_results['row_counts'] = {
            'weather_data': weather_count,
            'news_data': news_count,
            'weather_aggregations': agg_count
        }
        
        # Check for nulls in critical columns
        weather_nulls = conn.execute(text(
            "SELECT COUNT(*) FROM weather_data WHERE temperature IS NULL OR city IS NULL"
        )).scalar()
        
        validation_results['data_quality'] = {
            'weather_null_critical': weather_nulls,
            'passed': weather_nulls == 0
        }
    
    if validation_results['data_quality']['passed']:
        logger.info("Data validation passed")
    else:
        logger.error("Data validation failed")
    
    return validation_results

# Define tasks
extract_task = PythonOperator(
    task_id='extract_data',
    python_callable=extract_data,
    dag=dag,
)

transform_task = PythonOperator(
    task_id='transform_data',
    python_callable=transform_data,
    dag=dag,
)

load_task = PythonOperator(
    task_id='load_data',
    python_callable=load_data,
    dag=dag,
)

validate_task = PythonOperator(
    task_id='validate_data',
    python_callable=validate_data,
    dag=dag,
)

# Set task dependencies
extract_task >> transform_task >> load_task >> validate_task
