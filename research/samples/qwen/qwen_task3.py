"""Streamlit Data Dashboard with Plotly and APScheduler."""
import io, logging
from datetime import datetime
import pandas as pd
import plotly.express as px
import streamlit as st
from apscheduler.schedulers.background import BackgroundScheduler

logging.basicConfig(level=logging.INFO)
scheduler = BackgroundScheduler()

def take_snapshot():
    """Scheduled task to save daily data snapshot."""
    if 'df' in st.session_state and not st.session_state.df.empty:
        filename = f"snapshot_{datetime.now().strftime('%Y%m%d')}.csv"
        st.session_state.df.to_csv(filename, index=False)
        logging.info(f"Snapshot saved: {filename}")

scheduler.add_job(take_snapshot, 'interval', days=1)
scheduler.start()

st.set_page_config(page_title="Data Dashboard", layout="wide")
st.title("Interactive Data Dashboard")

uploaded_file = st.file_uploader("Upload CSV or Excel", type=['csv', 'xlsx'])

if uploaded_file:
    try:
        if uploaded_file.name.endswith('.csv'):
            df = pd.read_csv(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file)
        st.session_state.df = df
    except Exception as e:
        st.error(f"Error reading file: {e}")

if 'df' in st.session_state and not st.session_state.df.empty:
    df = st.session_state.df
    st.subheader("Raw Data")
    st.dataframe(df.head())

    st.subheader("Data Cleaning")
    col1, col2 = st.columns(2)
    if col1.button("Drop Duplicates"):
        df = df.drop_duplicates()
        st.session_state.df = df
        st.success(f"Dropped duplicates. Rows: {len(df)}")
    if col2.button("Fill Missing with Mean"):
        num_cols = df.select_dtypes(include=['number']).columns
        df[num_cols] = df[num_cols].fillna(df[num_cols].mean())
        st.session_state.df = df
        st.success("Filled numeric missing values with mean.")

    st.subheader("Summary Statistics")
    st.dataframe(df.describe())

    st.subheader("Visualizations")
    num_cols = df.select_dtypes(include=['number']).columns.tolist()
    if len(num_cols) >= 2:
        x_axis = st.selectbox("X-Axis", num_cols)
        y_axis = st.selectbox("Y-Axis", [c for c in num_cols if c != x_axis])
        fig = px.scatter(df, x=x_axis, y=y_axis, title=f"{y_axis} vs {x_axis}")
        st.plotly_chart(fig, use_container_width=True)

    st.download_button("Export Cleaned CSV", df.to_csv(index=False).encode('utf-8'), "cleaned_data.csv")
else:
    st.info("Please upload a file to begin.")