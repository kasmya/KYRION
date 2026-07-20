import csv
import sqlite3
import pandas as pd
from typing import Dict, List

def extract_data(file_path: str) -> List[Dict]:
    """
    Extract data from a CSV file.

    Args:
    file_path (str): Path to the CSV file.

    Returns:
    List[Dict]: List of dictionaries, where each dictionary represents a row in the CSV file.

    Raises:
    FileNotFoundError: If the CSV file does not exist.
    """
    try:
        with open(file_path, 'r') as file:
            csv_reader = csv.DictReader(file)
            data = [row for row in csv_reader]
        return data
    except FileNotFoundError:
        print(f"The file {file_path} does not exist.")
        raise

def transform_data(data: List[Dict]) -> pd.DataFrame:
    """
    Transform the data by cleaning and aggregating.

    Args:
    data (List[Dict]): List of dictionaries, where each dictionary represents a row in the CSV file.

    Returns:
    pd.DataFrame: Pandas DataFrame representing the transformed data.
    """
    df = pd.DataFrame(data)
    # Clean the data (e.g., remove duplicates, handle missing values)
    df = df.drop_duplicates()
    df = df.fillna('')
    # Aggregate the data (e.g., group by, sum, mean)
    df = df.groupby('column_name').agg({'column_name': 'sum'})
    return df

def load_data(df: pd.DataFrame, db_path: str, table_name: str) -> None:
    """
    Load the transformed data into a SQLite database.

    Args:
    df (pd.DataFrame): Pandas DataFrame representing the transformed data.
    db_path (str): Path to the SQLite database.
    table_name (str): Name of the table to load the data into.

    Raises:
    sqlite3.Error: If an error occurs while loading the data into the database.
    """
    try:
        with sqlite3.connect(db_path) as conn:
            df.to_sql(table_name, conn, if_exists='replace', index=False)
    except sqlite3.Error as e:
        print(f"An error occurred while loading the data into the database: {e}")
        raise

def main() -> None:
    file_path = 'data.csv'
    db_path = 'data.db'
    table_name = 'transformed_data'
    data = extract_data(file_path)
    df = transform_data(data)
    load_data(df, db_path, table_name)

if __name__ == '__main__':
    main()