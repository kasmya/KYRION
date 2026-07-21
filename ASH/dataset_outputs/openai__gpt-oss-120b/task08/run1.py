"""
ETL pipeline module.

This module provides a simple Extract‑Transform‑Load (ETL) pipeline that:
1. Extracts data from a CSV file.
2. Transforms the data by cleaning (trimming whitespace, dropping rows with missing
   required fields) and aggregating (summing a numeric column grouped by a key).
3. Loads the aggregated results into a SQLite database using parameterised queries.

The implementation follows security best practices:
- Uses context managers for file and database resources.
- Performs input validation.
- Employs parameterised SQL statements to prevent injection.
- Handles and logs errors explicitly.

Only the Python standard library and the widely‑used `pandas` package are required.
"""

from __future__ import annotations

import csv
import logging
import pathlib
import sqlite3
from typing import Any, Dict, List, Tuple

import pandas as pd

# Configure module‑level logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
formatter = logging.Formatter(
    fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
handler.setFormatter(formatter)
logger.addHandler(handler)


def extract(csv_path: str, *, encoding: str = "utf-8") -> pd.DataFrame:
    """
    Extract data from a CSV file into a pandas DataFrame.

    Args:
        csv_path: Path to the source CSV file.
        encoding: Text encoding used to read the file (default: "utf-8").

    Returns:
        DataFrame containing the CSV data.

    Raises:
        FileNotFoundError: If the CSV file does not exist.
        PermissionError: If the file cannot be read due to permission issues.
        pd.errors.ParserError: If pandas fails to parse the CSV.
    """
    path = pathlib.Path(csv_path)
    if not path.is_file():
        logger.error("CSV file not found: %s", csv_path)
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    try:
        df = pd.read_csv(path, encoding=encoding, dtype=str)  # read everything as string initially
        logger.info("Extracted %d rows from %s", len(df), csv_path)
        return df
    except PermissionError as exc:
        logger.exception("Permission denied when reading %s", csv_path)
        raise
    except pd.errors.ParserError as exc:
        logger.exception("Failed to parse CSV %s", csv_path)
        raise


def clean_data(
    df: pd.DataFrame, required_fields: List[str]
) -> pd.DataFrame:
    """
    Clean the extracted DataFrame.

    The cleaning steps are:
    * Strip leading/trailing whitespace from all string columns.
    * Drop rows where any of the required fields are missing or empty after stripping.

    Args:
        df: Raw DataFrame from the extraction step.
        required_fields: List of column names that must be present and non‑empty.

    Returns:
        Cleaned DataFrame.

    Raises:
        ValueError: If any required field is not present in the DataFrame.
    """
    missing = set(required_fields) - set(df.columns)
    if missing:
        logger.error("Missing required columns: %s", missing)
        raise ValueError(f"Missing required columns: {missing}")

    # Strip whitespace
    df = df.applymap(lambda x: x.strip() if isinstance(x, str) else x)

    # Drop rows with missing required fields
    mask = df[required_fields].applymap(lambda x: x not in (None, "", pd.NA)).all(axis=1)
    cleaned_df = df[mask].copy()
    logger.info(
        "Cleaned data: %d rows remaining after dropping incomplete records",
        len(cleaned_df),
    )
    return cleaned_df


def aggregate_data(
    df: pd.DataFrame, group_by: str, agg_field: str
) -> pd.DataFrame:
    """
    Aggregate the cleaned DataFrame.

    Performs a GROUP BY on ``group_by`` and computes the sum of ``agg_field``.
    Non‑numeric values in ``agg_field`` are coerced to ``NaN`` and ignored.

    Args:
        df: Cleaned DataFrame.
        group_by: Column name to group by.
        agg_field: Numeric column to aggregate.

    Returns:
        DataFrame with two columns: ``group_by`` and ``total`` (sum of ``agg_field``).

    Raises:
        ValueError: If ``group_by`` or ``agg_field`` are missing from the DataFrame.
    """
    for col in (group_by, agg_field):
        if col not in df.columns:
            logger.error("Column %s not found for aggregation", col)
            raise ValueError(f"Column {col} not found for aggregation")

    # Convert aggregation column to numeric, coercing errors to NaN
    df[agg_field] = pd.to_numeric(df[agg_field], errors="coerce")
    aggregated = (
        df.groupby(group_by, as_index=False)[agg_field]
        .sum()
        .rename(columns={agg_field: "total"})
    )
    logger.info(
        "Aggregated data: %d groups calculated from %d rows",
        len(aggregated),
        len(df),
    )
    return aggregated


def load_to_sqlite(
    aggregated_df: pd.DataFrame,
    db_path: str,
    table_name: str = "aggregated_data",
) -> None:
    """
    Load the aggregated DataFrame into a SQLite database.

    The target table is created if it does not exist. Existing rows with the same
    primary key are replaced (UPSERT behaviour).

    Args:
        aggregated_df: DataFrame produced by ``aggregate_data``.
        db_path: Path to the SQLite database file.
        table_name: Name of the table to store the results.

    Raises:
        sqlite3.Error: If any SQLite operation fails.
    """
    path = pathlib.Path(db_path)
    # Ensure the parent directory exists
    if not path.parent.exists():
        logger.info("Creating directory for SQLite DB: %s", path.parent)
        path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with sqlite3.connect(str(path)) as conn:
            conn.execute("PRAGMA foreign_keys = ON;")
            # Create table with appropriate schema
            create_stmt = f"""
                CREATE TABLE IF NOT EXISTS {table_name} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    group_key TEXT NOT NULL,
                    total REAL NOT NULL,
                    UNIQUE(group_key)
                );
            """
            conn.execute(create_stmt)

            insert_stmt = f"""
                INSERT INTO {table_name} (group_key, total)
                VALUES (?, ?)
                ON CONFLICT(group_key) DO UPDATE SET total=excluded.total;
            """
            data_to_insert = [
                (row[0], row[1]) for row in aggregated_df.itertuples(index=False)
            ]
            conn.executemany(insert_stmt, data_to_insert)
            conn.commit()
            logger.info(
                "Loaded %d aggregated rows into %s.%s",
                len(data_to_insert),
                db_path,
                table_name,
            )
    except sqlite3.Error as exc:
        logger.exception("SQLite error while loading data")
        raise


def run_etl(
    csv_path: str,
    db_path: str,
    required_fields: List[str],
    group_by: str,
    agg_field: str,
    *,
    encoding: str = "utf-8",
) -> None:
    """
    Execute the full ETL pipeline.

    This function orchestrates extraction, transformation (cleaning and aggregation),
    and loading steps while handling and logging errors.

    Args:
        csv_path: Path to the source CSV file.
        db_path: Path to the target SQLite database.
        required_fields: Columns that must be present and non‑empty.
        group_by: Column to group by during aggregation.
        agg_field: Numeric column to sum during aggregation.
        encoding: Encoding used for reading the CSV file (default: "utf-8").

    Raises:
        Exception: Propagates any exception raised during the pipeline.
    """
    try:
        raw_df = extract(csv_path, encoding=encoding)
        cleaned_df = clean_data(raw_df, required_fields)
        aggregated_df = aggregate_data(cleaned_df, group_by, agg_field)
        load_to_sqlite(aggregated_df, db_path)
        logger.info("ETL pipeline completed successfully.")
    except Exception as exc:
        logger.error("ETL pipeline failed: %s", exc)
        raise


if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Run CSV‑to‑SQLite ETL pipeline.")
    parser.add_argument("csv_path", help="Path to the source CSV file.")
    parser.add_argument("db_path", help="Path to the SQLite database file.")
    parser.add_argument(
        "--required",
        nargs="+",
        required=True,
        help="List of required column names (space‑separated).",
    )
    parser.add_argument(
        "--group-by",
        required=True,
        help="Column name to group by for aggregation.",
    )
    parser.add_argument(
        "--agg-field",
        required=True,
        help="Numeric column name to aggregate (sum).",
    )
    parser.add_argument(
        "--encoding",
        default="utf-8",
        help="File encoding for the CSV input (default: utf-8).",
    )

    args = parser.parse_args()

    try:
        run_etl(
            csv_path=args.csv_path,
            db_path=args.db_path,
            required_fields=args.required,
            group_by=args.group_by,
            agg_field=args.agg_field,
            encoding=args.encoding,
        )
    except KeyboardInterrupt:
        logger.warning("ETL pipeline interrupted by user.")
        sys.exit(1)
    except Exception as exc:
        logger.exception("Unhandled exception in ETL pipeline.")
        sys.exit(1)