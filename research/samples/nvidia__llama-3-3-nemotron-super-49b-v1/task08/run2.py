import csv
import logging
import os
import sqlite3
from datetime import datetime
from typing import Dict, List, Tuple

# Configure Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def extract_data(csv_file_path: str) -> Tuple[List[Dict[str, str]], None]:
    """
    Extracts data from a CSV file.

    Args:
    - csv_file_path (str): Path to the CSV file.

    Returns:
    - A tuple containing a list of dictionaries (each representing a row in the CSV)
      and None (for potential future use in returning an error object).
    """
    try:
        with open(csv_file_path, 'r') as file:
            csv_reader = csv.DictReader(file)
            data = [row for row in csv_reader]
            logger.info(f"Extracted {len(data)} rows from {csv_file_path}")
            return data, None
    except FileNotFoundError:
        logger.error(f"File not found: {csv_file_path}")
        raise
    except csv.Error as e:
        logger.error(f"CSV error in {csv_file_path}: {e}")
        raise

def transform_data(data: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """
    Transforms the extracted data by cleaning and aggregating.

    For demonstration, this example cleans by converting 'age' to integer (if possible)
    and aggregates by counting entries per 'country'.

    Args:
    - data (List[Dict[str, str]]): The extracted data.

    Returns:
    - The transformed data.
    """
    # Example Transformation: Clean and Aggregate
    transformed_data = []
    country_counts: Dict[str, int] = {}

    for row in data:
        try:
            # Clean: Convert 'age' to int if possible
            row['age'] = str(int(row['age'])) if row['age'].isdigit() else 'Unknown'
            
            # Aggregate Example: Count per country
            country_counts[row['country']] = country_counts.get(row['country'], 0) + 1
            
            transformed_data.append(row)
        except KeyError as e:
            logger.warning(f"Missing key in row: {e}")
            # Optionally, you could choose to skip or handle missing keys differently

    logger.info("Transformed data and counted entries per country")
    # For demonstration, log the aggregate counts
    for country, count in country_counts.items():
        logger.info(f"{country}: {count}")

    return transformed_data

def load_data(db_path: str, table_name: str, data: List[Dict[str, str]]) -> None:
    """
    Loads the transformed data into a SQLite database.

    Args:
    - db_path (str): Path to the SQLite database file.
    - table_name (str): Name of the table to load data into.
    - data (List[Dict[str, str]]): The transformed data to load.
    """
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            
            # Dynamically create table if not exists with generic columns for demo
            # **IN PRODUCTION, USE PREDEFINED TABLE STRUCTURE FOR SECURITY**
            columns = ', '.join([f"{key} TEXT" for key in data[0].keys()])
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {table_name} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    {columns}
                )
            """)
            
            # Insert data
            placeholders = ', '.join('?' for _ in data[0].keys())
            insert_stmt = f"INSERT INTO {table_name} VALUES (NULL, {placeholders})"
            cursor.executemany(insert_stmt, [list(row.values()) for row in data])
            conn.commit()
            logger.info(f"Loaded {len(data)} rows into {db_path}/{table_name}")
    except sqlite3.Error as e:
        logger.error(f"SQLite Error: {e}")
        raise

def main() -> None:
    """
    Orchestrates the ETL pipeline.
    """
    csv_file_path = "input/data.csv"  # Source CSV
    db_path = "output/etl.db"         # Destination Database
    table_name = "transformed_data"   # Table in the database
    
    # Ensure output directory exists
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    
    try:
        data, _ = extract_data(csv_file_path)
        if data:
            transformed_data = transform_data(data)
            load_data(db_path, table_name, transformed_data)
        else:
            logger.info("No data to process.")
    except Exception as e:
        logger.critical(f"ETL Pipeline Failed: {e}")
        raise

if __name__ == "__main__":
    main()