"""ETL pipeline module.

This module provides a simple Extract‑Transform‑Load (ETL) pipeline that:

1. Extracts data from a CSV file.
2. Transforms the data by cleaning and aggregating it.
3. Loads the transformed data into a SQLite database.

Only the Python standard library and the widely‑used ``pandas`` package are used.
All functions include type hints, docstrings, and explicit error handling.
Security best practices such as parameterised SQL statements and safe file handling are applied.
"""

from __future__ import annotations

import csv
import logging
import sqlite3
from pathlib import Path
from typing import Any, List

import pandas as pd

__all__: List[str] = ["extract", "transform", "load", "run_etl"]

# Configure a basic logger for the module.
logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def extract(csv_path: Path) -> pd.DataFrame:
    """Extract data from a CSV file into a pandas DataFrame.

    Args:
        csv_path: Path to the source CSV file.

    Returns:
        DataFrame containing the CSV data.

    Raises:
        FileNotFoundError: If the CSV file does not exist.
        pd.errors.EmptyDataError: If the CSV file is empty.
        pd.errors.ParserError: If the CSV cannot be parsed.
    """
    logger.info("Starting extraction from %s", csv_path)
    if not csv_path.is_file():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    try:
        df = pd.read_csv(csv_path, dtype=str)  # read everything as string initially
        logger.debug("Extracted %d rows", len(df))
        return df
    except pd.errors.EmptyDataError as exc:
        logger.error("CSV file is empty: %s", csv_path)
        raise
    except pd.errors.ParserError as exc:
        logger.error("Failed to parse CSV file: %s", csv_path)
        raise


def _clean_string_series(series: pd.Series) -> pd.Series:
    """Strip whitespace from string series and convert empty strings to NaN."""
    return series.str.strip().replace("", pd.NA)


def transform(df: pd.DataFrame) -> pd.DataFrame:
    """Clean and aggregate the extracted DataFrame.

    The transformation performs the following steps:
    1. Trim whitespace from all string columns.
    2. Convert empty strings to missing values (NaN).
    3. Drop rows where required columns are missing.
    4. Cast numeric columns to appropriate dtypes.
    5. Aggregate numeric ``value`` column by ``category`` using sum.

    Expected input columns:
        - ``category`` (string, grouping key)
        - ``value`` (numeric, values to aggregate)

    Args:
        df: Raw DataFrame from the extraction step.

    Returns:
        Aggregated DataFrame with columns ``category`` and ``total_value``.

    Raises:
        ValueError: If required columns are missing.
    """
    logger.info("Starting transformation")
    required_columns = {"category", "value"}
    missing = required_columns - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    # Clean string columns.
    for col in df.select_dtypes(include=["object"]).columns:
        df[col] = _clean_string_series(df[col])

    # Drop rows where category or value is missing.
    df_clean = df.dropna(subset=["category", "value"])
    logger.debug("Rows after dropping missing: %d", len(df_clean))

    # Convert value to numeric, coercing errors to NaN then dropping.
    df_clean["value"] = pd.to_numeric(df_clean["value"], errors="coerce")
    df_clean = df_clean.dropna(subset=["value"])
    logger.debug("Rows after numeric conversion: %d", len(df_clean))

    # Aggregate.
    aggregated = (
        df_clean.groupby("category", as_index=False)
        .agg(total_value=("value", "sum"))
        .sort_values("category")
    )
    logger.info("Transformation complete, %d aggregated rows", len(aggregated))
    return aggregated


def load(df: pd.DataFrame, db_path: Path, table_name: str = "aggregated_data") -> None:
    """Load the transformed DataFrame into a SQLite database.

    The function creates the target table if it does not exist and inserts the
    rows using a parameterised ``INSERT`` statement to avoid SQL injection.

    Args:
        df: DataFrame produced by the ``transform`` step.
        db_path: Path to the SQLite database file.
        table_name: Name of the table to store the data.

    Raises:
        sqlite3.DatabaseError: If any database operation fails.
    """
    logger.info("Starting load into database %s, table %s", db_path, table_name)
    try:
        conn = sqlite3.connect(db_path)
    except sqlite3.Error as exc:
        logger.exception("Failed to connect to SQLite database")
        raise

    try:
        with conn:
            # Create table if it does not exist.
            create_sql = f"""
                CREATE TABLE IF NOT EXISTS {table_name} (
                    category TEXT PRIMARY KEY,
                    total_value REAL NOT NULL
                );
            """
            conn.execute(create_sql)

            # Insert or replace rows.
            insert_sql = f"""
                INSERT INTO {table_name} (category, total_value)
                VALUES (?, ?)
                ON CONFLICT(category) DO UPDATE SET
                    total_value=excluded.total_value;
            """
            rows = df.itertuples(index=False, name=None)
            conn.executemany(insert_sql, rows)
            logger.info("Inserted %d rows into %s", df.shape[0], table_name)
    except sqlite3.Error as exc:
        logger.exception("Database operation failed")
        raise
    finally:
        conn.close()
        logger.debug("Database connection closed")


def run_etl(csv_path: Path, db_path: Path, table_name: str = "aggregated_data") -> None:
    """Convenient wrapper to run the full ETL pipeline.

    Args:
        csv_path: Path to the source CSV file.
        db_path: Path to the destination SQLite database file.
        table_name: Target table name for loading.

    Raises:
        Exception: Propagates any exception raised by the pipeline steps.
    """
    logger.info("ETL pipeline started")
    try:
        raw_df = extract(csv_path)
        transformed_df = transform(raw_df)
        load(transformed_df, db_path, table_name)
        logger.info("ETL pipeline completed successfully")
    except Exception as exc:
        logger.error("ETL pipeline failed: %s", exc)
        raise