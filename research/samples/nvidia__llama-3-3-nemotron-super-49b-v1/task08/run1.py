import csv
import logging
import os
import sqlite3
from typing import Tuple, Dict, List
import pandas as pd

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

class ETLPipeline:
    """
    ETL Pipeline for extracting data from CSV, transforming, and loading into SQLite.
    """

    def __init__(self, csv_file: str, db_file: str):
        """
        Initialize ETL Pipeline.

        :param csv_file: Path to the CSV file for extraction.
        :param db_file: Path to the SQLite database file for loading.
        """
        self.csv_file = csv_file
        self.db_file = db_file

    def extract(self) -> pd.DataFrame:
        """
        Extract data from CSV file.

        :return: Pandas DataFrame containing the extracted data.
        :raises FileNotFoundError: If the CSV file does not exist.
        """
        try:
            if not os.path.isfile(self.csv_file):
                raise FileNotFoundError(f"CSV file '{self.csv_file}' not found.")
            data = pd.read_csv(self.csv_file)
            logger.info(f"Extracted {len(data)} records from {self.csv_file}")
            return data
        except Exception as e:
            logger.error(f" Extraction failed: {e}", exc_info=True)
            raise

    def transform(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Transform the extracted data by cleaning and aggregating.

        :param data: Pandas DataFrame to be transformed.
        :return: Transformed Pandas DataFrame.
        """
        try:
            # Example transformation: Drop rows with missing values and aggregate
            transformed_data = data.dropna().groupby('category').sum().reset_index()
            logger.info("Transformed data successfully")
            return transformed_data
        except Exception as e:
            logger.error(f"Transformation failed: {e}", exc_info=True)
            raise

    def load(self, data: pd.DataFrame) -> None:
        """
        Load the transformed data into a SQLite database.

        :param data: Transformed Pandas DataFrame to be loaded.
        :raises sqlite3.Error: On database operation errors.
        """
        try:
            with sqlite3.connect(self.db_file) as conn:
                data.to_sql(name="transformed_data", con=conn, if_exists="replace", index=False)
                logger.info(f"Loaded data into {self.db_file}")
        except sqlite3.Error as e:
            logger.error(f"Loading data into DB failed: {e}", exc_info=True)
            raise

    def run(self) -> None:
        """
        Execute the full ETL pipeline.
        """
        try:
            extracted_data = self.extract()
            transformed_data = self.transform(extracted_data)
            self.load(transformed_data)
            logger.info("ETL Pipeline completed successfully")
        except Exception as e:
            logger.error(f"ETL Pipeline failed: {e}", exc_info=True)
            raise


if __name__ == "__main__":
    # Example usage
    csv_file_path = "example.csv"
    db_file_path = "etl_output.db"
    
    etl = ETLPipeline(csv_file_path, db_file_path)
    etl.run()