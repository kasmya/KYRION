"""
ETL Pipeline Module

Extracts data from a CSV file, transforms it by cleaning and aggregating,
and loads the result into a SQLite database.

Author: ETL Pipeline Generator
Version: 1.0.0
"""

import csv
import sqlite3
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def extract_from_csv(file_path: str) -> List[Dict[str, str]]:
    """
    Extract data from a CSV file and return it as a list of dictionaries.

    Args:
        file_path: Path to the CSV file to extract data from.

    Returns:
        A list of dictionaries where each dictionary represents a row
        with column headers as keys.

    Raises:
        FileNotFoundError: If the specified file does not exist.
        ValueError: If the CSV file is malformed or empty.
        PermissionError: If the file cannot be read due to permissions.
    """
    file_path_obj = Path(file_path)

    if not file_path_obj.exists():
        logger.error(f"File not found: {file_path}")
        raise FileNotFoundError(f"CSV file not found: {file_path}")

    if not file_path_obj.is_file():
        logger.error(f"Path is not a file: {file_path}")
        raise ValueError(f"Path is not a file: {file_path}")

    try:
        with open(file_path_obj, 'r', encoding='utf-8', newline='') as csvfile:
            reader = csv.DictReader(csvfile)
            data = list(reader)

            if not data:
                logger.error(f"CSV file is empty: {file_path}")
                raise ValueError(f"CSV file is empty: {file_path}")

            logger.info(f"Successfully extracted {len(data)} rows from {file_path}")
            return data

    except PermissionError as e:
        logger.error(f"Permission denied when reading file: {file_path} - {str(e)}")
        raise
    except csv.Error as e:
        logger.error(f"CSV parsing error in file {file_path}: {str(e)}")
        raise ValueError(f"Malformed CSV file: {str(e)}")
    except UnicodeDecodeError as e:
        logger.error(f"Encoding error in file {file_path}: {str(e)}")
        raise ValueError(f"File encoding error: {str(e)}")


