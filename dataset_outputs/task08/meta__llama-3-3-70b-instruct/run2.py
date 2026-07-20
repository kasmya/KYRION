import csv
import sqlite3
import pandas as pd
from typing import Dict, List, Optional
from pathlib import Path

def extract_data(file_path: Path) -> Optional[pd.DataFrame]:
    """
    Extract data from a CSV file.

    Args:
    file_path (Path): The path to the CSV file.

    Returns:
    Optional[pd.DataFrame]: The extracted data as a DataFrame, or None if extraction failed.
    """
    try:
        data = pd.read_csv(file_path)
        return data
    except pd.errors.EmptyDataError:
        print("Error: The CSV file is empty.")
        return None
    except pd.errors.ParserError as e:
        print(f"Error: Failed to parse the CSV file. {e}")
        return None

def transform_data(data: pd.DataFrame) -> pd.DataFrame:
    """
    Transform the data by cleaning and aggregating it.

    Args:
    data (pd.DataFrame): The data to transform.

    Returns:
    pd.DataFrame: The transformed data.
    """
    # Clean the data by dropping any rows with missing values
    data = data.dropna()

    # Aggregate the data by grouping it by a column and calculating the mean
    aggregated_data = data.groupby('column_name').mean()

    return aggregated_data

def load_data(data: pd.DataFrame, db_path: Path, table_name: str) -> None:
    """
    Load the data into a SQLite database.

    Args:
    data (pd.DataFrame): The data to load.
    db_path (Path): The path to the SQLite database.
    table_name (str): The name of the table to load the data into.
    """
    try:
        # Establish a connection to the database
        with sqlite3.connect(db_path) as conn:
            # Load the data into the table
            data.to_sql(table_name, conn, if_exists='replace', index=False)
    except sqlite3.Error as e:
        print(f"Error: Failed to load data into the database. {e}")

def main() -> None:
    # Define the paths and table name
    csv_file_path = Path('data.csv')
    db_path = Path('data.db')
    table_name = 'data_table'

    # Extract the data from the CSV file
    data = extract_data(csv_file_path)

    if data is not None:
        # Transform the data
        transformed_data = transform_data(data)

        # Load the transformed data into the database
        load_data(transformed_data, db_path, table_name)

if __name__ == '__main__':
    main()