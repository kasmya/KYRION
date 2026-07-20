#!/usr/bin/env python
"""
ETL pipeline: Extract data from a CSV file, transform it (cleaning & aggregation),
and load the result into a SQLite database.

Features
--------
- Type‑hints and detailed docstrings.
- Robust error handling for file I/O and DB operations.
- Security‑aware: uses parameterised queries & context managers.
- Configurable via command‑line arguments.
- Relies only on the Python standard library, `pandas`, and `sqlite3`.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Iterable, List, Tuple

import pandas as pd
import sqlite3

# --------------------------------------------------------------------------- #
# Configuration & Logging
# --------------------------------------------------------------------------- #

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("etl")


# --------------------------------------------------------------------------- #
# ETL Functions
# --------------------------------------------------------------------------- #


def extract(csv_path: Path, *, encoding: str = "utf-8") -> pd.DataFrame:
    """
    Load a CSV file into a pandas DataFrame.

    Parameters
    ----------
    csv_path: Path
        Path to the CSV file.
    encoding: str, optional
        File encoding (default ``utf-8``).

    Returns
    -------
    pd.DataFrame
        Raw data read from the CSV.

    Raises
    ------
    FileNotFoundError
        If ``csv_path`` does not exist.
    pd.errors.ParserError
        If the CSV cannot be parsed.
    """
    log.info("Extracting data from %s", csv_path)
    if not csv_path.is_file():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    try:
        df = pd.read_csv(csv_path, encoding=encoding)
    except pd.errors.ParserError as exc:
        raise pd.errors.ParserError(f"Failed to parse CSV {csv_path}") from exc

    log.debug("Extracted %d rows, %d columns", df.shape[0], df.shape[1])
    return df


def _clean(df: pd.DataFrame) -> pd.DataFrame:
    """Perform row/column cleaning."""
    # Strip whitespace from string columns
    str_cols = df.select_dtypes(include="object").columns
    for col in str_cols:
        df[col] = df[col].astype(str).str.strip()

    # Convert known date columns (example)
    for col in ["date"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")

    # Drop rows where critical columns are missing
    critical = ["id", "value"]
    missing = [col for col in critical if col in df.columns]
    if missing:
        df = df.dropna(subset=missing)

    # Remove duplicate rows based on a primary key (example)
    if "id" in df.columns:
        df = df.drop_duplicates(subset="id", keep="last")
    return df


def _aggregate(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate numeric data by a grouping key."""
    if "category" not in df.columns:
        log.warning("No 'category' column for aggregation; returning cleaned df")
        return df

    numeric_cols = df.select_dtypes(include=["number"]).columns.tolist()
    if not numeric_cols:
        log.warning("No numeric columns found for aggregation")
        return df

    agg_df = (
        df.groupby("category")[numeric_cols]
        .agg(["mean", "sum", "count"])
        .reset_index()
    )
    # Flatten MultiIndex columns
    agg_df.columns = [
        f"{col[0]}_{col[1]}" if col[1] else col[0] for col in agg_df.columns
    ]
    return agg_df


def transform(df: pd.DataFrame) -> pd.DataFrame:
    """
    Clean and aggregate the raw DataFrame.

    Parameters
    ----------
    df: pd.DataFrame
        Raw data.

    Returns
    -------
    pd.DataFrame
        Transformed data ready for loading.
    """
    log.info("Transforming data")
    cleaned = _clean(df)
    aggregated = _aggregate(cleaned)
    log.debug("Transformed DataFrame shape: %s", aggregated.shape)
    return aggregated


def load(
    df: pd.DataFrame,
    db_path: Path,
    table_name: str,
    *,
    if_exists: str = "replace",
    batch_size: int = 1000,
) -> None:
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
    if_exists: str, optional
        ``replace`` (default) drops the table first, ``append`` adds rows,
        ``fail`` raises an error if the table exists.
    batch_size: int, optional
        Number of rows per INSERT batch.

    Raises
    ------
    sqlite3.Error
        If any database operation fails.
    """
    log.info("Loading data into %s (table: %s)", db_path, table_name)
    try:
        with sqlite3.connect(db_path) as conn:
            conn.execute("PRAGMA foreign_keys = ON;")  # security best practice
            # Use pandas to_sql for schema creation, then manual batch inserts.
            df.head(0).to_sql(
                name=table_name,
                con=conn,
                if_exists=if_exists,
                index=False,
            )

            # Prepare parameterised insert statement
            placeholders = ", ".join("?" * len(df.columns))
            insert_sql = f"INSERT INTO {table_name} ({', '.join(df.columns)}) VALUES ({placeholders})"

            rows: Iterable[Tuple] = df.itertuples(index=False, name=None)
            batch: List[Tuple] = []
            for row in rows:
                batch.append(row)
                if len(batch) >= batch_size:
                    conn.executemany(insert_sql, batch)
                    batch.clear()
            if batch:
                conn.executemany(insert_sql, batch)

            conn.commit()
        log.info("Load completed successfully")
    except sqlite3.Error as exc:
        raise sqlite3.Error(f"Failed to load data into {db_path}") from exc


# --------------------------------------------------------------------------- #
# CLI Entrypoint
# --------------------------------------------------------------------------- #


def parse_args(argv: List[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ETL pipeline CSV → SQLite")
    parser.add_argument(
        "csv",
        type=Path,
        help="Path to the source CSV file",
    )
    parser.add_argument(
        "db",
        type=Path,
        help="Path to the SQLite database file (will be created if missing)",
    )
    parser.add_argument(
        "--table",
        default="etl_data",
        help="Destination table name in SQLite (default: %(default)s)",
    )
    parser.add_argument(
        "--if-exists",
        choices=["fail", "replace", "append"],
        default="replace",
        help="Behavior when the target table already exists (default: %(default)s)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=1000,
        help="Number of rows per INSERT batch (default: %(default)s)",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default="INFO",
        help="Logging verbosity (default: %(default)s)",
    )
    return parser.parse_args(argv)


def main(argv: List[str] | None = None) -> int:
    args = parse_args(argv)

    # Adjust logging level as requested
    log.setLevel(getattr(logging, args.log_level))

    try:
        raw_df = extract(args.csv)
        transformed_df = transform(raw_df)
        load(
            transformed_df,
            db_path=args.db,
            table_name=args.table,
            if_exists=args.if_exists,
            batch_size=args.batch_size,
        )
    except (FileNotFoundError, pd.errors.ParserError, sqlite3.Error) as exc:
        log.error("ETL failed: %s", exc)
        return 1
    except Exception as exc:  # pragma: no cover
        log.exception("Unexpected error")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())