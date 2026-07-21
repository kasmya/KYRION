"""
ETL Pipeline Module

Extracts data from a CSV file, transforms it by cleaning and aggregating,
and loads the results into a SQLite database.

Requirements:
- Python 3.8+
- Standard library only (csv, sqlite3, logging, pathlib, typing)
"""

import csv
import logging
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Configure module-level logger
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


def extract_csv(file_path: Path) -> List[Dict[str, str]]:
    """
    Extract data from a CSV file into a list of dictionaries.

    Args:
        file_path: Path to the CSV file.

    Returns:
        A list of dictionaries where keys are column headers and values are strings.

    Raises:
        FileNotFoundError: If the CSV file does not exist.
        PermissionError: If the file cannot be read due to permissions.
        csv.Error: If the CSV file is malformed.
    """
    if not file_path.is_file():
        raise FileNotFoundError(f"CSV file not found: {file_path}")

    logger.info("Extracting data from %s", file_path)
    rows: List[Dict[str, str]] = []
    try:
        with file_path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(row)
    except (PermissionError, FileNotFoundError) as e:
        logger.error("Cannot access file %s: %s", file_path, e)
        raise
    except csv.Error as e:
        logger.error("CSV parsing error in %s: %s", file_path, e)
        raise

    if not rows:
        logger.warning("No data rows found in %s", file_path)

    logger.info("Extracted %d rows", len(rows))
    return rows


def transform_clean(data: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    """
    Clean and transform raw CSV data.

    Steps performed:
    - Strip whitespace from all string values.
    - Convert numeric columns to float (if possible).
    - Drop rows with empty required fields: 'id', 'category', 'amount'.
    - Log and skip malformed rows.

    Args:
        data: Raw data as a list of dictionaries with string values.

    Returns:
        Cleaned and partially typed list of dictionaries.
    """
    required_cols = {"id", "category", "amount"}
    cleaned: List[Dict[str, Any]] = []
    skipped_count = 0

    for row_num, row in enumerate(data, start=2):  # header is row 1
        # Strip whitespace
        stripped = {k.strip(): v.strip() for k, v in row.items()}

        # Check required fields
        if not all(stripped.get(col) for col in required_cols):
            logger.warning("Row %d skipped: missing required fields", row_num)
            skipped_count += 1
            continue

        # Convert amount to float
        amount_str = stripped["amount"]
        try:
            amount = float(amount_str)
        except (ValueError, TypeError):
            logger.warning(
                "Row %d skipped: invalid amount '%s'", row_num, amount_str
            )
            skipped_count += 1
            continue

        cleaned.append(
            {
                "id": stripped["id"],
                "category": stripped["category"],
                "amount": amount,
                "description": stripped.get("description", ""),
            }
        )

    logger.info(
        "Transformed %d rows, skipped %d rows", len(cleaned), skipped_count
    )
    return cleaned


def transform_aggregate(
    cleaned_data: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Aggregate amounts by category.

    Args:
        cleaned_data: Cleaned data with 'category' and 'amount' fields.

    Returns:
        List of dictionaries with 'category' and 'total_amount' keys.
    """
    category_totals: Dict[str, float] = {}
    for row in cleaned_data:
        cat = row["category"]
        category_totals[cat] = category_totals.get(cat, 0.0) + row["amount"]

    aggregated = [
        {"category": cat, "total_amount": round(total, 2)}
        for cat, total in category_totals.items()
    ]
    logger.info("Aggregated into %d categories", len(aggregated))
    return aggregated


def load_to_sqlite(
    data: List[Dict[str, Any]],
    db_path: Path,
    table_name: str = "category_totals",
) -> None:
    """
    Load aggregated data into a SQLite database table.

    Creates the table if it does not exist. Replaces existing rows with the
    same category using INSERT OR REPLACE. Uses parameterized queries to
    prevent SQL injection.

    Args:
        data: Aggregated data rows.
        db_path: Path to the SQLite database file.
        table_name: Name of the target table.

    Raises:
        sqlite3.Error: If a database error occurs.
    """
    if not data:
        logger.warning("No data to load into %s", db_path)
        return

    logger.info("Loading data into %s table %s", db_path, table_name)

    try:
        with sqlite3.connect(str(db_path)) as conn:
            cursor = conn.cursor()

            # Create table with category as primary key to enable REPLACE
            cursor.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {table_name} (
                    category TEXT PRIMARY KEY,
                    total REAL NOT NULL
                )
                """
            )

            # Use parameterized query for safe insertion
            insert_query = f"INSERT OR REPLACE INTO {table_name} (category, total) VALUES (?, ?)"
            cursor.executemany(
                insert_query,
                [(row["category"], row["total"]) for row in data],
            )

            conn.commit()
            logger.info("Successfully loaded %d rows", len(data))
    except sqlite3.OperationalError as e:
        logger.error("Database operation failed: %s", e)
        raise
    except sqlite3.DatabaseError as e:
        logger.error("Database error: %s", e)
        raise


def run_etl(csv_path: Path, db_path: Path) -> None:
    """
    Execute the full ETL pipeline: extract, transform, aggregate, load.

    Args:
        csv_path: Path to the source CSV file.
        db_path: Path to the target SQLite database.
    """
    logger.info("Starting ETL pipeline: %s -> %s", csv_path, db_path)

    raw_data = extract_csv(csv_path)
    cleaned_data = transform_clean(raw_data)
    aggregated_data = transform_aggregate(cleaned_data)
    load_to_sqlite(aggregated_data, db_path)

    logger.info("ETL pipeline completed successfully")


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <csv_path> <db_path>")
        sys.exit(1)

    source_csv = Path(sys.argv[1])
    target_db = Path(sys.argv[2])

    try:
        run_etl(source_csv, target_db)
    except Exception as e:
        logger.exception("ETL pipeline failed: %s", e)
        sys.exit(1)