def transform_data(data: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    """
    Transform and clean the extracted data.

    Performs the following operations:
    - Strips whitespace from all string values
    - Converts numeric fields to appropriate types
    - Filters out rows with missing required fields
    - Aggregates data by category (sum of amounts)

    Args:
        data: List of dictionaries containing raw CSV data.

    Returns:
        List of dictionaries with cleaned and aggregated data.

    Raises:
        ValueError: If transformation fails due to invalid data types.
    """
    if not data:
        logger.warning("No data to transform")
        return []

    transformed_data = []
    skipped_rows = 0

    for row in data:
        try:
            # Strip whitespace from all string values
            cleaned_row = {}
            for key, value in row.items():
                if value is not None:
                    cleaned_row[key] = value.strip()
                else:
                    cleaned_row[key] = value

            # Validate required fields
            required_fields = ['category', 'amount']
            missing_fields = [field for field in required_fields if not cleaned_row.get(field)]

            if missing_fields:
                logger.debug(f"Skipping row due to missing required fields: {missing_fields}")
                skipped_rows += 1
                continue

            # Convert amount to float
            try:
                amount = float(cleaned_row['amount'])
            except (ValueError, TypeError) as e:
                logger.debug(f"Skipping row due to invalid amount: {cleaned_row.get('amount')}")
                skipped_rows += 1
                continue

            # Convert date if present
            date_value = None
            if 'date' in cleaned_row and cleaned_row['date']:
                try:
                    # Try multiple date formats for flexibility
                    date_value = _parse_date(cleaned_row['date'])
                except ValueError:
                    logger.debug(f"Could not parse date: {cleaned_row['date']}, skipping date field")

            transformed_row = {
                'category': cleaned_row['category'],
                'amount': amount,
                'date': date_value
            }

            # Include any additional fields
            for key, value in cleaned_row.items():
                if key not in transformed_row and key:
                    transformed_row[key] = value

            transformed_data.append(transformed_row)

    logger.info(f"Transformed {len(transformed_data)} rows, skipped {skipped_rows} rows")

    # Aggregate by category if there are records
    if transformed_data:
        aggregated_data = _aggregate_by_category(transformed_data)
        logger.info(f"Aggregated into {len(aggregated_data)} categories")
        return aggregated_data
    else:
        return []


def _parse_date(date_string: str) -> Optional[str]:
    """
    Parse a date string into ISO format (YYYY-MM-DD).

    Args:
        date_string: Date string to parse.

    Returns:
        ISO formatted date string or None if parsing fails.

    Raises:
        ValueError: If the date string cannot be parsed.
    """
    date_formats = [
        '%Y-%m-%d',
        '%m/%d/%Y',
        '%d/%m/%Y',
        '%Y/%m/%d',
        '%m-%d-%Y',
        '%d-%m-%Y'
    ]

    for fmt in date_formats:
        try:
            parsed_date = datetime.strptime(date_string, fmt)
            return parsed_date.strftime('%Y-%m-%d')
        except ValueError:
            continue

    raise ValueError(f"Unable to parse date: {date_string}")


def _aggregate_by_category(data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Aggregate data by category, summing amounts.

    Args:
        data: List of transformed data dictionaries.

    Returns:
        List of dictionaries with aggregated data by category.
    """
    category_map: Dict[str, Dict[str, Any]] = {}

    for row in data:
        category = row['category']

        if category not in category_map:
            category_map[category] = {
                'category': category,
                'total_amount': 0.0,
                'count': 0,
                'earliest_date': None,
                'latest_date': None
            }

        category_map[category]['total_amount'] += row['amount']
        category_map[category]['count'] += 1

        # Track date range if dates are present
        if row.get('date'):
            if (category_map[category]['earliest_date'] is None or
                    row['date'] < category_map[category]['earliest_date']):
                category_map[category]['earliest_date'] = row['date']

            if (category_map[category]['latest_date'] is None or
                    row['date'] > category_map[category]['latest_date']):
                category_map[category]['latest_date'] = row['date']

    # Round total_amount to 2 decimal places
    for cat_data in category_map.values():
        cat_data['total_amount'] = round(cat_data['total_amount'], 2)

    return list(category_map.values())


def load_to_sqlite(data: List[Dict[str, Any]], db_path: str) -> None:
    """
    Load transformed data into a SQLite database.

    Creates a table 'category_aggregates' and inserts the aggregated data.
    Uses parameterized queries to prevent SQL injection.

    Args:
        data: List of dictionaries containing transformed data.
        db_path: Path to the SQLite database file.

    Raises:
        sqlite3.Error: If database operations fail.
        PermissionError: If the database file cannot be created/written.
    """
    if not data:
        logger.warning("No data to load into database")
        return

    # Validate database path
    db_path_obj = Path(db_path)
    if not db_path_obj.parent.exists():
        logger.error(f"Directory for database does not exist: {db_path_obj.parent}")
        raise FileNotFoundError(f"Directory does not exist: {db_path_obj.parent}")

    connection = None
    try:
        # Connect to database with proper isolation level
        connection = sqlite3.connect(str(db_path_obj))
        connection.row_factory = sqlite3.Row
        cursor = connection.cursor()

        # Create table with appropriate schema
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS category_aggregates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL UNIQUE,
                total_amount REAL NOT NULL,
                count INTEGER NOT NULL,
                earliest_date TEXT,
                latest_date TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Insert data using parameterized query to prevent SQL injection
        insert_query = """
            INSERT OR REPLACE INTO category_aggregates 
            (category, total_amount, count, earliest_date, latest_date)
            VALUES (?, ?, ?, ?, ?)
        """

        rows_inserted = 0
        for row in data:
            try:
                cursor.execute(insert_query, (
                    row['category'],
                    row['total_amount'],
                    row['count'],
                    row.get('earliest_date'),
                    row.get('latest_date')
                ))
                rows_inserted += 1
            except sqlite3.IntegrityError as e:
                logger.warning(f"Skipping duplicate category: {row['category']} - {str(e)}")

        connection.commit()
        logger.info(f"Successfully loaded {rows_inserted} rows into {db_path}")

    except sqlite3.OperationalError as e:
        logger.error(f"Database operational error: {str(e)}")
        if connection:
            connection.rollback()
        raise
    except PermissionError as e:
        logger.error(f"Permission denied for database file: {db_path} - {str(e)}")
        raise
    finally:
        if connection:
            connection.close()


def run_etl_pipeline(csv_path: str, db_path: str) -> Dict[str, Any]:
    """
    Execute the complete ETL pipeline: extract, transform, load.

    Args:
        csv_path: Path to the source CSV file.
        db_path: Path to the target SQLite database.

    Returns:
        Dictionary containing pipeline execution statistics.

    Raises:
        Exception: If any step of the pipeline fails.
    """
    logger.info(f"Starting ETL pipeline: {csv_path} -> {db_path}")

    stats = {
        'status': 'success',
        'extracted_rows': 0,
        'transformed_rows': 0,
        'loaded_rows': 0,
        'errors': []
    }

    try:
        # Extract
        logger.info("Extracting data...")
        raw_data = extract_from_csv(csv_path)
        stats['extracted_rows'] = len(raw_data)

        # Transform
        logger.info("Transforming data...")
        transformed_data = transform_data(raw_data)
        stats['transformed_rows'] = len(transformed_data)

        # Load
        logger.info("Loading data...")
        load_to_sqlite(transformed_data, db_path)
        stats['loaded_rows'] = len(transformed_data)

        logger.info("ETL pipeline completed successfully")

    except Exception as e:
        stats['status'] = 'failed'
        stats['errors'].append(str(e))
        logger.error(f"ETL pipeline failed: {str(e)}")
        raise

    return stats


# Alias for backward compatibility
extract_from_csv = extract_Extract
load_to_sqlite = load_to_sqlite


if __name__ == "__main__":
    # Example usage
    try:
        result = run_etl_pipeline("input.csv", "output.db")
        print(f"ETL completed: {result}")
    except Exception as e:
        print(f"ETL failed: {e}")