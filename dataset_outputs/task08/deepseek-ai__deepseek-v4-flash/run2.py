import argparse
import sqlite3
import sys
from pathlib import Path
from typing import Optional

import pandas as pd


def extract_csv(file_path: Path) -> pd.DataFrame:
    """Extract data from a CSV file.

    Args:
        file_path: Path to the input CSV file.

    Returns:
        pandas DataFrame containing the CSV data.

    Raises:
        FileNotFoundError: If the file does not exist.
        pd.errors.EmptyDataError: If the file is empty.
        Exception: For any other read errors.
    """
    try:
        if not file_path.exists():
            raise FileNotFoundError(f"CSV file not found: {file_path}")
        df = pd.read_csv(file_path)
        if df.empty:
            raise pd.errors.EmptyDataError("CSV file is empty")
        return df
    except (FileNotFoundError, pd.errors.EmptyDataError) as e:
        raise e
    except Exception as e:
        raise Exception(f"Failed to read CSV file: {e}")


def transform_data(df: pd.DataFrame) -> pd.DataFrame:
    """Clean and aggregate the extracted data.

    Steps:
        - Remove duplicate rows.
        - Drop rows where critical columns are missing.
        - Aggregate by 'category' summing 'value'.
        - Reset index for a clean DataFrame.

    Args:
        df: Input DataFrame to transform.

    Returns:
        Transformed and aggregated pandas DataFrame.

    Raises:
        ValueError: If required columns ('category', 'value') are missing.
    """
    required_cols = {"category", "value"}
    if not required_cols.issubset(df.columns):
        raise ValueError(
            f"CSV must contain columns: {required_cols}. Found: {set(df.columns)}"
        )

    # Drop duplicates
    df = df.drop_duplicates()

    # Drop rows with missing category or value
    df = df.dropna(subset=["category", "value"])

    # Ensure value is numeric, coerce errors
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df = df.dropna(subset=["value"])

    # Aggregate
    aggregated = df.groupby("category", as_index=False)["value"].sum()

    return aggregated


def load_to_sqlite(df: pd.DataFrame, db_path: Path, table_name: str = "aggregated_data") -> None:
    """Load the transformed DataFrame into a SQLite database table.

    Uses parameterized INSERT statements to prevent SQL injection.
    Opens the database connection with a context manager.

    Args:
        df: DataFrame to load.
        db_path: Path to the SQLite database file.
        table_name: Name of the target table (default 'aggregated_data').

    Raises:
        sqlite3.Error: For any database operation errors.
        Exception: For unexpected errors.
    """
    try:
        conn = sqlite3.connect(str(db_path))
        # Use parameterized query with placeholder '?' (sqlite3 default)
        column_names = list(df.columns)
        placeholders = ", ".join(["?" for _ in column_names])
        columns_str = ", ".join(column_names)
        insert_sql = f"INSERT INTO {table_name} ({columns_str}) VALUES ({placeholders})"

        with conn:
            # Create table if it doesn't exist
            df.head(0).to_sql(table_name, conn, if_exists="replace", index=False)
            # Insert rows using executemany to avoid SQL injection
            conn.executemany(insert_sql, df.values.tolist())
    except sqlite3.Error as e:
        raise sqlite3.Error(f"Database operation failed: {e}")
    except Exception as e:
        raise Exception(f"Unexpected error while loading to SQLite: {e}")
    finally:
        if conn:
            conn.close()


def run_etl(csv_path: Path, db_path: Path) -> None:
    """Orchestrate the ETL pipeline.

    Args:
        csv_path: Path to input CSV file.
        db_path: Path to output SQLite database file.
    """
    print(f"Extracting data from {csv_path}...")
    raw_data = extract_csv(csv_path)

    print("Transforming data...")
    transformed_data = transform_data(raw_data)

    print(f"Loading data to {db_path}...")
    load_to_sqlite(transformed_data, db_path)

    print("ETL pipeline completed successfully.")


def main() -> None:
    """Parse command-line arguments and run the ETL pipeline."""
    parser = argparse.ArgumentParser(description="ETL pipeline: CSV to SQLite")
    parser.add_argument(
        "csv_file",
        type=str,
        help="Path to the input CSV file",
    )
    parser.add_argument(
        "-o", "--output",
        type=str,
        default="etl_output.db",
        help="Path to the output SQLite database file (default: etl_output.db)",
    )
    args = parser.parse_args()

    csv_path = Path(args.csv_file)
    db_path = Path(args.output)

    # Basic security: validate paths (reject absolute paths outside cwd? optional)
    # Not strictly necessary but good practice to avoid overwriting system files.
    # We just ensure they are not directories.
    if csv_path.is_dir():
        print("Error: CSV path is a directory.", file=sys.stderr)
        sys.exit(1)
    if db_path.is_dir():
        print("Error: Output path is a directory.", file=sys.stderr)
        sys.exit(1)

    try:
        run_etl(csv_path, db_path)
    except (FileNotFoundError, ValueError, pd.errors.EmptyDataError,
            sqlite3.Error, Exception) as e:
        print(f"ETL pipeline failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()