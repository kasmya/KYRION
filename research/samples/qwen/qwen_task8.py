"""Airflow ETL Pipeline extracting from APIs, transforming, and loading to SQLite."""
import logging
import pandas as pd
import requests
from sqlalchemy import create_engine
from datetime import datetime
from airflow import DAG
from airflow.operators.python import PythonOperator

logging.basicConfig(level=logging.INFO)
SQLITE_URL = "sqlite:///warehouse.db"
engine = create_engine(SQLITE_URL)

def extract_weather(**kwargs):
    """Extract weather data from Open-Meteo API."""
    url = "https://api.open-meteo.com/v1/forecast?latitude=52.52&longitude=13.41&current_weather=true"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()['current_weather']
        kwargs['ti'].xcom_push(key='weather', value=data)
        logging.info("Extracted weather data")
    except Exception as e:
        logging.error(f"Extraction failed: {e}")
        raise

def extract_news(**kwargs):
    """Extract mock news data."""
    # Using a mock structure since NewsAPI requires a key
    news_data = [
        {"title": "Tech News 1", "category": "Tech", "date": datetime.now().isoformat()},
        {"title": "Tech News 2", "category": "Tech", "date": datetime.now().isoformat()}
    ]
    kwargs['ti'].xcom_push(key='news', value=news_data)
    logging.info("Extracted news data")

def transform(**kwargs):
    """Clean and merge data."""
    ti = kwargs['ti']
    weather = ti.xcom_pull(task_ids='extract_weather', key='weather')
    news = ti.xcom_pull(task_ids='extract_news', key='news')
    
    # Transform weather
    weather_df = pd.DataFrame([weather])
    weather_df['timestamp'] = datetime.now()
    weather_df = weather_df.rename(columns={'temperature': 'temp_c'})
    
    # Transform news
    news_df = pd.DataFrame(news)
    news_df = news_df.drop_duplicates(subset=['title'])
    
    ti.xcom_push(key='weather_df', value=weather_df.to_dict('records'))
    ti.xcom_push(key='news_df', value=news_df.to_dict('records'))
    logging.info("Transformation complete")

def load(**kwargs):
    """Load data into SQLite warehouse."""
    ti = kwargs['ti']
    weather_data = ti.xcom_pull(task_ids='transform', key='weather_df')
    news_data = ti.xcom_pull(task_ids='transform', key='news_df')
    
    weather_df = pd.DataFrame(weather_data)
    news_df = pd.DataFrame(news_data)
    
    try:
        weather_df.to_sql('weather', engine, if_exists='append', index=False)
        news_df.to_sql('news', engine, if_exists='append', index=False)
        logging.info("Data loaded to SQLite")
    except Exception as e:
        logging.error(f"Load failed: {e}")
        raise

default_args = {'owner': 'airflow', 'start_date': datetime(2023, 1, 1), 'retries': 1}

with DAG('etl_pipeline', default_args=default_args, schedule_interval='@daily', catchup=False) as dag:
    t1 = PythonOperator(task_id='extract_weather', python_callable=extract_weather)
    t2 = PythonOperator(task_id='extract_news', python_callable=extract_news)
    t3 = PythonOperator(task_id='transform', python_callable=transform)
    t4 = PythonOperator(task_id='load', python_callable=load)
    
    [t1, t2] >> t3 >> t4