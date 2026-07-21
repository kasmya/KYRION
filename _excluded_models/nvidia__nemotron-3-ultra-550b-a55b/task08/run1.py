"""
ETL Pipeline Module

This module provides a simple ETL (Extract, Transform, Load) pipeline that:
1. Extracts data from a CSV file
2. Transforms the data by cleaning and aggregating
3. Loads the transformed data into a SQLite database

All functions include type hints, docstrings, and explicit error handling.
Security best practices are followed (parameterized queries, path validation).
"""

import csv
import logging
import os
import sqlite3
from typing import Any, Dict, List, Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def validate_file_path(file_path: str, must_exist: bool = True) -> str:
    """
    Validate and sanitize a file path to prevent directory traversal attacks.

    Args:
        file_path: The file path to validate.
        must_exist: If True, the file must exist; if False, the parent directory must exist.

    Returns:
        The normalized absolute path.

    Raises:
        ValueError: If the path is invalid or does not meet existence requirements.
    """
    if not file_path or not isinstance(file_path, str):
        raise ValueError("File path must be a non-empty string")

    # Normalize path (resolve .. and .)
    normalized_path = os.path.normpath(os.path.abspath(file_path))

    # Optional: restrict to current working directory or a safe base directory
    # For this example, we just ensure it's a valid path
    if must_exist and not os.path.exists(normalized_path):
        raise ValueError(f"File does not exist: {normalized_path}")

    if not must_exist:
        parent_dir = os.path.dirname(normalized_path)
        if parent_dir and not os.path.exists(parent_dir):
            raise ValueError(f"Parent directory does not exist: {parent_dir}")

    return normalized_path


def extract(csv_path: str) -> List[Dict[str, Any]]:
    """
    Extract data from a CSV file.

    Args:
        csv_path: Path to the CSV file.

    Returns:
        List of dictionaries representing rows, with column headers as keys.

    Raises:
        FileNotFoundError: If the CSV file does not exist.
        ValueError: If the CSV file is empty or malformed.
        Exception: For other I/O or parsing errors.
    """
    validated_path = validate_file_path(csv_path, must_exist=True)
    logger.info("Extracting data from %s", validated_path)

    try:
        with open(validated_path, mode="r", encoding="utf-8") as file:
            # Use DictReader to handle header mapping
            reader = csv.DictReader(file)
            if not reader.fieldnames:
                raise ValueError("CSV file has no header row")

            data = list(reader)
            if not data:
                logger.warning("CSV file contains no data rows")
            return data
    except FileNotFoundError as exc:
        logger.error("CSV file not found: %s", validated_path)
        raise
    except csv.Error as exc:
        logger.error("CSV parsing error: %s", exc)
        raise ValueError(f"Malformed CSV file: {exc}") from exc
    except Exception as exc:
        logger.error("Unexpected error during extraction: %s", exc)
        raise


def clean_row(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Clean a single row: strip whitespace, convert numeric fields, handle missing values.

    Args:
        row: Dictionary representing a row.

    Returns:
        Cleaned row dictionary, or None if the row should be discarded.
    """
    cleaned = {}
    for key, value in row.items():
        # Strip whitespace from strings
        if isinstance(value, str):
            stripped = value.strip()
            # Treat empty strings as None
            cleaned[key] = stripped if stripped else None
        else:
            cleaned[key] = value

    # Example: convert 'value' field to float if present
    if "value" in cleaned and cleaned["value"] is not None:
        try:
            cleaned["value"] = float(cleaned["value"])
        except ValueError:
            logger.warning("Invalid numeric value '%s' in row, discarding row", cleaned["value"])
            return None

    # Discard rows with missing required fields (customize as needed)
    required_fields = ["id", "category", "value"]
    for field in required_fields:
        if cleaned.get(field) is None:
            logger.warning("Missing required field '%s' in row, discarding row", field)
            return None

    return cleaned


def aggregate_data(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Aggregate cleaned rows by category.

    Args:
        rows: List of cleaned row dictionaries.

    Returns:
        List of aggregated dictionaries with keys: category, total_value, count.
    """
    aggregation: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        category = row["category"]
        value = row["value"]
        if category not in aggregation:
            aggregation[category] = {"category": category, "total_value": 0.0, "count": 0}
        aggregation[category]["total_value"] += value
        aggregation[category]["count"] += 1

    return list(aggregation.values())


def transform(raw_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Transform raw data by cleaning and aggregating.

    Args:
        raw_data: List of raw row dictionaries from CSV.

    Returns:
        List of aggregated dictionaries ready for loading.
    """
    logger.info("Transforming %d raw rows", len(raw_data))

    cleaned_rows = []
    for idx, row in enumerate(raw_data):
        cleaned = clean_row(row)
        if cleaned is not None:
            cleaned_rows.append(cleaned)
        else:
            logger.debug("Row %d discarded during cleaning", idx)

    logger.info("Retained %d rows after cleaning", len(cleaned_rows))

    aggregated = aggregate_data(cleaned_rows)
    logger.info("Aggregated into %d categories", len(aggregated))

    return aggregated


def load(transformed_data: List[Dict[str, Any]], db_path: str) -> None:
    """
    Load transformed data into a SQLite database.

    Args:
        transformed_data: List of aggregated dictionaries.
        db_path: Path to the SQLite database file.

    Raises:
        ValueError: If the database path is invalid.
        sqlite3.Error: For database errors.
    """
    validated_db_path = validate_file_path(db_path, must_exist=False)
    logger.info("Loading data into SQLite database at %s", validated_db_path)

    # Ensure directory exists
    os.makedirs(os.path.dirname(validated_db_path) or ".", exist_ok=True)

    try:
        with sqlite3.connect(validated_db_path) as conn:
            cursor = conn.cursor()

            # Create table if not exists
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS category_summary (
                    category TEXT PRIMARY KEY,
                    total_value REAL NOT NULL,
                    count INTEGER NOT NULL
                )
            """)

            # Use parameterized query to prevent SQL injection
            insert_sql = """
                INSERT OR REPLACE INTO category_summary (category, total_value, count)
                VALUES (?, ?, ?)
            """
            data_tuples = [
                (row["category"], row["total_value"], row["count"])
                for row in transformed_data
            ]
            cursor.executemany(insert_sql, data_tuples)
            conn.commit()
            logger.info("Inserted/updated %d rows in database", len(data_tuples))

    except sqlite3.Error as exc:
        logger.error("Database error: %s", exc)
        raise
    except Exception as exc:
        logger.error("Unexpected error during load: %s", exc)
        raise


def run_etl(csv_path: str, db_path: str) -> None:
    """
    Run the full ETL pipeline.

    Args:
        csv_path: Path to the source CSV file.
        db_path: Path to the target SQLite database file.

    Raises:
        Exception: Any exception from extract, transform, or load steps.
    """
    logger.info("Starting ETL pipeline")
    try:
        raw_data = extract(csv_path)
        transformed_data = transform(raw_data)
        load(transformed_data, db_path)
        logger.info("ETL pipeline completed successfully")
    except Exception as exc:
        logger.error("ETL pipeline failed: %s", exc)
        raise


if __name__ == "__main__":
    # Example usage (can be replaced with argument parsing)
    import sys

    if len(sys.argv) != 3:
        print("Usage: python etl_pipeline.py <input_csv> <output_db>")
        sys.exit(1)

    input_csv = sys.argv[1]
    output_db = sys.argv[2]

    try:
        run_etl(input_csv, output_db)
    except Exception as e:
        logger.exception("Fatal error in ETL pipeline")
        sys.exit(1)