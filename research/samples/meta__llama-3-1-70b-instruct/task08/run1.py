import csv
import logging
import os
import sqlite3
from pathlib import Path
from typing import Dict, List

import pandas as pd

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ETLPipeline:
    def __init__(self, csv_file: Path, db_file: Path):
        """
        Initializes the ETL pipeline with input CSV file and output SQLite database file.

        Args:
        csv_file (Path): Path to the input CSV file.
        db_file (Path): Path to the output SQLite database file.
        """
        self.csv_file = csv_file
        self.db_file = db_file

    def extract(self) -> pd.DataFrame:
        """
        Extracts data from the CSV file into a Pandas DataFrame.

        Returns:
        pd.DataFrame: The extracted data.
        """
        try:
            data = pd.read_csv(self.csv_file)
            logger.info(f"Extracted {len(data)} rows from {self.csv_file}")
            return data
        except pd.errors.EmptyDataError:
            logger.error(f"No data in {self.csv_file}")
            return pd.DataFrame()
        except pd.errors.ParserError as e:
            logger.error(f"Failed to parse {self.csv_file}: {e}")
            raise

    def transform(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Cleans and aggregates the extracted data.

        Args:
        data (pd.DataFrame): The extracted data.

        Returns:
        pd.DataFrame: The transformed data.
        """
        # Remove rows with missing values
        cleaned_data = data.dropna()
        logger.info(f"Removed {len(data) - len(cleaned_data)} rows with missing values")

        # Aggregate data by a column (e.g., 'category')
        aggregated_data = cleaned_data.groupby('category').sum()
        logger.info("Aggregated data by 'category' column")
        return aggregated_data

    def load(self, data: pd.DataFrame) -> None:
        """
        Loads the transformed data into the SQLite database.

        Args:
        data (pd.DataFrame): The transformed data.
        """
        try:
            # Create the database if it doesn't exist
            if not self.db_file.exists():
                logger.info(f"Creating database {self.db_file}")
                self.db_file.touch()

            # Connect to the database
            with sqlite3.connect(self.db_file) as conn:
                # Create a table if it doesn't exist
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS aggregated_data
                    (category TEXT PRIMARY KEY, sum REAL)
                """)
                logger.info("Created 'aggregated_data' table if it didn't exist")

                # Insert data into the table
                data.reset_index().to_sql('aggregated_data', conn, if_exists='replace', index=False)
                logger.info(f"Loaded {len(data)} rows into {self.db_file}")
        except sqlite3.Error as e:
            logger.error(f"Failed to load data into {self.db_file}: {e}")
            raise

    def run(self) -> None:
        """
        Runs the ETL pipeline.
        """
        data = self.extract()
        transformed_data = self.transform(data)
        self.load(transformed_data)

if __name__ == '__main__':
    csv_file = Path('input.csv')
    db_file = Path('output.db')
    pipeline = ETLPipeline(csv_file, db_file)
    pipeline.run()