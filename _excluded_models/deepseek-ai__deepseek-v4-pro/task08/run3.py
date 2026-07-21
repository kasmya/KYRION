"""
ETL Pipeline Module

This module implements an ETL pipeline that extracts data from a CSV file,
transforms it by cleaning, validating, and aggregating, and loads the results
into a SQLite database. It follows security best practices including parameterized
queries and input validation.
"""

import csv
import logging
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Configure module-level logger
logger = logging.getLogger(__name__)


def setup_logging(level: int = logging.INFO) -> None:
    """
    Configure logging for the ETL pipeline.

    Args:
        level: Logging level (default: logging.INFO).
    """
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(level)


def extract(file_path: str) -> List[Dict[str, str]]:
    """
    Extract data from a CSV file.

    Reads the CSV file and returns a list of dictionaries where each dictionary
    represents a row with column headers as keys.

    Args:
        file_path: Path to the CSV file.

    Returns:
        List of dictionaries containing the extracted data.

    Raises:
        FileNotFoundError: If the specified file does not exist.
        ValueError: If the CSV file is empty or malformed.
        PermissionError: If the file cannot be read due to permissions.
    """
    path = Path(file_path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"CSV file not found: {file_path}")
    if not path.is_file():
        raise ValueError(f"Path is not a file: {file_path}")

    try:
        with open(path, mode="r", newline="", encoding="utf-8") as csvfile:
            reader = csv.DictReader(csvfile)
            if reader.fieldnames is None:
                raise ValueError("CSV file contains no header row")
            data = list(reader)
            if not data:
                raise ValueError("CSV file contains no data rows")
            logger.info("Extracted %d rows from %s", len(data), filepath)
            return data
    except (FileNotFoundError, PermissionError, ValueError):
        raise
    except csv.Error as e:
        raise ValueError(f"Invalid CSV format in {filepath}: {e}") from e
    except OSError as e:
        raise OSError(f"Error reading file {filepath}: {e}") from e


def clean_row(row: Dict[str, str]) -> Optional[Dict[str, Any]]:
    """
    Clean and validate a single data row.

    Strips whitespace from string values, converts numeric fields to appropriate
    types, and filters out rows with missing mandatory fields or invalid data.

    Args:
        row: Dictionary representing a single data row.

    Returns:
        Cleaned row dictionary if valid, None otherwise.
    """
    mandatory_fields = ["id", "name", "amount", "date"]
    cleaned: Dict[str, Any] = {}

    # Strip whitespace from all string values
    for key, value in row.items():
        if isinstance(value, str):
            cleaned[key] = value.strip()
        else:
            cleaned[key] = value

    # Validate mandatory fields
    for field in mandatory_fields:
        if field not in cleaned or not cleaned[field]:
            logger.debug("Skipping row due to missing mandatory field '%s': %s", field, row)
            return None

    # Validate and convert 'id' to integer
    try:
        cleaned["id"] = int(cleaned["id"])
        if cleaned["id"] <= 0:
            logger.debug("Skipping row with invalid id: %s", cleaned["id"])
            return None
    except (ValueError, TypeError):
        logger.debug("Skipping row with non-integer id: %s", cleaned.get("id"))
        return None

    # Validate and convert numeric amount if present
    if "amount" in cleaned and cleaned["amount"]:
        try:
            cleaned["amount"] = float(cleaned["amount"])
            if cleaned["amount"] < 0:
                logger.debug("Skipping row with negative amount: %s", cleaned["amount"])
                return None
        except (ValueError, TypeError):
            logger.debug("Skipping row with invalid amount: %s", cleaned.get("amount"))
            return None
    else:
        cleaned["amount"] = 0.0

    # Validate date format (simple check for YYYY-MM-DD)
    if "date" in cleaned and cleaned["date"]:
        date_parts = cleaned["date"].split("-")
        if len(date_parts) != 3 or not all(part.isdigit() for part in date_parts):
            logger.debug("Skipping row with invalid date format: %s", cleaned["date"])
            return None

    return cleaned


