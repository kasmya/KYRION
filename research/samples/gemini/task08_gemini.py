"""
Task 8: Production Airflow ETL Pipeline Data Warehouse Engine
Features: Resilient REST Extraction, Pandas normalizations, structured SQLite storage.
Requires: apache-airflow, pandas, requests, sqlalchemy
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Any, Dict
import pandas as pd
import requests
from sqlalchemy import create_engine

from airflow import DAG
from airflow.operators.python import PythonOperator

# --- Configuration & Environment Setup ---
DB_PATH = os.environ.get("ETL_WAREHOUSE_DB", "sqlite:////tmp/analytics_warehouse.db")
MOCK_API_ENDPOINT = "https://api.open-meteo.com/v1/forecast?latitude=52.52&longitude=13.41&current_weather=true"

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

default_args = {
    'owner': 'data_platform_engineering',
    'depends_on_past': False,
    'start_date': datetime(2026, 1, 1),
    'email_on_failure': False,
    'retries': 2,
    'retry_delay': timedelta(minutes=5),
}

# --- ETL Core Business Operations ---

def extract_metrics_layer(**kwargs: Any) -> Dict[str, Any]:
    """Queries external endpoints to pull transactional metrics."""
    logger.info(f"Querying external REST endpoint: {MOCK_API_ENDPOINT}")
    try:
        response = requests.get(MOCK_API_ENDPOINT, timeout=15)
        response.raise_for_status()
        payload = response.json()
        
        if "current_weather" not in payload:
            raise KeyError("Inbound REST packet missing core 'current_weather' json structural keys.")
            
        return payload["current_weather"]
    except requests.RequestException as net_err:
        logger.error(f"Network processing bottleneck encountered during ingest phase: {net_err}")
        raise

def transform_metrics_layer(**kwargs: Any) -> str:
    """Ingests raw tracking strings from XComs, structures and sanitizes records."""
    ti = kwargs['ti']
    raw_data: Dict[str, Any] = ti.xcom_pull(task_ids='extract_raw_metrics')
    
    if not raw_data:
        raise ValueError("XCom ingestion failure: no processing stream records fetched from upstream extractor.")
        
    logger.info("Starting Pandas transformation and column standardization routines.")
    
    # Cast to structured DataFrame for metric cleaning
    df = pd.DataFrame([raw_data])
    
    # Normalization mappings
    df['temperature_celsius'] = df['temperature'].astype(float)
    df['windspeed_kmh'] = df['windspeed'].astype(float)
    df['weather_condition_code'] = df['weathercode'].astype(int)
    df['ingested_at'] = datetime.utcnow()
    
    # Drop volatile raw original source keys
    df.drop(columns=['temperature', 'windspeed', 'weathercode', 'time'], errors='ignore', inplace=True)
    
    # Serialize clean structural text out to transient storage cache
    temp_csv_path = "/tmp/transformed_metrics_frame.csv"
    df.to_csv(temp_csv_path, index=False)
    logger.info(f"Transformation lifecycle pipeline complete. Buffered output route: {temp_csv_path}")
    return temp_csv_path

def load_metrics_warehouse(**kwargs: Any) -> None:
    """Loads transformed records into the target relational SQLite production analytical tables."""
    ti = kwargs['ti']
    csv_source_path: str = ti.xcom_pull(task_ids='transform_raw_metrics')
    
    if not os.path.exists(csv_source_path):
        raise FileNotFoundError(f"Missing persistent transformation segment storage asset: {csv_source_path}")
        
    logger.info(f"Initializing connection to target warehouse engine database: {DB_PATH}")
    engine = create_engine(DB_PATH)
    
    try:
        df = pd.read_csv(csv_source_path)
        with engine.begin() as relational_transaction:
            df.to_sql(
                name="fact_climate_telemetry",
                con=relational_transaction,
                if_exists="append",
                index=False
            )
        logger.info(f"Successfully loaded {len(df)} warehouse data records cleanly to storage blocks.")
    except Exception as db_err:
        logger.error(f"Critical relational transaction database failure across ingestion layer: {db_err}")
        raise
    finally:
        if os.path.exists(csv_source_path):
            os.remove(csv_source_path)

# --- Airflow Graph Workflow Bindings ---

with DAG(
    'enterprise_metrics_etl_pipeline',
    default_args=default_args,
    description='Automated hourly production metrics warehouse loading schedule pipeline',
    schedule_interval='@hourly',
    catchup=False,
) as dag:

    extract_task = PythonOperator(
        task_id='extract_raw_metrics',
        python_callable=extract_metrics_layer,
    )

    transform_task = PythonOperator(
        task_id='transform_raw_metrics',
        python_callable=transform_metrics_layer,
    )

    load_task = PythonOperator(
        task_id='load_metrics_warehouse',
        python_callable=load_metrics_warehouse,
    )

    # Establish sequence orchestration maps
    extract_task >> transform_task >> load_task
