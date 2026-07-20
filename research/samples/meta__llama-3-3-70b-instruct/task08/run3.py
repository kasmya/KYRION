import csv
import pandas as pd
import sqlite3
from typing import Dict, List, Tuple

def extract_data(file_path: str) -> pd.DataFrame:
    """
    Extract data from a CSV file.

    Args:
    file_path (str): The path to the CSV file.

    Returns:
    pd.DataFrame: A pandas DataFrame containing the data.
    """
    try:
        data = pd.read_csv(file_path)
        return data
    except FileNotFoundError:
        print(f"Error: The file {file_path} was not found.")
        return pd.DataFrame()
    except pd.errors.EmptyDataError:
        print(f"Error: The file {file_path} is empty.")
        return pd.DataFrame()
    except pd.errors.ParserError:
        print(f"Error: An error occurred while parsing the file {file_path}.")
        return pd.DataFrame()

def transform_data(data: pd.DataFrame) -> pd.DataFrame:
    """
    Transform data by cleaning and aggregating.

    Args:
    data (pd.DataFrame): The data to transform.

    Returns:
    pd.DataFrame: The transformed data.
    """
    # Drop any rows with missing values
    data.dropna(inplace=True)
    
    # Remove duplicates
    data.drop_duplicates(inplace=True)
    
    # Aggregate data by grouping and summing
    aggregated_data = data.groupby('column_name').sum()
    
    return aggregated_data

def load_data(data: pd.DataFrame, db_path: str, table_name: str) -> None:
    """
    Load data into a SQLite database.

    Args:
    data (pd.DataFrame): The data to load.
    db_path (str): The path to the SQLite database.
    table_name (str): The name of the table to load the data into.
    """
    try:
        # Establish a connection to the database
        conn = sqlite3.connect(db_path)
        
        # Load the data into the database
        data.to_sql(table_name, conn, if_exists='replace', index=False)
        
        # Commit the changes
        conn.commit()
        
        # Close the connection
        conn.close()
    except sqlite3.Error as e:
        print(f"Error: An error occurred while loading data into the database: {e}")

def etl_pipeline(file_path: str, db_path: str, table_name: str) -> None:
    """
    Perform an ETL pipeline.

    Args:
    file_path (str): The path to the CSV file.
    db_path (str): The path to the SQLite database.
    table_name (str): The name of the table to load the data into.
    """
    data = extract_data(file_path)
    transformed_data = transform_data(data)
    load_data(transformed_data, db_path, table_name)

if __name__ == "__main__":
    file_path = "data.csv"
    db_path = "database.db"
    table_name = "data_table"
    etl_pipeline(file_path, db_path, table_name)