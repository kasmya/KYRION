"""etl_pipeline.py
A simple ETL (Extract, Transform, Load) pipeline that reads data from a CSV file,
cleans and aggregates it, and stores the result in a SQLite database.

The module uses only the Python standard library and the widely‑used third‑party
package ``pandas``.  All functions include type hints, comprehensive docstrings,
and explicit error handling following security best practices (e.g., context
managers and parameterised SQL statements).
"""

from __future__ import annotations

import csv
import os
import sqlite3
from pathlib import Path
from typing import Any, Iterable, List, Mapping, Tuple

import pandas as pd

__all__: List[str] = ["ETLException", "extract", "transform", "load", "run_etl"]


class ETLException(Exception):
    """Base exception for all ETL related errors."""

    pass


def extract(csv_path: str | os.PathLike[str], *, encoding: str = "utf-8") -> pd.DataFrame:
    """
    Extract data from a CSV file into a :class:`pandas.DataFrame`.

    Parameters
    ----------
    csv_path: str or PathLike
        Path to the source CSV file.  The file must be readable by the current user.
    encoding: str, optional
        Text encoding used to read the file.  Defaults to ``'utf-8'``.

    Returns
    -------
    pandas.DataFrame
        DataFrame containing the raw CSV data.

    Raises
    ------
    ETLException
        If the file does not exist, is not readable, or cannot be parsed as CSV.
    """
    path = Path(csv_path)

    if not path.is_file():
        raise ETLException(f"CSV file not found: {path}")

    try:
        df = pd.read_csv(path, encoding=encoding)
        if df.empty:
            raise ETLException("CSV file is empty.")
        return df
    except (pd.errors.EmptyDataError, pd.errors.ParserError) as exc:
        raise ETLException(f"Failed to parse CSV file '{path}': {exc}") from exc
    except UnicodeDecodeError as exc:
        raise ETLException(f"Encoding error while reading '{path}': {exc}") from exc
    except Exception as exc:  # pragma: no cover
        raise ETLException(f"Unexpected error during extraction: {exc}") from exc


def _clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    Internal helper to clean a DataFrame.

    - Strips whitespace from string columns.
    - Replaces empty strings with ``NaN``.
    - Drops rows that are completely empty.

    Parameters
    ----------
    df: pandas.DataFrame
        Raw DataFrame.

    Returns
    -------
    pandas.DataFrame
        Cleaned DataFrame.
    """
    df_clean = df.copy()

    # Strip whitespace from object (string) columns
    str_cols = df_clean.select_dtypes(include=["object"]).columns
    for col in str_cols:
        df_clean[col] = df_clean[col].astype(str).str.strip()

    # Convert empty strings to NaN
    df_clean.replace(r"^\s*$", pd.NA, regex=True, inplace=True)

    # Drop rows that are completely empty after cleaning
    df_clean.dropna(how="all", inplace=True)

    return df_clean


def transform(
    df: pd.DataFrame,
    *,
    group_by: str,
    agg_column: str,
    agg_func: str = "sum",
) -> pd.DataFrame:
    """
    Transform the extracted DataFrame by cleaning it and performing an aggregation.

    Parameters
    ----------
    df: pandas.DataFrame
        DataFrame returned by :func:`extract`.
    group_by: str
        Column name to group by.
    agg_column: str
        Column name on which the aggregation function will be applied.
    agg_func: str, optional
        Aggregation function name supported by pandas (e.g., ``'sum'``, ``'mean'``,
        ``'max'``).  Defaults to ``'sum'``.

    Returns
    -------
    pandas.DataFrame
        Aggregated DataFrame with ``group_by`` as the index and the aggregated
        ``agg_column`` as the sole column.

    Raises
    ------
    ETLException
        If required columns are missing or the aggregation fails.
    """
    if group_by not in df.columns:
        raise ETLException(f"Group‑by column '{group_by}' not found in data.")
    if agg_column not in df.columns:
        raise ETLException(f"Aggregation column '{agg_column}' not found in data.")

    df_clean = _clean_dataframe(df)

    try:
        agg_series = df_clean.groupby(group_by)[agg_column].agg(agg_func)
        result = agg_series.reset_index()
        return result
    except KeyError as exc:
        raise ETLException(f"Invalid column during aggregation: {exc}") from exc
    except Exception as exc:  # pragma: no cover
        raise ETLException(f"Unexpected error during transformation: {exc}") from exc


def load(
    df: pd.DataFrame,
    db_path: str | os.PathLike[str],
    table_name: str,
    *,
    if_exists: str = "replace",
) -> None:
    """
    Load a DataFrame into a SQLite database table.

    Parameters
    ----------
    df: pandas.DataFrame
        DataFrame to be persisted.
    db_path: str or PathLike
        Path to the SQLite database file.  The file will be created if it does not
        exist.
    table_name: str
        Name of the target table.  Must be a valid SQLite identifier.
    if_exists: {'fail', 'replace', 'append'}, optional
        Behaviour when the table already exists.  Defaults to ``'replace'``.

    Raises
    ------
    ETLException
        If the database cannot be accessed or the insertion fails.
    """
    if not table_name.isidentifier():
        raise ETLException(f"Invalid table name '{table_name}'. Must be a valid identifier.")

    db_file = Path(db_path)
    try:
        # Ensure the parent directory exists with restrictive permissions
        if not db_file.parent.exists():
            db_file.parent.mkdir(parents=True, mode=0o700, exist_ok=True)

        with sqlite3.connect(db_file) as conn:
            conn.execute("PRAGMA foreign_keys = ON;")  # security best practice
            # Use pandas to_sql with parameterised queries internally
            df.to_sql(
                name=table_name,
                con=conn,
                if_exists=if_exists,
                index=False,
                method="multi",  # efficient bulk insert
            )
    except sqlite3.Error as exc:
        raise ETLException(f"SQLite error while loading data: {exc}") from exc
    except Exception as exc:  # pragma: no cover
        raise ETLException(f"Unexpected error during loading: {exc}") from exc


def run_etl(
    csv_path: str,
    db_path: str,
    *,
    table_name: str = "etl_result",
    group_by: str,
    agg_column: str,
    agg_func: str = "sum",
    encoding: str = "utf-8",
) -> None:
    """
    Execute the full ETL workflow: extract, transform, and load.

    Parameters
    ----------
    csv_path: str
        Path to the source CSV.
    db_path: str
        Path to the SQLite database file.
    table_name: str, optional
        Destination table name in the SQLite database.
    group_by: str
        Column to group by during transformation.
    agg_column: str
        Column to aggregate.
    agg_func: str, optional
        Aggregation function (default ``'sum'``).
    encoding: str, optional
        Encoding used to read the CSV file.

    Raises
    ------
    ETLException
        Propagated from any of the pipeline stages.
    """
    raw_df = extract(csv_path, encoding=encoding)
    transformed_df = transform(
        raw_df, group_by=group_by, agg_column=agg_column, agg_func=agg_func
    )
    load(transformed_df, db_path, table_name)


if __name__ == "__main__":
    # Example usage (replace with real arguments or integrate with a CLI parser)
    try:
        run_etl(
            csv_path="data/input.csv",
            db_path="data/output.db",
            table_name="sales_summary",
            group_by="region",
            agg_column="sales",
            agg_func="sum",
        )
        print("ETL pipeline completed successfully.")
    except ETLException as e:
        print(f"ETL pipeline failed: {e}")