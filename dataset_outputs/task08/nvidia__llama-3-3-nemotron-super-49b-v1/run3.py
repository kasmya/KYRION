import csv
import logging
import os
import sqlite3
from dataclasses import dataclass
from enum import Enum
from typing import List, Dict

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

class ETLStatus(Enum):
    """ETL Pipeline Status"""
    SUCCESS = 1
    FAILURE = 2

@dataclass
class ETLConfig:
    """ETL Pipeline Configuration"""
    input_csv_file: str
    output_db_file: str
    table_name: str

class ETLPipeline:
    """ETL Pipeline for CSV to SQLite"""
    
    def __init__(self, config: ETLConfig):
        """
        Initialize ETL Pipeline with configuration.

        Args:
        - config (ETLConfig): Configuration object
        """
        self.config = config

    def extract(self) -> List[Dict]:
        """
        Extract data from CSV file.

        Returns:
        - List[Dict]: Extracted data as list of dictionaries
        """
        try:
            with open(self.config.input_csv_file, 'r') as file:
                reader = csv.DictReader(file)
                data = [row for row in reader]
                logging.info(f"Extracted {len(data)} records from {self.config.input_csv_file}")
                return data
        except FileNotFoundError:
            logging.error(f"Input file {self.config.input_csv_file} not found.")
            raise
        except csv.Error as e:
            logging.error(f"CSV error: {e}")
            raise

    def transform(self, data: List[Dict]) -> List[Dict]:
        """
        Transform data by cleaning and aggregating.

        Note: This example assumes a simple transformation (lowercasing strings and summing a value).
              Real-world scenarios would require more sophisticated logic based on the data.

        Args:
        - data (List[Dict]): Data to transform

        Returns:
        - List[Dict]: Transformed data
        """
        # Example transformation: lowercase all string values and assume a column 'value' to sum
        transformed_data = []
        for row in data:
            transformed_row = {k: v.lower() if isinstance(v, str) else v for k, v in row.items()}
            # Simple aggregation example: assume 'value' column exists and is numeric
            if 'value' in transformed_row and isinstance(transformed_row['value'], (int, float)):
                transformed_row['value'] = transformed_row['value']  # No aggregation in this example
            transformed_data.append(transformed_row)
        logging.info("Transformed data")
        return transformed_data

    def load(self, data: List[Dict]) -> ETLStatus:
        """
        Load transformed data into SQLite database.

        Args:
        - data (List[Dict]): Transformed data to load

        Returns:
        - ETLStatus: Status of the load operation
        """
        try:
            with sqlite3.connect(self.config.output_db_file) as conn:
                cursor = conn.cursor()
                # Create table if not exists with dynamic column handling
                columns = ', '.join(f'{k} TEXT' for k in data[0].keys()) if data else ''
                if columns:
                    cursor.execute(f"CREATE TABLE IF NOT EXISTS {self.config.table_name} ({columns})")
                    # Insert data
                    placeholders = ', '.join('?' for _ in data[0].keys())
                    insert_stmt = f"INSERT INTO {self.config.table_name} VALUES ({placeholders})"
                    cursor.executemany(insert_stmt, (list(row.values()) for row in data))
                    conn.commit()
                    logging.info(f"Loaded {len(data)} records into {self.config.table_name}")
                    return ETLStatus.SUCCESS
                else:
                    logging.warning("No data to load.")
                    return ETLStatus.SUCCESS
        except sqlite3.Error as e:
            logging.error(f"SQLite error: {e}")
            return ETLStatus.FAILURE

    def run(self) -> ETLStatus:
        """
        Run the ETL pipeline.

        Returns:
        - ETLStatus: Overall status of the ETL pipeline
        """
        try:
            data = self.extract()
            transformed_data = self.transform(data)
            status = self.load(transformed_data)
            return status
        except Exception as e:
            logging.error(f"ETL Pipeline failed: {e}")
            return ETLStatus.FAILURE

if __name__ == "__main__":
    # Example usage
    config = ETLConfig(
        input_csv_file="input_data.csv",
        output_db_file="output.db",
        table_name="TransformedData"
    )
    etl = ETLPipeline(config)
    status = etl.run()
    logging.info(f"ETL Pipeline {status.name}")