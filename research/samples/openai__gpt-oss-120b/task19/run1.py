"""
pdf_report.py

A simple PDF report generator using ReportLab and Matplotlib.
Supports header/footer, tables, bar/line/pie charts, and multi‑page layouts.

Usage example:
    generator = PDFReportGenerator("report.pdf")
    generator.add_header("My Company • Quarterly Report")
    generator.add_footer("Confidential • Page %(page)d")
    generator.add_table([["Header1", "Header2"], [1, 2], [3, 4]])
    generator.add_chart(
        chart_type="bar",
        data={"Category A": [5, 3, 6], "Category B": [2, 7, 4]},
        title="Sales by Category"
    )
    generator.build()
"""

from __future__ import annotations

import io
import os
from typing import Any, Dict, List, Optional, Tuple

import matplotlib.pyplot as plt
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, inch
from reportlab.platypus import (
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Table,
    TableStyle,
    Flowable,
)

# --------------------------------------------------------------------------- #
# Helper for secure file handling
# --------------------------------------------------------------------------- #
def _ensure_parent_dir(path: str) -> None:
    """Create parent directories if they do not exist, in a safe manner."""
    parent = os.path.abspath(os.path.dirname(path))
    os.makedirs(parent, exist_ok=True)


# --------------------------------------------------------------------------- #
# PDFReportGenerator definition
# --------------------------------------------------------------------------- #
class PDFReportGenerator:
    """
    PDFReportGenerator builds a PDF document with optional header/footer,
    tables, and Matplotlib charts.

    Parameters
    ----------
    filename: str
        Destination PDF file path.
    pagesize: Tuple[float, float], optional
        Page size (default: letter). Use ``reportlab.lib.pagesizes`` constants.
    """

    def __init__(self, filename: str, pagesize: Tuple[float, float] = letter) -> None:
        _ensure_parent_dir(filename)
        self.filename: str = filename
        self.pagesize: Tuple[float, float] = pagesize
        self.elements: List[Flowable] = []
        self._header_text: Optional[str] = None
        self._footer_text: Optional[str] = None
        self.styles = getSampleStyleSheet()
        self.normal_style: ParagraphStyle = self.styles["Normal"]
        self.title_style: ParagraphStyle = self.styles["Title"]

    # ------------------------------------------------------------------- #
    # Header / Footer handling
    # ------------------------------------------------------------------- #
    def add_header(self, text: str) -> None:
        """Set header text displayed on each page."""
        self._header_text = text

    def add_footer(self, text: str) -> None:
        """Set footer text displayed on each page.
        Use ``%(page)d`` placeholder for the page number."""
        self._footer_text = text

    @staticmethod
    def _page_decorator(canvas, doc, header: Optional[str], footer: Optional[str]) -> None:
        """Internal callback attached to ``SimpleDocTemplate`` to render header/footer."""
        canvas.saveState()
        width, height = doc.pagesize

        # Header
        if header:
            canvas.setFont("Helvetica", 9)
            canvas.drawString(cm, height - cm + 5, header)

        # Footer
        if footer:
            canvas.setFont("Helvetica", 9)
            page_num = canvas.getPageNumber()
            footer_resolved = footer.replace("%(page)d", str(page_num))
            canvas.drawString(cm, cm - 10, footer_resolved)

        canvas.restoreState()

    # ------------------------------------------------------------------- #
    # Table handling
    # ------------------------------------------------------------------- #
    def add_table(
        self,
        data: List[List[Any]],
        col_widths: Optional[List[float]] = None,
        style: Optional[TableStyle] = None,
        repeat_rows: int = 1,
    ) -> None:
        """
        Add a table to the report.

        Parameters
        ----------
        data : List[List[Any]]
            2‑D list representing rows and columns.
        col_widths : List[float], optional
            Column widths in points (default: auto).
        style : TableStyle, optional
            Custom ReportLab TableStyle.
        repeat_rows : int, optional
            Number of header rows to repeat on each page.
        """
        if not data or not isinstance(data, list) or not isinstance(data[0], list):
            raise ValueError("Table data must be a non‑empty list of lists.")

        table = Table(data, colWidths=col_widths, repeatRows=repeat_rows)

        default_style = TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
            ]
        )
        table.setStyle(style or default_style)
        self.elements.append(table)

    # ------------------------------------------------------------------- #
    # Chart handling (Matplotlib -> ReportLab Image)
    # ------------------------------------------------------------------- #
    def add_chart(
        self,
        chart_type: str,
        data: Dict[str, List[float]],
        title: Optional[str] = None,
        width: float = 6 * inch,
        height: float = 4 * inch,
    ) -> None:
        """
        Generate a chart with Matplotlib and embed it as an image.

        Parameters
        ----------
        chart_type : {"bar", "line", "pie"}
            Type of chart to render.
        data : Dict[str, List[float]]
            Mapping of series names to numeric data.
        title : str, optional
            Chart title.
        width, height : float
            Desired image size in points.
        """
        if chart_type not in {"bar", "line", "pie"}:
            raise ValueError(f"Unsupported chart_type '{chart_type}'. Choose from bar, line, pie.")

        # Prepare figure
        plt.close("all")
        fig, ax = plt.subplots(figsize=(width / inch, height / inch), dpi=96)

        try:
            if chart_type == "pie":
                # For pie we expect a single series
                if len(data) != 1:
                    raise ValueError("Pie chart expects exactly one data series.")
                label, values = next(iter(data.items()))
                ax.pie(values, labels=label, autopct="%1.1f%%", startangle=90)
                ax.axis("equal")
            else:
                x = range(len(next(iter(data.values()))))
                for label, values in data.items():
                    if chart_type == "bar":
                        ax.bar(x, values, label=label, alpha=0.7)
                    elif chart_type == "line":
                        ax.plot(x, values, marker="o", label=label)
                ax.set_xticks(list(x))
                ax.legend()
        except Exception as exc:
            plt.close(fig)
            raise RuntimeError(f"Failed to generate {chart_type} chart: {exc}") from exc

        if title:
            ax.set_title(title)

        buf = io.BytesIO()
        try:
            fig.savefig(buf