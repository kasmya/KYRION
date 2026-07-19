"""
ETL Pipeline using Airflow and Pandas.
Features:
- Extract from REST APIs (weather, news)
- Transform (clean, aggregate, merge)
- Load into SQLite warehouse
- Schedule with Airflow DAG
"""

import requests
import pandas as pd
import sqlite3
import logging
from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO)

DB_FILE = "warehouse.db"


def extract_weather() -> pd.DataFrame:
    """Extract weather data from API (stubbed)."""
    logging.info("Extracting weather data...")
    # Stubbed API response
    data = [{"city": "Delhi", "temp": 35}, {"city": "Mumbai", "temp": 30}]
    return pd.DataFrame(data)


def extract_news() -> pd.DataFrame:
    """Extract news data from API (stubbed)."""
    logging.info("Extracting news data...")
    data = [{"headline": "Market up", "category": "Business"}, {"headline": "Rain expected", "category": "Weather"}]
    return pd.DataFrame(data)


def transform(**context) -> pd.DataFrame:
    """Transform and merge extracted data."""
    weather = context["ti"].xcom_pull(task_ids="extract_weather")
    news = context["ti"].xcom_pull(task_ids="extract_news")
    df_weather = pd.DataFrame(weather)
    df_news = pd.DataFrame(news)
    df_weather["source"] = "weather"
    df_news["source"] = "news"
    combined = pd.concat([df_weather, df_news], ignore_index=True)
    logging.info("Transformation complete")
    return combined


def load(**context) -> None:
    """Load transformed data into SQLite warehouse."""
    combined = context["ti"].xcom_pull(task_ids="transform")
    df = pd.DataFrame(combined)
    conn = sqlite3.connect(DB_FILE)
    df.to_sql("etl_data", conn, if_exists="append", index=False)
    conn.close()
    logging.info("Data loaded into warehouse")


# Airflow DAG
default_args = {"owner": "airflow", "start_date": datetime(2024, 1, 1)}
dag = DAG("etl_pipeline", default_args=default_args, schedule_interval="@daily", catchup=False)

extract_weather_task = PythonOperator(task_id="extract_weather", python_callable=lambda: extract_weather().to_dict("records"), dag=dag)
extract_news_task = PythonOperator(task_id="extract_news", python_callable=lambda: extract_news().to_dict("records"), dag=dag)
transform_task = PythonOperator(task_id="transform", python_callable=transform, provide_context=True, dag=dag)
load_task = PythonOperator(task_id="load", python_callable=load, provide_context=True, dag=dag)

extract_weather_task >> extract_news_task >> transform_task >> load_task

