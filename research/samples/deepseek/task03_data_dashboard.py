"""
Interactive Data Dashboard with Streamlit for data analysis and visualization.

Features:
- CSV/Excel file upload and parsing
- Data cleaning operations
- Interactive Plotly charts
- Summary statistics
- Export cleaned data
- Scheduled snapshots via APScheduler
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple
import io
import tempfile
from pathlib import Path

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
import json

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('dashboard.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Page configuration
st.set_page_config(
    page_title="Data Analysis Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Session state initialization
if 'data' not in st.session_state:
    st.session_state.data = None
if 'cleaned_data' not in st.session_state:
    st.session_state.cleaned_data = None
if 'file_name' not in st.session_state:
    st.session_state.file_name = None
if 'snapshot_dir' not in st.session_state:
    st.session_state.snapshot_dir = os.path.join(tempfile.gettempdir(), 'dashboard_snapshots')

class DataCleaner:
    """Handles data cleaning operations."""
    
    @staticmethod
    def remove_duplicates(df: pd.DataFrame, subset: Optional[List[str]] = None) -> pd.DataFrame:
        """
        Remove duplicate rows from DataFrame.
        
        Args:
            df: Input DataFrame
            subset: Columns to consider for duplicate detection
            
        Returns:
            DataFrame with duplicates removed
        """
        initial_count = len(df)
        df_cleaned = df.drop_duplicates(subset=subset, keep='first')
        removed = initial_count - len(df_cleaned)
        logger.info(f"Removed {removed} duplicate rows")
        return df_cleaned
    
    @staticmethod
    def handle_missing_values(
        df: pd.DataFrame,
        strategy: str = 'mean',
        fill_value: Any = None,
        columns: Optional[List[str]] = None
    ) -> pd.DataFrame:
        """
        Handle missing values in DataFrame.
        
        Args:
            df: Input DataFrame
            strategy: Strategy for handling missing values ('mean', 'median', 'mode', 'drop', 'fill')
            fill_value: Value to use for 'fill' strategy
            columns: Specific columns to process
            
        Returns:
            DataFrame with handled missing values
        """
        if columns is None:
            columns = df.columns.tolist()
        
        df_processed = df.copy()
        missing_before = df_processed[columns].isnull().sum().sum()
        
        if strategy == 'drop':
            df_processed = df_processed.dropna(subset=columns)
        else:
            for col in columns:
                if df_processed[col].dtype in ['int64', 'float64']:
                    if strategy == 'mean':
                        df_processed[col] = df_processed[col].fillna(df_processed[col].mean())
                    elif strategy == 'median':
                        df_processed[col] = df_processed[col].fillna(df_processed[col].median())
                    elif strategy == 'mode':
                        df_processed[col] = df_processed[col].fillna(df_processed[col].mode()[0])
                    elif strategy == 'fill':
                        df_processed[col] = df_processed[col].fillna(fill_value)
                else:
                    if strategy == 'mode':
                        df_processed[col] = df_processed[col].fillna(df_processed[col].mode()[0])
                    elif strategy == 'fill':
                        df_processed[col] = df_processed[col].fillna(fill_value if fill_value else 'Unknown')
        
        missing_after = df_processed[columns].isnull().sum().sum()
        logger.info(f"Missing values: {missing_before} before, {missing_after} after cleaning")
        return df_processed
    
    @staticmethod
    def remove_outliers(df: pd.DataFrame, columns: List[str], method: str = 'iqr') -> pd.DataFrame:
        """
        Remove outliers from specified columns.
        
        Args:
            df: Input DataFrame
            columns: Columns to check for outliers
            method: Outlier detection method ('iqr' or 'zscore')
            
        Returns:
            DataFrame with outliers removed
        """
        df_cleaned = df.copy()
        initial_count = len(df_cleaned)
        
        for col in columns:
            if df_cleaned[col].dtype in ['int64', 'float64']:
                if method == 'iqr':
                    Q1 = df_cleaned[col].quantile(0.25)
                    Q3 = df_cleaned[col].quantile(0.75)
                    IQR = Q3 - Q1
                    lower_bound = Q1 - 1.5 * IQR
                    upper_bound = Q3 + 1.5 * IQR
                    df_cleaned = df_cleaned[
                        (df_cleaned[col] >= lower_bound) & 
                        (df_cleaned[col] <= upper_bound)
                    ]
                elif method == 'zscore':
                    from scipy import stats
                    z_scores = np.abs(stats.zscore(df_cleaned[col].dropna()))
                    df_cleaned = df_cleaned[z_scores < 3]
        
        removed = initial_count - len(df_cleaned)
        logger.info(f"Removed {removed} outliers")
        return df_cleaned

class DataVisualizer:
    """Handles data visualization creation."""
    
    @staticmethod
    def create_distribution_plot(df: pd.DataFrame, column: str) -> go.Figure:
        """Create distribution plot for a column."""
        fig = make_subplots(
            rows=2, cols=1,
            subplot_titles=(f'Distribution of {column}', f'Box Plot of {column}'),
            vertical_spacing=0.2
        )
        
        fig.add_trace(
            go.Histogram(x=df[column], name='Distribution', nbinsx=30),
            row=1, col=1
        )
        
        fig.add_trace(
            go.Box(x=df[column], name='Box Plot'),
            row=2, col=1
        )
        
        fig.update_layout(
            height=600,
            showlegend=False,
            title_text=f"Distribution Analysis: {column}"
        )
        
        return fig
    
    @staticmethod
    def create_correlation_heatmap(df: pd.DataFrame) -> go.Figure:
        """Create correlation heatmap for numeric columns."""
        numeric_cols = df.select_dtypes(include=[np.number]).columns
        if len(numeric_cols) < 2:
            return go.Figure()
        
        corr_matrix = df[numeric_cols].corr()
        
        fig = go.Figure(data=go.Heatmap(
            z=corr_matrix.values,
            x=corr_matrix.columns,
            y=corr_matrix.index,
            colorscale='RdBu',
            zmid=0,
            text=np.round(corr_matrix.values, 2),
            texttemplate='%{text}',
            textfont={"size": 10},
            hoverongaps=False
        ))
        
        fig.update_layout(
            title='Correlation Heatmap',
            height=500,
            width=700
        )
        
        return fig
    
    @staticmethod
    def create_time_series(df: pd.DataFrame, date_col: str, value_col: str) -> go.Figure:
        """Create time series plot."""
        fig = go.Figure()
        
        fig.add_trace(go.Scatter(
            x=df[date_col],
            y=df[value_col],
            mode='lines+markers',
            name=value_col,
            hovertemplate='%{x}<br>%{y:.2f}<extra></extra>'
        ))
        
        fig.update_layout(
            title=f'Time Series: {value_col}',
            xaxis_title=date_col,
            yaxis_title=value_col,
            hovermode='x unified'
        )
        
        return fig
    
    @staticmethod
    def create_scatter_plot(
        df: pd.DataFrame,
        x_col: str,
        y_col: str,
        color_col: Optional[str] = None,
        size_col: Optional[str] = None
    ) -> go.Figure:
        """Create scatter plot with optional color and size dimensions."""
        fig = px.scatter(
            df,
            x=x_col,
            y=y_col,
            color=color_col,
            size=size_col,
            title=f'{y_col} vs {x_col}',
            hover_data=df.columns.tolist()
        )
        
        fig.update_layout(height=500)
        return fig

class SnapshotManager:
    """Manages scheduled data snapshots."""
    
    def __init__(self, snapshot_dir: str):
        """Initialize snapshot manager."""
        self.snapshot_dir = Path(snapshot_dir)
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)
        self.scheduler = BackgroundScheduler()
        self.scheduler.start()
        logger.info(f"Snapshot manager initialized. Directory: {self.snapshot_dir}")
    
    def take_snapshot(self, df: pd.DataFrame, name: str) -> str:
        """
        Take a snapshot of current data.
        
        Args:
            df: DataFrame to snapshot
            name: Name for the snapshot
            
        Returns:
            Path to snapshot file
        """
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{name}_{timestamp}.csv"
        filepath = self.snapshot_dir / filename
        
        df.to_csv(filepath, index=False)
        logger.info(f"Snapshot saved: {filepath}")
        
        return str(filepath)
    
    def schedule_snapshot(
        self,
        df: pd.DataFrame,
        name: str,
        interval_hours: Optional[int] = None,
        cron_expression: Optional[str] = None
    ) -> None:
        """
        Schedule periodic snapshots.
        
        Args:
            df: DataFrame to snapshot
            name: Base name for snapshots
            interval_hours: Interval in hours between snapshots
            cron_expression: Cron expression for scheduling
        """
        if interval_hours:
            trigger = IntervalTrigger(hours=interval_hours)
        elif cron_expression:
            trigger = CronTrigger.from_crontab(cron_expression)
        else:
            raise ValueError("Either interval_hours or cron_expression must be provided")
        
        self.scheduler.add_job(
            self.take_snapshot,
            trigger,
            args=[df, name],
            id=f"snapshot_{name}",
            replace_existing=True
        )
        
        logger.info(f"Scheduled snapshot: {name}")

def load_data(file) -> Optional[pd.DataFrame]:
    """
    Load data from uploaded file.
    
    Args:
        file: Uploaded file object
        
    Returns:
        Loaded DataFrame or None if loading fails
    """
    try:
        file_extension = file.name.split('.')[-1].lower()
        
        if file_extension == 'csv':
            df = pd.read_csv(file)
        elif file_extension in ['xls', 'xlsx']:
            df = pd.read_excel(file)
        elif file_extension == 'json':
            df = pd.read_json(file)
        else:
            st.error(f"Unsupported file format: {file_extension}")
            return None
        
        logger.info(f"Loaded file: {file.name} ({len(df)} rows, {len(df.columns)} columns)")
        return df
        
    except Exception as e:
        logger.error(f"Error loading file: {str(e)}", exc_info=True)
        st.error(f"Error loading file: {str(e)}")
        return None

def display_data_overview(df: pd.DataFrame) -> None:
    """Display data overview information."""
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Rows", len(df))
    with col2:
        st.metric("Columns", len(df.columns))
    with col3:
        st.metric("Missing Values", df.isnull().sum().sum())
    with col4:
        st.metric("Duplicate Rows", df.duplicated().sum())

def main():
    """Main dashboard application."""
    
    # Sidebar
    st.sidebar.title("📊 Data Dashboard")
    st.sidebar.markdown("---")
    
    # File upload section
    st.sidebar.header("1. Upload Data")
    uploaded_file = st.sidebar.file_uploader(
        "Choose a file",
        type=['csv', 'xlsx', 'xls', 'json'],
        help="Upload your data file for analysis"
    )
    
    if uploaded_file is not None:
        df = load_data(uploaded_file)
        if df is not None:
            st.session_state.data = df
            st.session_state.file_name = uploaded_file.name
            st.session_state.cleaned_data = df.copy()
    
    # Data cleaning section
    st.sidebar.header("2. Data Cleaning")
    
    if st.session_state.data is not None:
        df = st.session_state.cleaned_data.copy()
        
        # Cleaning options
        clean_options = st.sidebar.multiselect(
            "Cleaning Operations",
            ["Remove Duplicates", "Handle Missing Values", "Remove Outliers"],
            default=["Handle Missing Values"]
        )
        
        if "Handle Missing Values" in clean_options:
            missing_strategy = st.sidebar.selectbox(
                "Missing Value Strategy",
                ["mean", "median", "mode", "drop", "fill"],
                index=0
            )
            
            if missing_strategy == "fill":
                fill_value = st.sidebar.text_input("Fill Value", "0")
            else:
                fill_value = None
            
            df = DataCleaner.handle_missing_values(
                df, strategy=missing_strategy, fill_value=fill_value
            )
        
        if "Remove Duplicates" in clean_options:
            df = DataCleaner.remove_duplicates(df)
        
        if "Remove Outliers" in clean_options:
            numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
            outlier_cols = st.sidebar.multiselect(
                "Columns for Outlier Removal",
                numeric_cols
            )
            if outlier_cols:
                outlier_method = st.sidebar.selectbox(
                    "Outlier Method",
                    ["iqr", "zscore"]
                )
                df = DataCleaner.remove_outliers(df, outlier_cols, outlier_method)
        
        st.session_state.cleaned_data = df
    
    # Main content area
    st.title("📊 Data Analysis Dashboard")
    
    if st.session_state.data is None:
        st.info("👈 Please upload a data file to get started")
        
        # Demo data option
        if st.button("Load Demo Data"):
            demo_data = pd.DataFrame({
                'Date': pd.date_range('2023-01-01', periods=100, freq='D'),
                'Sales': np.random.normal(1000, 200, 100).cumsum(),
                'Customers': np.random.randint(50, 200, 100),
                'Revenue': np.random.normal(5000, 1000, 100).cumsum(),
                'Category': np.random.choice(['A', 'B', 'C', 'D'], 100),
                'Region': np.random.choice(['North', 'South', 'East', 'West'], 100)
            })
            st.session_state.data = demo_data
            st.session_state.cleaned_data = demo_data.copy()
            st.session_state.file_name = "demo_data.csv"
            st.rerun()
        
        return
    
    # Display tabs for analysis
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📋 Data Preview", "📊 Visualizations", "📈 Statistics",
        "🔍 Exploration", "💾 Export"
    ])
    
    df = st.session_state.cleaned_data
    
    with tab1:
        st.header("Data Preview")
        display_data_overview(df)
        
        st.subheader("Raw Data")
        n_rows = st.slider("Rows to display", 5, min(len(df), 100), 10)
        st.dataframe(df.head(n_rows), use_container_width=True)
        
        st.subheader("Data Info")
        col1, col2 = st.columns(2)
        
        with col1:
            st.write("Column Types:")
            st.write(df.dtypes.to_frame('Type'))
        
        with col2:
            st.write("Missing Values:")
            st.write(df.isnull().sum().to_frame('Missing'))
    
    with tab2:
        st.header("Visualizations")
        
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        categorical_cols = df.select_dtypes(include=['object']).columns.tolist()
        
        viz_type = st.selectbox(
            "Visualization Type",
            ["Distribution", "Correlation Heatmap", "Scatter Plot", "Bar Chart", "Time Series"]
        )
        
        visualizer = DataVisualizer()
        
        if viz_type == "Distribution" and numeric_cols:
            col = st.selectbox("Select Column", numeric_cols)
            fig = visualizer.create_distribution_plot(df, col)
            st.plotly_chart(fig, use_container_width=True)
        
        elif viz_type == "Correlation Heatmap" and len(numeric_cols) > 1:
            fig = visualizer.create_correlation_heatmap(df)
            st.plotly_chart(fig, use_container_width=True)
        
        elif viz_type == "Scatter Plot" and len(numeric_cols) >= 2:
            col1 = st.selectbox("X Axis", numeric_cols)
            col2 = st.selectbox("Y Axis", [c for c in numeric_cols if c != col1])
            color_col = st.selectbox("Color (optional)", ["None"] + categorical_cols)
            fig = visualizer.create_scatter_plot(
                df, col1, col2,
                color_col=None if color_col == "None" else color_col
            )
            st.plotly_chart(fig, use_container_width=True)
        
        elif viz_type == "Bar Chart":
            if categorical_cols:
                cat_col = st.selectbox("Category", categorical_cols)
                if numeric_cols:
                    val_col = st.selectbox("Value", numeric_cols)
                    agg_func = st.selectbox("Aggregation", ["mean", "sum", "count", "max", "min"])
                    
                    if agg_func == "count":
                        plot_df = df[cat_col].value_counts().reset_index()
                        plot_df.columns = [cat_col, 'count']
                        fig = px.bar(plot_df, x=cat_col, y='count')
                    else:
                        plot_df = df.groupby(cat_col)[val_col].agg(agg_func).reset_index()
                        fig = px.bar(plot_df, x=cat_col, y=val_col)
                    
                    st.plotly_chart(fig, use_container_width=True)
            else:
                st.warning("No categorical columns found for bar chart")
        
        elif viz_type == "Time Series":
            date_cols = []
            for col in df.columns:
                if pd.api.types.is_datetime64_any_dtype(df[col]):
                    date_cols.append(col)
            
            if not date_cols:
                st.warning("No datetime columns detected. Please convert a column to datetime first.")
                if st.checkbox("Try parsing date columns"):
                    for col in df.columns:
                        try:
                            df[col] = pd.to_datetime(df[col])
                            if pd.api.types.is_datetime64_any_dtype(df[col]):
                                date_cols.append(col)
                                st.success(f"Converted {col} to datetime")
                        except:
                            pass
            else:
                date_col = st.selectbox("Date Column", date_cols)
                if numeric_cols:
                    value_col = st.selectbox("Value Column", numeric_cols)
                    fig = visualizer.create_time_series(df, date_col, value_col)
                    st.plotly_chart(fig, use_container_width=True)
    
    with tab3:
        st.header("Summary Statistics")
        
        if numeric_cols:
            st.subheader("Numeric Columns Statistics")
            stats_df = df[numeric_cols].describe()
            st.dataframe(stats_df, use_container_width=True)
            
            # Additional statistics
            st.subheader("Additional Statistics")
            for col in numeric_cols:
                with st.expander(f"📊 {col}"):
                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        st.metric("Skewness", f"{df[col].skew():.2f}")
                    with col2:
                        st.metric("Kurtosis", f"{df[col].kurtosis():.2f}")
                    with col3:
                        st.metric("Unique Values", df[col].nunique())
                    with col4:
                        st.metric("Missing", df[col].isnull().sum())
        
        if categorical_cols:
            st.subheader("Categorical Columns Statistics")
            for col in categorical_cols[:5]:  # Limit to 5 for performance
                with st.expander(f"📋 {col}"):
                    value_counts = df[col].value_counts().head(10)
                    fig = px.bar(x=value_counts.index, y=value_counts.values)
                    st.plotly_chart(fig, use_container_width=True)
    
    with tab4:
        st.header("Data Exploration")
        
        st.subheader("Filter Data")
        filters = []
        
        for col in df.columns:
            if df[col].dtype in ['object', 'category']:
                unique_vals = df[col].unique()
                if len(unique_vals) < 20:
                    selected = st.multiselect(
                        f"Filter {col}",
                        unique_vals,
                        key=f"filter_{col}"
                    )
                    if selected:
                        filters.append((col, selected))
            elif df[col].dtype in ['int64', 'float64']:
                min_val = float(df[col].min())
                max_val = float(df[col].max())
                if min_val < max_val:
                    range_vals = st.slider(
                        f"Range for {col}",
                        min_val, max_val,
                        (min_val, max_val),
                        key=f"range_{col}"
                    )
                    filters.append((col, range_vals))
        
        # Apply filters
        filtered_df = df.copy()
        for col, val in filters:
            if isinstance(val, list):
                filtered_df = filtered_df[filtered_df[col].isin(val)]
            elif isinstance(val, tuple):
                filtered_df = filtered_df[
                    (filtered_df[col] >= val[0]) & 
                    (filtered_df[col] <= val[1])
                ]
        
        st.write(f"Filtered rows: {len(filtered_df)}")
        st.dataframe(filtered_df, use_container_width=True)
        
        st.subheader("Pivot Table")
        if categorical_cols and numeric_cols:
            pivot_index = st.selectbox("Row", categorical_cols, key="pivot_index")
            pivot_columns = st.selectbox("Column", [c for c in categorical_cols if c != pivot_index], key="pivot_columns")
            pivot_values = st.selectbox("Values", numeric_cols, key="pivot_values")
            pivot_agg = st.selectbox("Aggregation", ["mean", "sum", "count"], key="pivot_agg")
            
            try:
                pivot_table = pd.pivot_table(
                    filtered_df,
                    values=pivot_values,
                    index=pivot_index,
                    columns=pivot_columns,
                    aggfunc=pivot_agg,
                    fill_value=0
                )
                st.dataframe(pivot_table, use_container_width=True)
            except Exception as e:
                st.error(f"Error creating pivot table: {str(e)}")
    
    with tab5:
        st.header("Export Data")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("Export Options")
            export_format = st.selectbox(
                "Format",
                ["CSV", "Excel", "JSON"]
            )
            
            if st.button("Download Cleaned Data"):
                if export_format == "CSV":
                    csv = df.to_csv(index=False)
                    st.download_button(
                        label="Download CSV",
                        data=csv,
                        file_name=f"cleaned_{st.session_state.file_name}",
                        mime="text/csv"
                    )
                elif export_format == "Excel":
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                        df.to_excel(writer, index=False, sheet_name='Cleaned Data')
                    st.download_button(
                        label="Download Excel",
                        data=output.getvalue(),
                        file_name=f"cleaned_{st.session_state.file_name.replace('.csv', '.xlsx')}",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                elif export_format == "JSON":
                    json_str = df.to_json(orient='records')
                    st.download_button(
                        label="Download JSON",
                        data=json_str,
                        file_name=f"cleaned_{st.session_state.file_name.replace('.csv', '.json')}",
                        mime="application/json"
                    )
        
        with col2:
            st.subheader("Snapshot Scheduler")
            snapshot_manager = SnapshotManager(st.session_state.snapshot_dir)
            
            if st.button("Take Snapshot Now"):
                filepath = snapshot_manager.take_snapshot(
                    df,
                    st.session_state.file_name.replace('.', '_')
                )
                st.success(f"Snapshot saved: {filepath}")
            
            st.write("Schedule Automatic Snapshots")
            interval = st.number_input(
                "Interval (hours)",
                min_value=1,
                value=24,
                step=1
            )
            
            if st.button("Schedule Snapshots"):
                snapshot_manager.schedule_snapshot(
                    df,
                    st.session_state.file_name.replace('.', '_'),
                    interval_hours=interval
                )
                st.success(f"Scheduled snapshots every {interval} hours")
            
            # Show existing snapshots
            snapshots = list(Path(st.session_state.snapshot_dir).glob("*.csv"))
            if snapshots:
                st.write(f"Existing snapshots: {len(snapshots)}")
                for snap in snapshots[:10]:
                    st.write(f"- {snap.name}")

if __name__ == "__main__":
    main()