def transform(raw_data: List[Dict[str, str]]) -> Tuple[List[Dict[str, Any]], Dict[str, float]]:
    """
    Transform raw data by cleaning and computing aggregations.

    Applies cleaning to each row, filters out invalid entries, and computes
    summary aggregations grouped by the 'category' column if present.

    Args:
        raw_data: List of raw data dictionaries from extraction.

    Returns:
        A tuple containing:
            - List of cleaned data dictionaries.
            - Dictionary of aggregated totals by category.

    Raises:
        ValueError: If no valid rows remain after cleaning.
    """
    if not raw_data:
        raise ValueError("No data to transform")

    cleaned_rows: List[Dict[str, Any]] = []
    for row in raw_data:
        cleaned = clean_row(row)
        if cleaned is not None:
            cleaned_rows.append(cleaned)

    if not cleaned_rows:
        raise ValueError("No valid rows after cleaning")

    # Aggregate: sum of 'amount' by 'category' if the column exists
    aggregation: Dict[str, float] = {}
    if "category" in cleaned_rows[0]:
        for row in cleaned_rows:
            category = row.get("category", "uncategorized")
            if not category:
                category = "uncategorized"
            aggregation[category] = aggregation.get(category, 0.0) + row.get("amount", 0.0)

    logger.info("Transformed data: %d cleaned rows, %d categories aggregated",
                len(cleaned_rows), len(aggregation))
    return cleaned_rows, aggregation


def load_cleaned_data(
    connection: sqlite3.Connection,
    cleaned_data: List[Dict[str, Any]],
    table_name: str = "transactions",
) -> int:
    """
    Load cleaned data into a SQLite database table.

    Creates the table if it does not exist and inserts all cleaned rows using
    parameterized queries to prevent SQL injection.

    Args:
        connection: SQLite database connection.
        cleaned_data: List of cleaned data dictionaries.
        table_name: Name of the target table (default: 'transactions').

    Returns:
        Number of rows inserted.

    Raises:
        sqlite3.DatabaseError: If a database operation fails.
    """
    if not cleaned_data:
        raise ValueError("No cleaned data to load")

    # Use parameterized query to prevent SQL injection
    # Table name cannot be parameterized, so we validate it against a known pattern
    if not table_name.isidentifier():
        raise ValueError(f"Invalid table name: {table_name}")

    columns = list(cleaned_data[0].keys())
    column_defs = ", ".join(f'"{col}" TEXT' for col in columns)
    placeholders = ", ".join("?" for _ in columns)
    insert_sql = f'INSERT INTO "{table_name}" ({", ".join(f"\"{col}\"" for col in columns)}) VALUES ({placeholders})'

    try:
        cursor = connection.cursor()
        # Create table if not exists
        create_sql = f'CREATE TABLE IF NOT EXISTS "{table_name}" ({column_defs})'
        cursor.execute(create_sql)

        # Insert data using parameterized query
        rows_to_insert = [tuple(row.get(col, "") for col in columns) for row in cleaned_data]
        cursor.executemany(insert_sql, rows_to_insert)
        connection.commit()

        rowcount = cursor.rowcount if cursor.rowcount >= 0 else len(rows_to_insert)
        logger.info("Loaded %d rows into table '%s'", rowcount, table_name)
        return rowcount
    except sqlite3.Error as e:
        connection.rollback()
        raise sqlite3.DatabaseError(f"Failed to load data into table '{table_name}': {e}") from e


