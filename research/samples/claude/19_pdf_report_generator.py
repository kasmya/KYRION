"""
### Task 19: PDF Report Generator (ReportLab)

Generates polished PDF reports from CSV data, including tables, a bar
chart, headers/footers with page numbers, and an optional logo image.

Requirements:
    pip install reportlab pandas

Usage:
    python 19_pdf_report_generator.py --csv sales.csv --output report.pdf --title "Q3 Sales Report"
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import List, Optional

import pandas as pd
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("pdf_report_generator")


class ReportGenerationError(Exception):
    """Raised when the PDF report cannot be generated."""


def load_csv_data(csv_path: Path) -> pd.DataFrame:
    """Loads and lightly validates a CSV file for reporting."""
    if not csv_path.is_file():
        raise ReportGenerationError(f"CSV file not found: {csv_path}")
    try:
        df = pd.read_csv(csv_path)
    except Exception as exc:  # noqa: BLE001
        raise ReportGenerationError(f"Failed to parse CSV '{csv_path}': {exc}") from exc

    if df.empty:
        raise ReportGenerationError(f"CSV file '{csv_path}' contains no rows")
    return df


def _build_table(df: pd.DataFrame, max_rows: int = 30) -> Table:
    """Builds a styled ReportLab Table from a DataFrame (truncated for readability)."""
    display_df = df.head(max_rows)
    data = [list(display_df.columns)] + display_df.astype(str).values.tolist()

    table = Table(data, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c3e50")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f2f2")]),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    return table


def _build_bar_chart(df: pd.DataFrame, category_col: str, value_col: str) -> Drawing:
    """Builds a simple vertical bar chart Drawing from two numeric/categorical columns."""
    grouped = df.groupby(category_col)[value_col].sum().sort_values(ascending=False).head(10)

    drawing = Drawing(400, 200)
    chart = VerticalBarChart()
    chart.x = 30
    chart.y = 20
    chart.height = 150
    chart.width = 340
    chart.data = [list(grouped.values)]
    chart.categoryAxis.categoryNames = [str(c) for c in grouped.index]
    chart.categoryAxis.labels.angle = 30
    chart.categoryAxis.labels.dy = -10
    chart.bars[0].fillColor = colors.HexColor("#2980b9")
    drawing.add(chart)
    return drawing


def _header_footer(canvas, doc) -> None:
    """Draws a header and footer with page numbers on every page."""
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.drawString(0.75 * inch, letter[1] - 0.5 * inch, "Confidential Report")
    canvas.drawRightString(
        letter[0] - 0.75 * inch, 0.5 * inch, f"Page {doc.page}"
    )
    canvas.restoreState()


def generate_report(
    csv_path: Path,
    output_path: Path,
    title: str,
    category_col: Optional[str] = None,
    value_col: Optional[str] = None,
    logo_path: Optional[Path] = None,
) -> None:
    """Generates a full PDF report from CSV data.

    Args:
        csv_path: Path to the source CSV file.
        output_path: Where to write the generated PDF.
        title: Title displayed at the top of the report.
        category_col: Column to group by for the bar chart (defaults to first column).
        value_col: Numeric column to sum for the bar chart (defaults to first numeric column).
        logo_path: Optional path to a logo image to place at the top of the report.

    Raises:
        ReportGenerationError: If data loading or PDF generation fails.
    """
    df = load_csv_data(csv_path)
    styles = getSampleStyleSheet()

    story: List = []

    if logo_path and logo_path.is_file():
        try:
            story.append(Image(str(logo_path), width=1.5 * inch, height=1.5 * inch))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not embed logo '%s': %s", logo_path, exc)

    story.append(Paragraph(title, styles["Title"]))
    story.append(Spacer(1, 0.25 * inch))
    story.append(Paragraph(f"Generated from: {csv_path.name}", styles["Normal"]))
    story.append(Spacer(1, 0.25 * inch))

    story.append(Paragraph("Data Table", styles["Heading2"]))
    story.append(_build_table(df))
    story.append(Spacer(1, 0.3 * inch))

    numeric_columns = df.select_dtypes(include="number").columns.tolist()
    category_col = category_col or df.columns[0]
    value_col = value_col or (numeric_columns[0] if numeric_columns else None)

    if value_col and category_col in df.columns and value_col in df.columns:
        story.append(PageBreak())
        story.append(Paragraph(f"Summary Chart: {value_col} by {category_col}", styles["Heading2"]))
        try:
            story.append(_build_bar_chart(df, category_col, value_col))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to build chart: %s", exc)
            story.append(Paragraph("(Chart unavailable for this dataset)", styles["Normal"]))
    else:
        logger.info("Skipping chart: no suitable numeric column found")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        doc = SimpleDocTemplate(str(output_path), pagesize=letter)
        doc.build(story, onFirstPage=_header_footer, onLaterPages=_header_footer)
    except Exception as exc:  # noqa: BLE001
        raise ReportGenerationError(f"Failed to write PDF '{output_path}': {exc}") from exc

    logger.info("Report generated at '%s'", output_path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate a PDF report from a CSV file.")
    parser.add_argument("--csv", required=True, help="Path to input CSV file")
    parser.add_argument("--output", required=True, help="Path to output PDF file")
    parser.add_argument("--title", default="Data Report", help="Report title")
    parser.add_argument("--category-col", help="Column to group by for the chart")
    parser.add_argument("--value-col", help="Numeric column to sum for the chart")
    parser.add_argument("--logo", help="Optional path to a logo image")
    return parser


def main(argv: List[str] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        generate_report(
            csv_path=Path(args.csv),
            output_path=Path(args.output),
            title=args.title,
            category_col=args.category_col,
            value_col=args.value_col,
            logo_path=Path(args.logo) if args.logo else None,
        )
        return 0
    except ReportGenerationError as exc:
        logger.error("Report generation failed: %s", exc)
        return 1
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected error: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
