"""
pdf_report.py

A small but feature‑complete PDF report generator built on ReportLab.
It supports:

* Customizable headers and footers (automatically repeated on each page)
* Table rendering from list‑of‑lists data
* Insertion of bar, line, and pie charts (via ReportLab graphics)
* Multi‑page documents with automatic page breaks
* Type hints, comprehensive docstrings and robust error handling
* Security‑oriented defaults (e.g. no external file reads unless explicitly passed)

Only the standard library and the well‑known ``reportlab`` package are required.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from io import BytesIO
from typing import List, Sequence, Tuple, Union, Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    PageTemplate,
    Paragraph,
    Table,
    TableStyle,
    Spacer,
    Flowable,
    KeepTogether,
)
from reportlab.graphics.shapes import Drawing
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.charts.linecharts import HorizontalLineChart
from reportlab.graphics.charts.piecharts import Pie
from reportlab.graphics.widgets.markers import makeMarker

# --------------------------------------------------------------------------- #
# Exceptions
# --------------------------------------------------------------------------- #


class PDFReportError(Exception):
    """Base class for all PDF report related errors."""


class InvalidChartTypeError(PDFReportError, ValueError):
    """Raised when an unsupported chart type is requested."""


class TableDataError(PDFReportError, ValueError):
    """Raised when table data is malformed."""


# --------------------------------------------------------------------------- #
# Helper data structures
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class PageMargins:
    """Page margin definition in points (1/72 inch)."""

    left: float = 2 * cm
    right: float = 2 * cm
    top: float = 2 * cm
    bottom: float = 2 * cm


# --------------------------------------------------------------------------- #
# Core implementation
# --------------------------------------------------------------------------- #


class PDFReportGenerator:
    """
    Generates PDF reports with headers, footers, tables and charts.

    Example
    -------
    >>> report = PDFReportGenerator("out.pdf", title="Sales Report")
    >>> report.add_header("My Company")
    >>> report.add_footer("Page %(page_number)s of %(total_pages)s")
    >>> data = [["Product", "Qty", "Revenue"], ["A", 10, "$100"], ["B", 5, "$50"]]
    >>> report.add_table(data, col_widths=[4*cm, 2*cm, 3*cm])
    >>> chart_data = ([10, 20, 30], ["Jan", "Feb", "Mar"])
    >>> report.add_chart("bar", chart_data, title="Quarterly Sales")
    >>> report.build()
    """

    def __init__(
        self,
        filename: str,
        title: str = "",
        page_size: Tuple[float, float] = A4,
        margins: PageMargins = PageMargins(),
        author: str = "PDFReportGenerator",
    ) -> None:
        """
        Initialise the generator.

        Parameters
        ----------
        filename: str
            Destination file path. The directory must exist and be writable.
        title: str, optional
            Document title (PDF metadata).
        page_size: tuple, optional
            (width, height) in points; defaults to A4.
        margins: PageMargins, optional
            Margins for all pages.
        author: str, optional
            Author metadata.
        """
        if not isinstance(filename, str) or not filename:
            raise PDFReportError("A non‑empty filename must be provided.")
        if not os.path.isdir(os.path.dirname(os.path.abspath(filename))):
            raise PDFReportError(f"Directory does not exist: {os.path.dirname(filename)}")

        self.filename = filename
        self.title = title
        self.author = author
        self.page_size = page_size
        self.margins = margins

        # Internal storage for flowables
        self._story: List[Flowable] = []

        # Header/footer placeholders
        self._header_text: Optional[str] = None
        self._footer_text: Optional[str] = None

        # Styles
        self._styles = getSampleStyleSheet()
        self._styles.add(
            ParagraphStyle(name="TableHeader", parent=self._styles["Normal"], fontSize=10, leading=12, alignment=1)
        )
        self._styles.add(
            ParagraphStyle(name="TableCell", parent=self._styles["Normal"], fontSize=9, leading=11)
        )

    # ----------------------------------------------------------------------- #
    # Header / Footer handling
    # ----------------------------------------------------------------------- #

    def add_header(self, text: str) -> None:
        """Set the header text. It will appear on every page."""
        if not isinstance(text, str):
            raise PDFReportError("Header text must be a string.")
        self._header_text = text

    def add_footer(self, text: str) -> None:
        """
        Set the footer text. Use ``%(page_number)s`` and ``%(total_pages)s`` placeholders
        for automatic substitution.
        """
        if not isinstance(text, str):
            raise PDFReportError("Footer text must be a string.")
        self._footer_text = text

    # ----------------------------------------------------------------------- #
    # Table handling
    # ----------------------------------------------------------------------- #

    def add_table(
        self,
        data: Sequence[Sequence[Union[str, int, float]]],
        col_widths: Optional[Sequence[float]] = None,
        repeat_rows: int = 1,
        style: Optional[TableStyle] = None,
    ) -> None:
        """
        Add a table to the report.

        Parameters
        ----------
        data: 2‑D sequence
            Table data; first row is usually the header.
        col_widths: sequence of float, optional
            Widths for each column (in points). If omitted, columns share available width.
        repeat_rows: int, optional
            Number of rows to repeat on page breaks (e.g., header rows).
        style: TableStyle, optional
            Custom table style. If omitted, a default style is applied.
        """
        if not data or not all(isinstance(row, (list, tuple)) for row in data):
            raise TableDataError("Table data must be a non‑empty 2‑D sequence.")
        if repeat_rows < 0:
            raise TableDataError("repeat_rows cannot be negative.")

        # Default style if none supplied
        if style is None:
            style = TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ]
            )

        tbl = Table(data, colWidths=col_widths, repeatRows=repeat_rows, hAlign="LEFT")
        tbl.setStyle(style)
        self._story.append(KeepTogether([tbl, Spacer(1, 0.2 * cm)]))

    # ----------------------------------------------------------------------- #
    # Chart handling
    # ----------------------------------------------------------------------- #

    def _create_bar_chart(
        self,
        values: Sequence[float],
        categories: Sequence[str],
        width: float,
        height: float,
        title: str = "",
    ) -> Drawing:
        """Internal helper to build a vertical bar chart."""
        drawing = Drawing(width, height)
        chart = VerticalBarChart()
        chart.x = 0
        chart.y = 0
        chart.width = width
        chart.height = height
        chart.data = [list(values)]
        chart.categoryAxis.categoryNames = list(categories)
        chart.barWidth = 0.5 * cm
        chart.groupSpacing = 0.2 * cm
        chart.barSpacing = 0.1 * cm
        chart.valueAxis.valueMin = 0
        chart.valueAxis.valueMax = max(values) * 1.1 if values else 1
        chart.valueAxis.valueStep = max(1, int(chart.valueAxis.valueMax / 5))
        chart.b