import csv
import sqlite3
from pathlib import Path
from typing import Optional, Tuple

import pandas as pd


class ETLPipeline:
    """
    A simple ETL pipeline that extracts data from a CSV file,
    transforms it by cleaning and aggregating, and loads the results
    into a SQLite database.

    Attributes:
        csv_path (Path): Path to the input CSV file.
        db_path (Path): Path to the SQLite database file.
    """

    def __init__(self, csv_path: str, db_path: str) -> None:
        """
        Initialize the pipeline with source and destination paths.

        Args:
            csv_path: Path to the input CSV file.
            db_path: Path to the SQLite database file.
        """
        self.csv_path = Path(csv_path)
        self.db_path = Path(db_path)

    def extract(self) -> pd.DataFrame:
        """
        Extract data from the CSV file.

        Returns:
            A pandas DataFrame containing the CSV data.

        Raises:
            FileNotFoundError: If the CSV file does not exist.
            pd.errors.EmptyDataError: If the CSV file is empty.
            pd.errors.ParserError: If the CSV file is malformed.
        """
        if not self.csv_path.is_file():
            raise FileNotFoundError(f"CSV file not found: {self.csv_path}")

        try:
            df = pd.read_csv(self.csv_path)
        except pd.errors.EmptyDataError:
            raise pd.errors.EmptyDataError(f"CSV file is empty: {self.csv_path}")
        except pd.errors.ParserError as e:
            raise pd.errors.ParserError(f"Error parsing CSV: {e}")

        return df

    def transform(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Clean and aggregate the input DataFrame.

        Cleaning steps:
            - Remove duplicate rows.
            - Drop rows with missing values in critical columns (e.g., 'id', 'name', 'age').
            - Convert 'age' and 'salary' columns to numeric, coercing errors to NaN.
            - Drop rows where numeric conversion failed.

        Aggregation:
            - Group by 'department' and compute average salary and employee count.

        Args:
            df: Input DataFrame to transform.

        Returns:
            A tuple (cleaned_df, aggregated_df) where:
                - cleaned_df: Cleaned DataFrame with no duplicates and valid numeric fields.
                - aggregated_df: DataFrame with columns 'department', 'avg_salary', 'employee_count'.

        Raises:
            ValueError: If required columns are missing from the DataFrame.
        """
        required_cols = ['id', 'name', 'age', 'salary', 'department']
        missing = [col for col in required_cols if col not in df.columns]
        if missing:
            raise ValueError(f"Missing required columns: {missing}")

        # Remove duplicates
        df_clean = df.drop_duplicates()

        # Drop rows with missing values in critical columns
        df_clean = df_clean.dropna(subset=['id', 'name', 'age'])

        # Convert numeric columns, coerce errors to NaN, then drop NaN rows
        df_clean['age'] = pd.to_numeric(df_clean['age'], errors='coerce')
        df_clean['salary'] = pd.to_numeric(df_clean['salary'], errors='coerce')
        df_clean = df_clean.dropna(subset=['age', 'salary'])

        # Aggregation
        aggregated = (
            df_clean.groupby('department')
            .agg(
                avg_salary=('salary', 'mean'),
                employee_count=('id', 'count')
            )
            .reset_index()
        )

        return df_clean, aggregated

    def load(self, cleaned_df: pd.DataFrame, aggregated_df: pd.DataFrame) -> None:
        """
        Load the transformed data into the SQLite database.

        Creates two tables:
            - 'employees': contains the cleaned individual records.
            - 'department_summary': contains aggregated department statistics.

        If the tables already exist, they will be replaced.

        Args:
            cleaned_df: Cleaned employee data.
            aggregated_df: Aggregated department data.

        Raises:
            sqlite3.Error: If any database operation fails.
        """
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                # Write cleaned data to 'employees' table
                cleaned_df.to_sql('employees', conn, if_exists='replace', index=False)

                # Write aggregated data to 'department_summary' table
                aggregated_df.to_sql('department_summary', conn, if_exists='replace', index=False)

                # Use parameterized queries for any manual SQL (example: verify row count)
                cur = conn.cursor()
                cur.execute("SELECT COUNT(*) FROM employees")
                count = cur.fetchone()[0]
                print(f"Loaded {count} employee records.")
        except sqlite3.Error as e:
            raise sqlite3.Error(f"Database error during load: {e}")

    def run(self) -> None:
        """
        Execute the full ETL pipeline: extract, transform, load.

        This is the main entry point.

        Raises:
            Exception: Re-raises any exception encountered during the pipeline.
        """
        print("Starting ETL pipeline...")
        try:
            df = self.extract()
            print(f"Extracted {len(df)} rows from CSV.")
        except Exception as e:
            print(f"Extraction failed: {e}")
            raise

        try:
            cleaned_df, aggregated_df = self.transform(df)
            print(f"Transformed data: {len(cleaned_df)} cleaned rows, {len(aggregated_df)} departments.")
        except Exception as e:
            print(f"Transformation failed: {e}")
            raise

        try:
            self.load(cleaned_df, aggregated_df)
            print("Data loaded successfully.")
        except Exception as e:
            print(f"Loading failed: {e}")
            raise

        print("ETL pipeline completed.")


# Example usage (commented out - user can uncomment to test)
if __name__ == "__main__":
    # Replace with actual paths
    pipeline = ETLPipeline("employees.csv", "employees.db")
    pipeline.run()