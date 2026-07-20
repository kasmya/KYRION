"""ETL pipeline: CSV → clean/aggregate → SQLite.

The script extracts data from a CSV file using pandas, performs basic cleaning
and aggregation, and loads the result into a SQLite database using the
standard library's ``sqlite3`` module.

Only the standard library together with ``pandas`` is required.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Sequence

import pandas as pd

# --------------------------------------------------------------------------- #
# Configuration and logging
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class ETLConfig:
    """Configuration for the ETL process."""
    csv_path: Path                 # Path to the source CSV file
    db_path: Path                  # Path to the SQLite database file
    table_name: str                # Destination table name
    key_columns: Sequence[str]    # Columns to group by for aggregation
    agg_columns: List[str]         # Numeric columns to aggregate
    agg_funcs: List[str]           # Aggregation functions (e.g., ["sum", "mean"])


DEFAULT_CONFIG = ETLConfig(
    csv_path=Path("data/input.csv"),
    db_path=Path("data/output.db"),
    table_name="aggregated_data",
    key_columns=["category"],
    agg_columns=["value"],
    agg_funcs=["sum", "mean"],
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Extraction
# --------------------------------------------------------------------------- #


def extract(csv_path: Path) -> pd.DataFrame:
    """
    Load a CSV file into a pandas DataFrame.

    Parameters
    ----------
    csv_path: Path
        Path to the CSV file.

    Returns
    -------
    pd.DataFrame
        DataFrame containing the raw data.

    Raises
    ------
    FileNotFoundError
        If the CSV file does not exist.
    pd.errors.EmptyDataError, pd.errors.ParserError
        If pandas cannot parse the CSV.
    """
    logger.info("Extracting data from %s", csv_path)
    if not csv_path.is_file():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    try:
        df = pd.read_csv(csv_path)
    except (pd.errors.EmptyDataError, pd.errors.ParserError) as exc:
        logger.exception("Failed to parse CSV file.")
        raise

    logger.info("Extracted %d rows and %d columns", df.shape[0], df.shape[1])
    return df


# --------------------------------------------------------------------------- #
# Transformation
# --------------------------------------------------------------------------- #


def transform(
    df: pd.DataFrame,
    key_columns: Sequence[str],
    agg_columns: List[str],
    agg_funcs: List[str],
) -> pd.DataFrame:
    """
    Clean and aggregate the DataFrame.

    Cleaning steps:
    - Drop rows where any of the key columns are missing.
    - Convert aggregation columns to numeric (coerce errors to NaN).
    - Drop rows where all aggregation columns are NaN.

    Aggregation:
    - Group by ``key_columns`` and apply ``agg_funcs`` to ``agg_columns``.

    Parameters
    ----------
    df: pd.DataFrame
        Raw data.
    key_columns: Sequence[str]
        Columns to use as grouping keys.
    agg_columns: List[str]
        Numeric columns to aggregate.
    agg_funcs: List[str]
        Aggregation functions supported by pandas (e.g., "sum", "mean").

    Returns
    -------
    pd.DataFrame
        Aggregated DataFrame ready for loading.
    """
    logger.info("Starting transformation step")

    # --- Cleaning ---
    missing_keys = df[key_columns].isnull().any(axis=1)
    if missing_keys.any():
        logger.warning("Dropping %d rows with missing key columns", missing_keys.sum())
        df = df.loc[~missing_keys].copy()

    for col in agg_columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    nan_agg = df[agg_columns].isnull().all(axis=1)
    if nan_agg.any():
        logger.warning("Dropping %d rows with all NaN aggregation columns", nan_agg.sum())
        df = df.loc[~nan_agg].copy()

    # --- Aggregation ---
    agg_dict = {col: agg_funcs for col in agg_columns}
    aggregated = (
        df.groupby(list(key_columns), as_index=False)
        .agg(agg_dict)
        .sort_values(by=list(key_columns))
    )
    # Flatten MultiIndex columns resulting from multiple agg funcs
    aggregated.columns = [
        f"{'_'.join(filter(None, map(str, col)))}" for col in aggregated.columns.to_flat_index()
    ]

    logger.info("Transformation produced %d rows", aggregated.shape[0])
    return aggregated


# --------------------------------------------------------------------------- #
# Loading
# --------------------------------------------------------------------------- #


def _create_table_if_not_exists(conn: sqlite3.Connection, table: str, df: pd.DataFrame) -> None:
    """
    Create a SQLite table matching the DataFrame schema if it does not already exist.

    Parameters
    ----------
    conn: sqlite3.Connection
        Open SQLite connection.
    table: str
        Destination table name.
    df: pd.DataFrame
        DataFrame whose columns define the table schema.
    """
    column_defs = []
    for col, dtype in zip(df.columns, df.dtypes):
        if pd.api.types.is_integer_dtype(dtype):
            sql_type = "INTEGER"
        elif pd.api.types.is_float_dtype(dtype):
            sql_type = "REAL"
        else:
            sql_type = "TEXT"
        column_defs.append(f'"{col}" {sql_type}')

    create_stmt = f'CREATE TABLE IF NOT EXISTS "{table}" ({", ".join(column_defs)});'
    logger.debug("Creating table with statement: %s", create_stmt)
    conn.execute(create_stmt)


def load(df: pd.DataFrame, db_path: Path, table_name: str) -> None:
    """
    Load a DataFrame into a SQLite database table.

    Parameters
    ----------
    df: pd.DataFrame
        Data to load.
    db_path: Path
        Path to the SQLite database file.
    table_name: str
        Destination table name.

    Raises
    ------
    sqlite3.DatabaseError
        If any database operation fails.
    """
    logger.info("Loading %d rows into %s (SQLite DB: %s)", df.shape[0], table_name, db_path)
    try:
        conn = sqlite3.connect(db_path.as_posix(), detect_types=sqlite3.PARSE_DECLTYPES)
        conn.execute("PRAGMA foreign_keys = ON;")  # security best practice
        with conn:
            _create_table_if_not_exists(conn, table_name, df)

            # Use executemany with parameter substitution to avoid SQL injection
            placeholders = ", ".join("?" for _ in df.columns)
            insert_sql = f'INSERT INTO "{table_name}" ({", ".join(df.columns)}) VALUES ({placeholders});'
            logger.debug("Insert statement: %s", insert_sql)

            rows = df.where(pd.notnull(df), None).values.tolist()
            conn.executemany(insert_sql, rows)
            logger.info("Load completed successfully")
    except sqlite3.DatabaseError as exc:
        logger.exception("Database operation failed")
        raise
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #


def run_etl(config: ETLConfig) -> None:
    """
    Run the full ETL pipeline using the provided configuration.

    Parameters
    ----------
    config: ETLConfig
        Pipeline configuration.
    """
    try:
        raw_df = extract(config.csv_path)
        transformed_df = transform(
            raw_df,
            key_columns=config.key_columns,
            agg_columns=config.agg_columns,
            agg_funcs=config.agg_funcs,
        )
        load(transformed_df, config.db_path, config.table_name)
    except Exception as exc:  # pylint: disable=broad-except
        logger.error("ETL pipeline failed: %s", exc)
        raise


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #


if __name__ == "__main__":
    # Example usage: adjust paths and column names as appropriate.
    example_config = ETLConfig(
        csv_path=Path("sample_data.csv"),
        db_path=Path("sample_output.db"),
        table_name="sales_summary",
        key_columns=["region", "product"],
        agg_columns=["units_sold", "revenue"],
        agg_funcs=["sum", "mean"],
    )
    run_etl(example_config)