"""ETL Pipeline: Extract from CSV, transform (clean and aggregate), load into SQLite.

This module provides a self-contained ETL pipeline using only the Python standard library.
It includes explicit error handling, type hints, and comprehensive docstrings.
"""

import csv
import sqlite3
import os
from typing import List, Dict, Any, Optional


def extract(csv_path: str) -> List[Dict[str, Any]]:
    """Extract data from a CSV file.

    Args:
        csv_path: Path to the CSV file.

    Returns:
        List of dictionaries representing rows, with keys from the header.

    Raises:
        FileNotFoundError: If the CSV file does not exist.
        PermissionError: If the file cannot be read.
        csv.Error: If the CSV is malformed.
    """
    if not os.path.isfile(csv_path):
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    data: List[Dict[str, Any]] = []
    try:
        with open(csv_path, mode="r", newline="", encoding="utf-8") as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                data.append(row)
    except PermissionError as exc:
        raise PermissionError(f"Permission denied reading {csv_path}") from exc
    except csv.Error as exc:
        raise csv.Error(f"Error parsing CSV file {csv_path}: {exc}") from exc

    return data


def transform(
    data: List[Dict[str, Any]],
    group_by: str,
    aggregate_column: str,
    *,
    fill_missing: Optional[Any] = None,
) -> List[Dict[str, Any]]:
    """Clean and aggregate the extracted data.

    Cleaning steps:
    - Strip whitespace from string values.
    - Convert numeric strings to float where possible.
    - Replace missing values (empty strings) with `fill_missing` (default None).

    Aggregation:
    - Group by `group_by` column.
    - Compute sum of `aggregate_column` for each group.

    Args:
        data: List of row dictionaries from extract().
        group_by: Column name to group by.
        aggregate_column: Column name to sum.
        fill_missing: Value to substitute for missing/empty fields.

    Returns:
        List of dictionaries with keys: group_by column and aggregated sum.

    Raises:
        ValueError: If required columns are missing or aggregation column non-numeric.
    """
    if not data:
        return []

    # Validate columns exist
    first_row = data[0]
    if group_by not in first_row:
        raise ValueError(f"Group-by column '{group_by}' not found in data")
    if aggregate_column not in first_row:
        raise ValueError(f"Aggregate column '{aggregate_column}' not found in data")

    cleaned: List[Dict[str, Any]] = []
    for row in data:
        cleaned_row: Dict[str, Any] = {}
        for key, value in row.items():
            # Strip whitespace from strings
            if isinstance(value, str):
                value = value.strip()
                if value == "":
                    value = fill_missing
            # Attempt numeric conversion for aggregate column
            if key == aggregate_column and value is not None:
                try:
                    value = float(value)
                except ValueError as exc:
                    raise ValueError(
                        f"Non-numeric value '{value}' in aggregate column '{aggregate_column}'"
                    ) from exc
            cleaned_row[key] = value
        cleaned.append(cleaned_row)

    # Aggregate
    aggregates: Dict[Any, float] = {}
    for row in cleaned:
        group_val = row[group_by]
        agg_val = row[aggregate_column]
        if agg_val is None:
            continue
        aggregates[group_val] = aggregates.get(group_val, 0.0) + agg_val

    # Build result
    result = [
        {group_by: group, aggregate_column: total}
        for group, total in aggregates.items()
    ]
    return result


def load(
    data: List[Dict[str, Any]],
    db_path: str,
    table_name: str,
    *,
    if_exists: str = "replace",
) -> None:
    """Load transformed data into a SQLite database.

    Args:
        data: List of dictionaries from transform().
        db_path: Path to SQLite database file.
        table_name: Name of the table to create/populate.
        if_exists: Behavior if table exists: 'replace' (drop and recreate), 'append', or 'fail'.

    Raises:
        ValueError: If `if_exists` is not one of the allowed values.
        sqlite3.Error: For any database operation errors.
    """
    allowed_if_exists = {"replace", "append", "fail"}
    if if_exists not in allowed_if_exists:
        raise ValueError(f"if_exists must be one of {allowed_if_exists}")

    if not data:
        return

    # Determine columns from first row
    columns = list(data[0].keys())
    col_defs = ", ".join([f'"{col}" TEXT' for col in columns])  # Use TEXT for simplicity
    placeholders = ", ".join(["?" for _ in columns])
    insert_sql = f'INSERT INTO "{table_name}" ({", ".join(f\'"{c}"\' for c in columns)}) VALUES ({placeholders})'

    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()

            if if_exists == "replace":
                cursor.execute(f'DROP TABLE IF EXISTS "{table_name}"')
                cursor.execute(f'CREATE TABLE "{table_name}" ({col_defs})')
            elif if_exists == "fail":
                cursor.execute(
                    f'SELECT name FROM sqlite_master WHERE type="table" AND name=?', (table_name,)
                )
                if cursor.fetchone():
                    raise sqlite3.Error(f"Table '{table_name}' already exists")
                cursor.execute(f'CREATE TABLE "{table_name}" ({col_defs})')
            else:  # append
                cursor.execute(
                    f'SELECT name FROM sqlite_master WHERE type="table" AND name=?', (table_name,)
                )
                if not cursor.fetchone():
                    cursor.execute(f'CREATE TABLE "{table_name}" ({col_defs})')

            # Insert rows
            for row in data:
                values = [row[col] for col in columns]
                cursor.execute(insert_sql, values)
            conn.commit()
    except sqlite3.Error as exc:
        raise sqlite3.Error(f"Database error: {exc}") from exc


def run_etl(
    csv_path: str,
    db_path: str,
    table_name: str,
    group_by: str,
    aggregate_column: str,
    *,
    fill_missing: Optional[Any] = None,
    if_exists: str = "replace",
) -> None:
    """Run the full ETL pipeline.

    Args:
        csv_path: Path to source CSV file.
        db_path: Path to target SQLite database.
        table_name: Name of the table to load data into.
        group_by: Column to group by during aggregation.
        aggregate_column: Column to sum during aggregation.
        fill_missing: Value to use for missing fields during cleaning.
        if_exists: Table existence behavior ('replace', 'append', 'fail').

    Raises:
        FileNotFoundError: If CSV file not found.
        PermissionError: If CSV file cannot be read.
        csv.Error: If CSV is malformed.
        ValueError: If columns missing or non-numeric aggregate values.
        sqlite3.Error: If database operations fail.
    """
    raw_data = extract(csv_path)
    transformed_data = transform(
        raw_data, group_by, aggregate_column, fill_missing=fill_missing
    )
    load(transformed_data, db_path, table_name, if_exists=if_exists)


if __name__ == "__main__":
    # Example usage (can be removed or adapted for CLI)
    import sys

    if len(sys.argv) != 6:
        print(
            "Usage: python etl.py <csv_path> <db_path> <table_name> <group_by> <aggregate_column>",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        run_etl(
            csv_path=sys.argv[1],
            db_path=sys.argv[2],
            table_name=sys.argv[3],
            group_by=sys.argv[4],
            aggregate_column=sys.argv[5],
        )
        print("ETL completed successfully.")
    except Exception as exc:
        print(f"ETL failed: {exc}", file=sys.stderr)
        sys.exit(1)