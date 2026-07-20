#!/usr/bin/env python3
"""
ETL pipeline:
  1. Extract – read a CSV file into a pandas DataFrame.
  2. Transform – clean data (type casting, whitespace trimming, null handling)
                 and aggregate (example: sum of numeric columns grouped by a key).
  3. Load – write the transformed data into a SQLite table using
            parameterised queries (security best‑practice).

Only the standard library, ``pandas`` and ``sqlite3`` are used.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Final, Iterable, List, Optional

import pandas as pd
import sqlite3

# --------------------------------------------------------------------------- #
# Configuration & Logging
# --------------------------------------------------------------------------- #

DEFAULT_CHUNK_SIZE: Final[int] = 100_000  # rows per CSV read chunk (if needed)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Custom Exceptions
# --------------------------------------------------------------------------- #


class ETLException(RuntimeError):
    """Base class for ETL related errors."""


# --------------------------------------------------------------------------- #
# Helper Functions
# --------------------------------------------------------------------------- #


def _validate_path(file_path: Path) -> None:
    """Ensure a path is absolute and points to an existing regular file."""
    if not file_path.is_absolute():
        raise ETLException(f"Path must be absolute: {file_path}")
    if not file_path.is_file():
        raise ETLException(f"File does not exist: {file_path}")


def _sanitize_column_name(name: str) -> str:
    """
    Return a safe SQLite column name:
      * Strip surrounding whitespace.
      * Replace spaces with underscores.
      * Remove characters other than alphanumerics and underscores.
    """
    clean = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in name.strip())
    return clean


# --------------------------------------------------------------------------- #
# ETL Steps
# --------------------------------------------------------------------------- #


def extract(csv_path: Path, *, encoding: str = "utf-8") -> pd.DataFrame:
    """
    Read a CSV file into a DataFrame.

    Parameters
    ----------
    csv_path: Path
        Absolute path to the CSV file.
    encoding: str, optional
        Encoding to use when reading the CSV (default "utf-8").

    Returns
    -------
    pd.DataFrame
        Raw data from the CSV.

    Raises
    ------
    ETLException
        If the file cannot be read.
    """
    _validate_path(csv_path)
    try:
        logger.info("Extracting data from %s", csv_path)
        df = pd.read_csv(csv_path, encoding=encoding, low_memory=False)
        logger.info("Extracted %d rows, %d columns", df.shape[0], df.shape[1])
        return df
    except Exception as exc:
        raise ETLException(f"Failed to read CSV at {csv_path}: {exc}") from exc


def _clean_string(series: pd.Series) -> pd.Series:
    """Trim whitespace and replace NaN with empty string."""
    return series.astype(str).str.strip().replace("nan", "")


def transform(df: pd.DataFrame) -> pd.DataFrame:
    """
    Clean and aggregate the raw DataFrame.

    Cleaning steps:
      * Strip whitespace from object columns.
      * Convert numeric columns to appropriate dtypes.
      * Drop rows where essential columns are missing.

    Aggregation example:
      * Group by a column named "category" (if present) and sum numeric columns.

    Parameters
    ----------
    df: pd.DataFrame
        DataFrame returned by ``extract``.

    Returns
    -------
    pd.DataFrame
        Cleaned and aggregated data ready for loading.
    """
    if df.empty:
        logger.warning("Received empty DataFrame – nothing to transform.")
        return df.copy()

    logger.info("Starting transformation of %d rows.", df.shape[0])
    df_clean = df.copy()

    # ------------------------------------------------------------------- #
    # 1. Sanitize column names for SQLite compatibility.
    # ------------------------------------------------------------------- #
    original_columns = df_clean.columns.tolist()
    sanitized = [_sanitize_column_name(col) for col in original_columns]
    df_clean.columns = sanitized
    logger.debug("Sanitized columns: %s", sanitized)

    # ------------------------------------------------------------------- #
    # 2. Clean string/object columns.
    # ------------------------------------------------------------------- #
    obj_cols = df_clean.select_dtypes(include=["object"]).columns
    for col in obj_cols:
        df_clean[col] = _clean_string(df_clean[col])
    logger.debug("Cleaned %d object columns.", len(obj_cols))

    # ------------------------------------------------------------------- #
    # 3. Convert numeric columns.
    # ------------------------------------------------------------------- #
    for col in df_clean.columns:
        # Skip if already numeric
        if pd.api.types.is_numeric_dtype(df_clean[col]):
            continue
        try:
            df_clean[col] = pd.to_numeric(df_clean[col], errors="coerce")
        except Exception:
            # Keep as original if conversion fails
            continue
    logger.debug("Converted columns to numeric where possible.")

    # ------------------------------------------------------------------- #
    # 4. Drop rows where essential data is missing.
    #    (Assume a column named 'id' or the first column is essential.)
    # ------------------------------------------------------------------- #
    essential = "id" if "id" in df_clean.columns else df_clean.columns[0]
    before_drop = df_clean.shape[0]
    df_clean = df_clean.dropna(subset=[essential])
    logger.info(
        "Dropped %d rows missing essential column '%s'.", before_drop - df_clean.shape[0], essential
    )

    # ------------------------------------------------------------------- #
    # 5. Example aggregation: group by 'category' if present.
    # ------------------------------------------------------------------- #
    if "category" in df_clean.columns:
        numeric_cols = df_clean.select_dtypes(include=["number"]).columns.tolist()
        agg_dict = {col: "sum" for col in numeric_cols if col != "category"}
        df_agg = (
            df_clean.groupby("category", as_index=False)
            .agg(agg_dict)
            .reset_index(drop=True)
        )
        logger.info("Aggregated data by 'category' – %d groups.", df_agg.shape[0])
        return df_agg

    # No aggregation needed – return cleaned dataframe.
    logger.info("Transformation complete – %d rows remain.", df_clean.shape[0])
    return df_clean


def load(
    df: pd.DataFrame,
    db_path: Path,
    table_name: str,
    *,
    if_exists: str = "replace",
) -> None:
    """
    Load a DataFrame into a SQLite database table.

    Parameters
    ----------
    df: pd.DataFrame
        DataFrame produced by ``transform``.
    db_path: Path
        Absolute path to the SQLite database file. Will be created if missing.
    table_name: str
        Target table name.
    if_exists: str, optional
        How to behave if the table already exists.
        Options: 'replace' (drop & recreate), 'append', 'fail'.
        Default is 'replace'.

    Raises
    ------
    ETLException
        If any database operation fails.
    """
    if not db_path.is_absolute():
        raise ETLException(f"Database path must be absolute: {db_path}")

    try:
        logger.info("Connecting to SQLite database at %s", db_path)
        with sqlite3.connect(db_path) as conn:
            conn.execute("PRAGMA foreign_keys = ON;")
            placeholders = ", ".join("?" * len(df.columns))
            columns = ", ".join(f'"{col}"' for col in df.columns)

            if if_exists == "replace":
                logger.info("Dropping existing table %s if it exists.", table_name)
                conn.execute(f'DROP TABLE IF EXISTS "{table_name}"')
                # Derive simple CREATE TABLE statement based on pandas dtypes
                create_stmt = _generate_create_table_sql(df, table_name)
                logger.debug("Create table statement: %s", create_stmt)
                conn.execute(create_stmt)
            elif if_exists == "fail":
                # Ensure table does not exist
                cur = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                    (table_name,),
                )
                if cur.fetchone():
                    raise ETLException(f"Table '{table_name}' already exists.")
            elif if_exists != "append":
                raise ETLException(f"Invalid if_exists value: {if_exists}")

            insert_sql = f'INSERT INTO "{table_name}" ({columns}) VALUES ({placeholders})'
            logger.info("Inserting %d rows into %s.", df.shape[0], table_name)
            conn.executemany(insert_sql, df.itertuples(index=False, name=None))
            conn.commit()
            logger.info("Load completed successfully.")
    except sqlite3.Error as exc:
        raise ETLException(f"SQLite error: {exc}") from exc
    except Exception as exc:
        raise ETLException(f"Failed during load phase: {exc}") from exc


def _generate_create_table_sql(df: pd.DataFrame, table_name: str) -> str:
    """
    Produce a CREATE TABLE statement based on pandas dtypes.
    Only a subset of SQLite types is used (INTEGER, REAL, TEXT).
    """
    type_map = {
        "int64": "INTEGER",
        "float64": "REAL",
        "object": "TEXT",
        "bool": "INTEGER",
        "datetime64[ns]": "TEXT",
    }

    cols_sql: List[str] = []
    for col, dtype in zip(df.columns, df.dtypes):
        sql_type = type_map.get(str(dtype), "TEXT")
        cols_sql.append(f'"{col}" {sql_type}')
    cols_clause = ", ".join(cols_sql)
    return f'CREATE TABLE "{table_name}" ({cols_clause});'


# --------------------------------------------------------------------------- #
# CLI Interface
# --------------------------------------------------------------------------- #


def parse_args(args: Optional[Iterable[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Simple ETL pipeline (CSV → SQLite).")
    parser.add_argument(
        "csv_file",
        type=Path,
        help="Absolute path to the source CSV file.",
    )
    parser.add_argument(
        "sqlite_db",
        type=Path,
        help="Absolute path to the target SQLite database file.",
    )
    parser.add_argument(
        "--table",
        default="etl_data",
        help="Destination table name in SQLite (default: etl_data).",
    )
    parser.add_argument(
        "--if-exists",
        choices=["replace", "append", "fail"],
        default="replace",
        help="Behaviour when the destination table already exists (default: replace).",
    )
    parser.add_argument(
        "--encoding",
        default="utf-8",
        help="Encoding of the source CSV file (default: utf-8).",
    )
    return parser.parse_args(args)


def main() -> None:
    """Entry point: orchestrates extract → transform → load."""
    options = parse_args()
    try:
        raw_df = extract(options.csv_file, encoding=options.encoding)
        transformed_df = transform(raw_df)
        if transformed_df.empty:
            logger.warning("Transformed DataFrame is empty – nothing to load.")
            return
        load(
            transformed_df,
            db_path=options.sqlite_db,
            table_name=options.table,
            if_exists=options.if_exists,
        )
    except ETLException as exc:
        logger.error("ETL failed: %s", exc)
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info("ETL cancelled by user.")
        sys.exit(130)


if __name__ == "__main__":
    main()