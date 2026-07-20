import csv
import logging
import os
import sqlite3
from typing import Any, Dict, List

# Set up logging configuration
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def extract_data(csv_file: str) -> List[Dict[str, Any]]:
    """
    Extract data from a CSV file.

    Args:
    - csv_file (str): Path to the CSV file.

    Returns:
    - List[Dict[str, Any]]: A list of dictionaries, where each dictionary represents a row in the CSV file.

    Raises:
    - FileNotFoundError: If the CSV file does not exist.
    - csv.Error: If there is an error parsing the CSV file.
    """
    try:
        with open(csv_file, 'r') as file:
            reader = csv.DictReader(file)
            data = [row for row in reader]
            return data
    except FileNotFoundError:
        logging.error(f"File {csv_file} not found.")
        raise
    except csv.Error as e:
        logging.error(f"Error parsing CSV file: {e}")
        raise

def transform_data(data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Clean and aggregate the extracted data.

    Args:
    - data (List[Dict[str, Any]]): The extracted data.

    Returns:
    - List[Dict[str, Any]]: The cleaned and aggregated data.
    """
    # Example transformation: Remove any rows with missing values and calculate the sum of a column
    transformed_data = [row for row in data if not any(value == '' for value in row.values())]
    for row in transformed_data:
        row['sum_column'] = sum(int(value) for value in row['column_name'].split(','))
    return transformed_data

def load_data(data: List[Dict[str, Any]], db_file: str, table_name: str) -> None:
    """
    Load the transformed data into a SQLite database.

    Args:
    - data (List[Dict[str, Any]]): The transformed data.
    - db_file (str): Path to the SQLite database file.
    - table_name (str): Name of the table to create in the database.

    Raises:
    - sqlite3.Error: If there is an error connecting to the database or executing the SQL query.
    """
    try:
        with sqlite3.connect(db_file) as conn:
            cursor = conn.cursor()
            # Create the table if it does not exist
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {table_name} (
                    id INTEGER PRIMARY KEY,
                    {', '.join(f'{key} TEXT' for key in data[0].keys())}
                )
            """)
            # Insert the data into the table
            cursor.executemany(f"""
                INSERT INTO {table_name} ({', '.join(data[0].keys())})
                VALUES ({', '.join('?' for _ in data[0])})
            """, [tuple(row.values()) for row in data])
    except sqlite3.Error as e:
        logging.error(f"Error loading data into database: {e}")
        raise

def main() -> None:
    csv_file = 'data.csv'
    db_file = 'data.db'
    table_name = 'data_table'

    data = extract_data(csv_file)
    transformed_data = transform_data(data)
    load_data(transformed_data, db_file, table_name)

if __name__ == '__main__':
    main()