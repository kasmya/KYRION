"""
### Task 3: Data Dashboard (Streamlit + Pandas)

An interactive Streamlit dashboard for uploading CSV/Excel files, cleaning
data, viewing Plotly charts and summary statistics, exporting cleaned
data, and taking scheduled daily snapshots via APScheduler.

Requirements:
    pip install streamlit pandas plotly apscheduler openpyxl

Run:
    streamlit run 03_data_dashboard.py
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd
import plotly.express as px
import streamlit as st
from apscheduler.schedulers.background import BackgroundScheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("data_dashboard")

SNAPSHOT_DIR = Path("snapshots")
SNAPSHOT_DIR.mkdir(exist_ok=True)


class DataCleaner:
    """Encapsulates basic, reusable data-cleaning operations."""

    @staticmethod
    def drop_duplicates(df: pd.DataFrame) -> pd.DataFrame:
        """Removes exact duplicate rows."""
        before = len(df)
        cleaned = df.drop_duplicates()
        logger.info("Dropped %d duplicate row(s)", before - len(cleaned))
        return cleaned

    @staticmethod
    def handle_missing_values(df: pd.DataFrame, strategy: str = "drop") -> pd.DataFrame:
        """Handles missing values via 'drop', 'mean', or 'zero' strategies.

        Args:
            df: Input DataFrame.
            strategy: One of 'drop', 'mean', or 'zero'.
        """
        if strategy == "drop":
            return df.dropna()
        if strategy == "mean":
            numeric_cols = df.select_dtypes(include="number").columns
            df = df.copy()
            df[numeric_cols] = df[numeric_cols].fillna(df[numeric_cols].mean())
            return df
        if strategy == "zero":
            return df.fillna(0)
        raise ValueError(f"Unknown missing-value strategy: {strategy}")


def load_uploaded_file(uploaded_file) -> Optional[pd.DataFrame]:
    """Loads a Streamlit UploadedFile (CSV or Excel) into a DataFrame."""
    try:
        if uploaded_file.name.lower().endswith(".csv"):
            return pd.read_csv(uploaded_file)
        return pd.read_excel(uploaded_file)
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to load uploaded file '%s': %s", uploaded_file.name, exc)
        st.error(f"Could not read file: {exc}")
        return None


def take_daily_snapshot(df: pd.DataFrame, name: str = "dataset") -> None:
    """Persists a timestamped snapshot of the current DataFrame to disk."""
    try:
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        path = SNAPSHOT_DIR / f"{name}_{timestamp}.csv"
        df.to_csv(path, index=False)
        logger.info("Snapshot saved to '%s'", path)
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to save snapshot: %s", exc)


def start_scheduler(df_getter) -> BackgroundScheduler:
    """Starts a background scheduler that snapshots the current data once per day."""
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        lambda: take_daily_snapshot(df_getter()) if df_getter() is not None else None,
        "interval",
        days=1,
        id="daily_snapshot",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Daily snapshot scheduler started")
    return scheduler


def render_dashboard() -> None:
    """Renders the full Streamlit dashboard UI."""
    st.set_page_config(page_title="Data Dashboard", layout="wide")
    st.title("📊 Data Cleaning & Visualization Dashboard")

    if "scheduler_started" not in st.session_state:
        st.session_state["scheduler_started"] = False
    if "current_df" not in st.session_state:
        st.session_state["current_df"] = None

    uploaded_file = st.file_uploader("Upload a CSV or Excel file", type=["csv", "xlsx", "xls"])

    if uploaded_file is not None:
        df = load_uploaded_file(uploaded_file)
        if df is not None:
            st.session_state["current_df"] = df

    df = st.session_state["current_df"]
    if df is None:
        st.info("Upload a file to get started.")
        return

    st.subheader("Raw Data Preview")
    st.dataframe(df.head(20))

    st.subheader("Data Cleaning")
    col1, col2 = st.columns(2)
    with col1:
        remove_dupes = st.checkbox("Drop duplicate rows", value=True)
    with col2:
        missing_strategy = st.selectbox(
            "Missing value strategy", ["drop", "mean", "zero"], index=0
        )

    cleaned_df = df.copy()
    if remove_dupes:
        cleaned_df = DataCleaner.drop_duplicates(cleaned_df)
    try:
        cleaned_df = DataCleaner.handle_missing_values(cleaned_df, missing_strategy)
    except ValueError as exc:
        st.error(str(exc))
        return

    st.subheader("Cleaned Data Preview")
    st.dataframe(cleaned_df.head(20))

    st.subheader("Summary Statistics")
    st.write(cleaned_df.describe(include="all"))

    numeric_columns = cleaned_df.select_dtypes(include="number").columns.tolist()
    if numeric_columns:
        st.subheader("Interactive Chart")
        x_axis = st.selectbox("X-axis", cleaned_df.columns.tolist())
        y_axis = st.selectbox("Y-axis", numeric_columns)
        chart_type = st.radio("Chart type", ["line", "bar", "scatter"], horizontal=True)

        if chart_type == "line":
            fig = px.line(cleaned_df, x=x_axis, y=y_axis)
        elif chart_type == "bar":
            fig = px.bar(cleaned_df, x=x_axis, y=y_axis)
        else:
            fig = px.scatter(cleaned_df, x=x_axis, y=y_axis)

        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("No numeric columns available for charting.")

    st.subheader("Export")
    csv_bytes = cleaned_df.to_csv(index=False).encode("utf-8")
    st.download_button("Download cleaned data as CSV", data=csv_bytes, file_name="cleaned_data.csv")

    if not st.session_state["scheduler_started"]:
        start_scheduler(lambda: st.session_state.get("current_df"))
        st.session_state["scheduler_started"] = True

    if st.button("Take snapshot now"):
        take_daily_snapshot(cleaned_df)
        st.success("Snapshot saved.")


if __name__ == "__main__":
    render_dashboard()
