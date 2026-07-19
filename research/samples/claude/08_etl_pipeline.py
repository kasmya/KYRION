"""
### Task 8: ETL Pipeline (Airflow + Pandas)

An Airflow DAG that extracts data from REST APIs (weather and news),
transforms/cleans/merges it with Pandas, and loads the result into a
SQLite data warehouse. Designed to be dropped into an Airflow `dags/`
folder.

Requirements:
    pip install apache-airflow pandas requests sqlalchemy

Deploy:
    Copy this file into your Airflow DAGs folder; Airflow will pick it
    up automatically (DAG id: "api_etl_pipeline").
"""

from __future__ import annotations

import logging
import os
import sqlite3
from datetime import datetime, timedelta
from typing import Any, Dict, List

import pandas as pd
import requests
from airflow import DAG
from airflow.operators.python import PythonOperator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("etl_pipeline")

WAREHOUSE_DB_PATH = os.environ.get("ETL_WAREHOUSE_DB", "warehouse.db")
WEATHER_API_URL = "https://api.open-meteo.com/v1/forecast"
WEATHER_PARAMS = {"latitude": 51.5074, "longitude": -0.1278, "current_weather": True}
NEWS_API_URL = os.environ.get("NEWS_API_URL", "https://newsapi.org/v2/top-headlines")
NEWS_API_KEY = os.environ.get("NEWS_API_KEY", "")

REQUEST_TIMEOUT = 15

default_args = {
    "owner": "data-engineering",
    "retries": 3,
    "retry_delay": timedelta(minutes=5),
    "email_on_failure": False,
}


class ETLError(Exception):
    """Raised when an ETL stage fails in a way that should halt the pipeline."""


def extract_weather(**_context: Any) -> Dict[str, Any]:
    """Extracts current weather data from the Open-Meteo API."""
    try:
        response = requests.get(WEATHER_API_URL, params=WEATHER_PARAMS, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        data = response.json()
        logger.info("Extracted weather data: %s", data.get("current_weather"))
        return data
    except requests.RequestException as exc:
        logger.error("Failed to extract weather data: %s", exc)
        raise ETLError(f"weather extraction failed: {exc}") from exc


def extract_news(**_context: Any) -> List[Dict[str, Any]]:
    """Extracts top news headlines from a news API (requires NEWS_API_KEY)."""
    if not NEWS_API_KEY:
        logger.warning("NEWS_API_KEY not set; returning empty news list")
        return []

    try:
        response = requests.get(
            NEWS_API_URL,
            params={"country": "us", "apiKey": NEWS_API_KEY, "pageSize": 20},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        articles = response.json().get("articles", [])
        logger.info("Extracted %d news article(s)", len(articles))
        return articles
    except requests.RequestException as exc:
        logger.error("Failed to extract news data: %s", exc)
        raise ETLError(f"news extraction failed: {exc}") from exc


def transform_data(**context: Any) -> Dict[str, str]:
    """Cleans, aggregates, and merges weather and news data into warehouse-ready tables."""
    ti = context["ti"]
    weather_raw = ti.xcom_pull(task_ids="extract_weather")
    news_raw = ti.xcom_pull(task_ids="extract_news")

    if not weather_raw:
        raise ETLError("no weather data available to transform")

    current = weather_raw.get("current_weather", {})
    weather_df = pd.DataFrame(
        [
            {
                "recorded_at": current.get("time"),
                "temperature_c": current.get("temperature"),
                "windspeed_kmh": current.get("windspeed"),
                "weathercode": current.get("weathercode"),
                "ingested_at": datetime.utcnow().isoformat(),
            }
        ]
    )
    weather_df = weather_df.dropna(subset=["recorded_at"])

    news_df = pd.DataFrame(news_raw or [])
    if not news_df.empty:
        news_df = news_df.drop_duplicates(subset=["title"])
        news_df = news_df[["title", "source", "publishedAt", "url"]].copy()
        news_df["source"] = news_df["source"].apply(
            lambda s: s.get("name") if isinstance(s, dict) else s
        )
        news_df["ingested_at"] = datetime.utcnow().isoformat()
    else:
        news_df = pd.DataFrame(columns=["title", "source", "publishedAt", "url", "ingested_at"])

    weather_path = "/tmp/transformed_weather.csv"
    news_path = "/tmp/transformed_news.csv"
    weather_df.to_csv(weather_path, index=False)
    news_df.to_csv(news_path, index=False)

    logger.info(
        "Transformed data: %d weather row(s), %d news row(s)", len(weather_df), len(news_df)
    )
    return {"weather_path": weather_path, "news_path": news_path}


def load_to_warehouse(**context: Any) -> None:
    """Loads transformed CSVs into the SQLite warehouse database."""
    ti = context["ti"]
    paths = ti.xcom_pull(task_ids="transform_data")
    if not paths:
        raise ETLError("no transformed data paths available to load")

    try:
        weather_df = pd.read_csv(paths["weather_path"])
        news_df = pd.read_csv(paths["news_path"])
    except (OSError, pd.errors.ParserError) as exc:
        raise ETLError(f"failed to read transformed data: {exc}") from exc

    try:
        with sqlite3.connect(WAREHOUSE_DB_PATH) as conn:
            weather_df.to_sql("weather_snapshots", conn, if_exists="append", index=False)
            news_df.to_sql("news_headlines", conn, if_exists="append", index=False)
            conn.commit()
    except sqlite3.Error as exc:
        raise ETLError(f"failed to load data into warehouse: {exc}") from exc

    logger.info(
        "Loaded %d weather row(s) and %d news row(s) into '%s'",
        len(weather_df),
        len(news_df),
        WAREHOUSE_DB_PATH,
    )


with DAG(
    dag_id="api_etl_pipeline",
    default_args=default_args,
    description="Extract weather/news APIs, transform with Pandas, load into SQLite warehouse.",
    schedule_interval="@hourly",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["etl", "weather", "news"],
) as dag:

    extract_weather_task = PythonOperator(
        task_id="extract_weather",
        python_callable=extract_weather,
    )

    extract_news_task = PythonOperator(
        task_id="extract_news",
        python_callable=extract_news,
    )

    transform_task = PythonOperator(
        task_id="transform_data",
        python_callable=transform_data,
    )

    load_task = PythonOperator(
        task_id="load_to_warehouse",
        python_callable=load_to_warehouse,
    )

    [extract_weather_task, extract_news_task] >> transform_task >> load_task
