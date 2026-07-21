"""ETL Pipeline: Extract from CSV, Transform (clean and aggregate), Load into SQLite.

This module provides a self-contained ETL pipeline using only the Python standard library.
It includes extraction from a CSV file, data cleaning and aggregation, and loading into a SQLite database.
"""

import csv
import logging
import sqlite3
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class ETLError(Exception):
    """Base exception for ETL pipeline errors."""
    pass


class ExtractError(ETLError):
    """Exception raised during data extraction."""
    pass


class TransformError(ETLError):
    """Exception raised during data transformation."""
    pass


class LoadError(ETLError):
    """Exception raised during data loading."""
    pass


def extract_csv(file_path: Union[str, Path]) -> List[Dict[str, Any]]:
    """Extract data from a CSV file.

    Args:
        file_path: Path to the CSV file.

    Returns:
        List of dictionaries representing rows, with column headers as keys.

    Raises:
        ExtractError: If the file cannot be read or parsed.
    """
    path = Path(file_path)
    if not path.is_file():
        raise ExtractError(f"CSV file not found: {path}")

    try:
        with path.open(mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            data = [row for row in reader]
        logger.info("Extracted %d rows from %s", len(data), path)
        return data
    except (csv.Error, OSError, UnicodeDecodeError) as exc:
        raise ExtractError(f"Failed to extract CSV data: {exc}") from exc


def clean_row(row: Dict[str, Any], cleaners: Optional[Dict[str, Callable[[str], Any]]] = None) -> Dict[str, Any]:
    """Clean a single row by applying optional type conversion functions.

    Args:
        row: Dictionary representing a row.
        cleaners: Optional mapping of column names to cleaning functions.

    Returns:
        Cleaned row dictionary.
    """
    if cleaners is None:
        return row

    cleaned = {}
    for key, value in row.items():
        if key in cleaners:
            try:
                cleaned[key] = cleaners[key](value)
            except (ValueError, TypeError) as exc:
                logger.warning("Cleaning failed for column '%s' value '%s': %s", key, value, exc)
                cleaned[key] = None
        else:
            cleaned[key] = value
    return cleaned


def aggregate_data(
    data: List[Dict[str, Any]],
    group_by: str,
    agg_column: str,
    agg_func: Callable[[List[Any]], Any]
) -> List[Dict[str, Any]]:
    """Aggregate data by grouping and applying an aggregation function.

    Args:
        data: List of cleaned row dictionaries.
        group_by: Column name to group by.
        agg_column: Column name to aggregate.
        agg_func: Function that takes a list of values and returns an aggregated result.

    Returns:
        List of dictionaries with group_by column and aggregated value.

    Raises:
        TransformError: If group_by or agg_column not present in data.
    """
    if not data:
        return []

    if group_by not in data[0] or agg_column not in data[0]:
        raise TransformError(f"Columns '{group_by}' or '{agg_column}' not found in data")

    groups: Dict[Any, List[Any]] = {}
    for row in data:
        key = row[group_by]
        val = row[agg_column]
        if val is None or val == "":
            continue
        groups.setdefault(key, []).append(val)

    aggregated = []
    for key, values in groups.items():
        try:
            agg_value = agg_func(values)
        except Exception as exc:
            logger.warning("Aggregation failed for group '%s': %s", key, exc)
            agg_value = None
        aggregated.append({group_by: key, f"{agg_func.__name__}_{agg_column}": agg_value})

    logger.info("Aggregated into %d groups", len(aggregated))
    return aggregated


def transform_data(
    raw_data: List[Dict[str, Any]],
    cleaners: Optional[Dict[str, Callable[[str], Any]]] = None,
    group_by: Optional[str] = None,
    agg_column: Optional[str] = None,
    agg_func: Optional[Callable[[List[Any]], Any]] = None
) -> List[Dict[str, Any]]:
    """Transform raw data by cleaning and optionally aggregating.

    Args:
        raw_data: List of raw row dictionaries from extraction.
        cleaners: Optional mapping of column names to cleaning functions.
        group_by: Optional column name to group by for aggregation.
        agg_column: Optional column name to aggregate.
        agg_func: Optional aggregation function (e.g., sum, len, lambda x: sum(x)/len(x)).

    Returns:
        Transformed data (cleaned rows or aggregated results).

    Raises:
        TransformError: If aggregation parameters are inconsistent.
    """
    # Clean all rows
    cleaned_data = [clean_row(row, cleaners) for row in raw_data]
    logger.info("Cleaned %d rows", len(cleaned_data))

    # Aggregate if requested
    if group_by and agg_column and agg_func:
        if not (group_by and agg_column and agg_func):
            raise TransformError("group_by, agg_column, and agg_func must all be provided for aggregation")
        return aggregate_data(cleaned_data, group_by, agg_column, agg_func)

    return cleaned_data


def load_to_sqlite(
    data: List[Dict[str, Any]],
    db_path: Union[str, Path],
    table_name: str,
    primary_key: Optional[str] = None
) -> None:
    """Load data into a SQLite database table.

    Args:
        data: List of dictionaries to insert.
        db_path: Path to SQLite database file.
        table_name: Name of the table to create/insert into.
        primary_key: Optional column name to set as primary key.

    Raises:
        LoadError: If database operations fail.
    """
    if not data:
        logger.warning("No data to load into %s", table_name)
        return

    path = Path(db_path)
    # Ensure parent directory exists
    path.parent.mkdir(parents=True, exist_ok=True)

    columns = list(data[0].keys())
    # Sanitize table and column names (basic validation)
    if not table_name.isidentifier():
        raise LoadError(f"Invalid table name: {table_name}")
    for col in columns:
        if not col.isidentifier():
            raise LoadError(f"Invalid column name: {col}")

    try:
        with sqlite3.connect(path) as conn:
            cursor = conn.cursor()

            # Build CREATE TABLE statement
            col_defs = []
            for col in columns:
                col_def = f'"{col}" TEXT'
                if primary_key and col == primary_key:
                    col_def += " PRIMARY KEY"
                col_defs.append(col_def)
            create_sql = f'CREATE TABLE IF NOT EXISTS "{table_name}" ({", ".join(col_defs)})'
            cursor.execute(create_sql)

            # Prepare INSERT statement
            placeholders = ", ".join(["?"] * len(columns))
            insert_sql = f'INSERT OR REPLACE INTO "{table_name}" ({", ".join(f\'"{c}"\' for c in columns)}) VALUES ({placeholders})'

            # Insert rows
            rows = [tuple(row[col] for col in columns) for row in data]
            cursor.executemany(insert_sql, rows)
            conn.commit()
        logger.info("Loaded %d rows into %s.%s", len(data), path, table_name)
    except sqlite3.Error as exc:
        raise LoadError(f"Failed to load data into SQLite: {exc}") from exc


def run_etl_pipeline(
    csv_path: Union[str, Path],
    db_path: Union[str, Path],
    table_name: str,
    cleaners: Optional[Dict[str, Callable[[str], Any]]] = None,
    group_by: Optional[str] = None,
    agg_column: Optional[str] = None,
    agg_func: Optional[Callable[[List[Any]], Any]] = None,
    primary_key: Optional[str] = None
) -> None:
    """Run the full ETL pipeline: extract, transform, load.

    Args:
        csv_path: Path to input CSV file.
        db_path: Path to output SQLite database.
        table_name: Name of the table to create in the database.
        cleaners: Optional column cleaning functions.
        group_by: Optional column to group by for aggregation.
        agg_column: Optional column to aggregate.
        agg_func: Optional aggregation function.
        primary_key: Optional primary key column for the table.

    Raises:
        ETLError: If any stage of the pipeline fails.
    """
    logger.info("Starting ETL pipeline: %s -> %s.%s", csv_path, db_path, table_name)

    try:
        raw_data = extract_csv(csv_path)
        transformed_data = transform_data(
            raw_data,
            cleaners=cleaners,
            group_by=group_by,
            agg_column=agg_column,
            agg_func=agg_func
        )
        load_to_sqlite(transformed_data, db_path, table_name, primary_key)
        logger.info("ETL pipeline completed successfully")
    except ETLError:
        logger.exception("ETL pipeline failed")
        raise


if __name__ == "__main__":
    # Example usage
    import sys

    def to_int(val: str) -> int:
        return int(val)

    def to_float(val: str) -> float:
        return float(val)

    # Example: aggregate sales by region
    example_cleaners = {
        "sales": to_float,
        "quantity": to_int,
    }

    if len(sys.argv) < 4:
        print("Usage: python etl_pipeline.py <csv_path> <db_path> <table_name>")
        sys.exit(1)

    run_etl_pipeline(
        csv_path=sys.argv[1],
        db_path=sys.argv[2],
        table_name=sys.argv[3],
        cleaners=example_cleaners,
        group_by="region",
        agg_column="sales",
        agg_func=sum,
        primary_key="region"
    )