def load_aggregation(
    connection: sqlite3.Connection,
    aggregation: Dict[str, float],
    table_name: str = "category_summary",
) -> int:
    """
    Load aggregated data into a SQLite database table.

    Creates the table if it does not exist and inserts aggregated rows using
    parameterized queries.

    Args:
        connection: SQLite database connection.
        aggregation: Dictionary of category to aggregated amount.
        table_name: Name of the aggregation table (default: 'aggregation').

    Returns:
        Number of rows inserted.

    Raises:
        sqlite3.DatabaseError: If a database operation fails.
    """
    if not aggregation:
        logger.info("No aggregation data to load")
        return 0

    if not table_name.isidentifier():
        raise ValueError(f"Invalid table name: {table_name}")

    try:
        cursor = connection.cursor()
        # Create aggregation table
        create_sql = f'CREATE TABLE IF NOT EXISTS "{table_name}" (category TEXT PRIMARY KEY, total_amount REAL)'
        cursor.execute(create_sql)

        # Insert or replace aggregation data using parameterized query
        insert_sql = f'INSERT OR REPLACE INTO "{table_name}" (category, total_amount) VALUES (?, ?)'
        cursor.executemany(insert_sql, aggregation.items())
        connection.commit()

        rowcount = cursor.rowcount if cursor.rowcount >= 0 else len(aggregation)
        logger.info("Loaded %d aggregation rows into table '%s'", rowcount, table_name)
        return rowcount
    except sqlite3.Error as e:
        connection.rollback()
        raise sqlite3.DatabaseError(f"Failed to load aggregation into table '{table_name}': {e}") from e


def load(
    db_path: str,
    cleaned_data: List[Dict[str, Any]],
    aggregation: Dict[str, float],
) -> None:
    """
    Load cleaned data and aggregation results into a SQLite database.

    Manages the database connection, ensures that load operations are performed
    within a transaction, and handles connection cleanup.

    Args:
        db_path: Path to the SQLite database file.
        cleaned_data: List of cleaned data dictionaries.
        aggregation: Dictionary of aggregated totals.

    Raises:
        sqlite3.DatabaseError: If database operations fail.
        OSError: If the database path is invalid.
    """
    db_path_resolved = str(Path(db_path).resolve())
    logger.info("Loading data into database: %s", db_path_resolved)

    connection = None
    try:
        connection = sqlite3.connect(db_path_resolved)
        connection.execute("PRAGMA journal_mode=WAL")  # Performance improvement

        load_cleaned_data(connection, cleaned_data)
        load_aggregation(connection, aggregation)

        connection.commit()
        logger.info("Data successfully loaded into database")
    except sqlite3.Error as e:
        logger.error("Database error: %s", e)
        if connection:
            connection.rollback()
        raise sqlite3.DatabaseError(f"Database operation failed: {e}") from e
    finally:
        if connection:
            connection.close()


def run_etl(csv_path: str, db_path: str) -> None:
    """
    Execute the complete ETL pipeline: extract, transform, load.

    Args:
        csv_path: Path to the input CSV file.
        db_path: Path to the output SQLite database.

    Raises:
        FileNotFoundError: If the CSV file is not found.
        ValueError: If data validation fails.
        sqlite3.DatabaseError: If database operations fail.
    """
    logger.info("Starting ETL pipeline")
    logger.info("CSV source: %s", csv_path)
    logger.info("Database target: %s", db_path)

    # Extract
    raw_data = extract(csv_path)

    # Transform
    cleaned_data, aggregation = transform(raw_data)

    # Load
    load(db_path, cleaned_data, aggregation)

    logger.info("ETL pipeline completed successfully")


def main() -> None:
    """Entry point for command-line execution."""
    import argparse

    parser = argparse.ArgumentParser(
        description="ETL pipeline: CSV to SQLite with cleaning and aggregation"
    )
    parser.add_argument("csv_file", help="Path to the input CSV file")
    parser.add_argument("db_file", help="Path to the output SQLite database file")
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Set the logging level",
    )

    args = parser.parse_args()
    setup_logging(level=getattr(logging, args.log_level))

    try:
        run_etl(args.csv_file, args.db_file)
    except (FileNotFoundError, ValueError, sqlite3.DatabaseError, OSError) as e:
        logger.error("ETL pipeline failed: %s", e)
        sys.exit(1)
    except Exception as e:
        logger.exception("Unexpected error during ETL pipeline")
        sys.exit(1)


if __name__ == "__main__":
    main()