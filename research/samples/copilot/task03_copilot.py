"""
Data Dashboard using Streamlit, Pandas, Plotly, and APScheduler.
Features:
- Upload CSV/Excel files
- Data cleaning (drop duplicates, handle missing values)
- Interactive Plotly charts
- Summary statistics
- Export cleaned data as CSV
- Scheduled daily snapshots
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
from typing import Optional

# Configure logging
logging.basicConfig(level=logging.INFO)

# Global variable to hold data
DATA: Optional[pd.DataFrame] = None


def clean_data(df: pd.DataFrame) -> pd.DataFrame:
    """Clean the uploaded dataframe by handling missing values and duplicates.

    Args:
        df (pd.DataFrame): Input dataframe.

    Returns:
        pd.DataFrame: Cleaned dataframe.
    """
    df = df.drop_duplicates()
    df = df.fillna(method="ffill").fillna(method="bfill")
    return df


def save_snapshot(df: pd.DataFrame) -> None:
    """Save daily snapshot of cleaned data to CSV.

    Args:
        df (pd.DataFrame): Dataframe to save.
    """
    if df is not None:
        filename = f"snapshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        df.to_csv(filename, index=False)
        logging.info(f"Snapshot saved: {filename}")


# Scheduler for daily snapshots
scheduler = BackgroundScheduler()
scheduler.add_job(lambda: save_snapshot(DATA) if DATA is not None else None, "interval", days=1)
scheduler.start()


def main():
    """Main Streamlit app."""
    global DATA

    st.title("📊 Data Dashboard")

    # File upload
    uploaded_file = st.file_uploader("Upload CSV or Excel file", type=["csv", "xlsx"])
    if uploaded_file:
        try:
            if uploaded_file.name.endswith(".csv"):
                df = pd.read_csv(uploaded_file)
            else:
                df = pd.read_excel(uploaded_file)
            DATA = clean_data(df)
            st.success("File uploaded and cleaned successfully!")

            # Show summary statistics
            st.subheader("Summary Statistics")
            st.write(DATA.describe())

            # Interactive chart selection
            st.subheader("Interactive Charts")
            numeric_cols = DATA.select_dtypes(include="number").columns.tolist()
            if numeric_cols:
                x_axis = st.selectbox("Select X-axis", options=numeric_cols)
                y_axis = st.selectbox("Select Y-axis", options=numeric_cols)
                fig = px.scatter(DATA, x=x_axis, y=y_axis, title="Scatter Plot")
                st.plotly_chart(fig)
            else:
                st.warning("No numeric columns available for plotting.")

            # Export cleaned data
            st.subheader("Export Cleaned Data")
            st.download_button(
                label="Download CSV",
                data=DATA.to_csv(index=False).encode("utf-8"),
                file_name="cleaned_data.csv",
                mime="text/csv",
            )

        except Exception as e:
            logging.error(f"Error processing file: {e}")
            st.error("Failed to process file. Please check format.")

    st.info("Daily snapshots are automatically saved in the working directory.")


if __name__ == "__main__":
    main()

