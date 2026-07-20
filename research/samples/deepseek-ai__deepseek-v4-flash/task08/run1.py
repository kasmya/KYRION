import csv
import sqlite3
from pathlib import Path
from typing import List, Dict, Any, Optional
import pandas as pd


class ETLPipeline:
    """
    A simple ETL pipeline that extracts data from a CSV file,
    transforms it by cleaning and aggregating, and loads it into a SQLite database.
    """

    def __init__(self, csv_path: str, db_path: str, table_name: str = "aggregated_data"):
        """
        Initialize the pipeline with file paths and target table name.

        Args:
            csv_path: Path to the input CSV file.
            db_path: Path to the SQLite database file.
            table_name: Name of the table to store aggregated data.

        Raises:
            ValueError: If table_name is empty or contains invalid characters.
        """
        self.csv_path = Path(csv_path)
        self.db_path = Path(db_path)
        if not table_name or not table_name.isidentifier():
            raise ValueError("table_name must be a non‑empty valid identifier")
        self.table_name = table_name

    def extract(self) -> pd.DataFrame:
        """
        Extract data from the CSV file into a pandas DataFrame.

        Returns:
            DataFrame containing raw CSV data.

        Raises:
            FileNotFoundError: If CSV file does not exist.
            PermissionError: If CSV file cannot be read.
            pd.errors.EmptyDataError: If CSV file is empty.
            pd.errors.ParserError: If CSV is malformed.
        """
        if not self.csv_path.exists():
            raise FileNotFoundError(f"CSV file not found: {self.csv_path}")
        try:
            df = pd.read_csv(self.csv_path, encoding='utf-8-sig')
        except (PermissionError, pd.errors.EmptyDataError, pd.errors.ParserError) as e:
            raise type(e)(f"Error reading CSV file: {e}") from e
        return df

    def transform(self, df: pd.DataFrame, group_by_column: str, agg_column: str) -> pd.DataFrame:
        """
        Clean and aggregate the DataFrame.

        Steps:
            - Remove duplicate rows.
            - Drop rows with missing values in key columns.
            - Strip whitespace from string columns.
            - Group by the specified column and aggregate another column (sum).

        Args:
            df: Input DataFrame to transform.
            group_by_column: Column name to group by.
            agg_column: Column name to aggregate (sum).

        Returns:
            Aggregated DataFrame.

        Raises:
            ValueError: If required columns are missing or aggregation fails.
        """
        # Validate column existence
        for col in [group_by_column, agg_column]:
            if col not in df.columns:
                raise ValueError(f"Column '{col}' not found in data")

        # Clean data
        df = df.drop_duplicates().copy()
        df = df.dropna(subset=[group_by_column, agg_column])

        # Strip whitespace from string columns
        for col in df.select_dtypes(include='object').columns:
            df[col] = df[col].str.strip()

        # Attempt to convert aggregation column to numeric, coercing errors
        df[agg_column] = pd.to_numeric(df[agg_column], errors='coerce')
        df = df.dropna(subset=[agg_column])

        # Aggregate
        try:
            aggregated = df.groupby(group_by_column, as_index=False)[agg_column].sum()
        except Exception as e:
            raise ValueError(f"Aggregation failed: {e}") from e

        return aggregated

    def load(self, df: pd.DataFrame) -> None:
        """
        Load the aggregated DataFrame into the SQLite database table.

        Uses parameterized INSERT to avoid SQL injection.

        Args:
            df: DataFrame to load.

        Raises:
            sqlite3.Error: If database operation fails.
            PermissionError: If database file cannot be created/written.
        """
        # Ensure parent directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                # Use parameterized inserts via pandas to_sql with if_exists='replace'
                # Security: pandas to_sql uses parameterized queries internally
                df.to_sql(
                    self.table_name,
                    conn,
                    if_exists='replace',
                    index=False,
                    method='multi'  # faster inserts, safe with placeholders
                )
        except sqlite3.Error as e:
            raise sqlite3.Error(f"Database error: {e}") from e
        except PermissionError as e:
            raise PermissionError(f"Cannot write to database file: {e}") from e

    def run(self, group_by_column: str, agg_column: str) -> None:
        """
        Execute the full ETL pipeline: extract -> transform -> load.

        Args:
            group_by_column: Column name to group by.
            agg_column: Column name to aggregate (sum).

        Raises:
            Various exceptions from extract, transform, or load.
        """
        print("Starting ETL pipeline...")
        df = self.extract()
        print(f"Extracted {len(df)} rows from CSV.")
        aggregated = self.transform(df, group_by_column, agg_column)
        print(f"Transformed data: {len(aggregated)} rows after aggregation.")
        self.load(aggregated)
        print(f"Loaded data into table '{self.table_name}' in {self.db_path}.")


# Example usage (uncomment to test):
# if __name__ == "__main__":
#     pipeline = ETLPipeline("data.csv", "output.db", "sales_summary")
#     pipeline.run("category", "amount")