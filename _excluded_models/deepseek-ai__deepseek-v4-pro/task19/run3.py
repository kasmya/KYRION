"""
PDF Report Generator Module

This module provides functionality to generate PDF reports with headers, footers,
data tables, and chart insertion (bar, line, pie). It supports multi-page documents
and includes comprehensive error handling.

Dependencies:
    - reportlab (PyPI package)
"""

import io
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Union

from reportlab.graphics.shapes import Drawing
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.charts.linecharts import HorizontalLineChart
from reportlab.graphics.charts.piecharts import Pie
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch, mm
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    Image,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.flowables import Flowable

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Custom Flowable for Matplotlib-like charts using reportlab.graphics
# ---------------------------------------------------------------------------


class ChartFlowable(Flowable):
    """A flowable that renders a reportlab.graphics chart."""

    def __init__(self, drawing: Drawing, width: float, height: float):
        self._drawing = drawing
        self._width = width
        self._height = height
        super().__init__()

    def wrap(self, availWidth: float, availHeight: float) -> Tuple[float, float]:
        return (self._width, self._height)

    def draw(self) -> None:
        self._drawing.drawOn(self.canv, 0, 0)


# ---------------------------------------------------------------------------
    # Helper functions for chart creation
# ---------------------------------------------------------------------------


def _create_bar_chart(
    data: List[List[float]],
    categories: List[str],
    series_names: List[str],
    width: int = 400,
    height: int = 250,
    title: Optional[str] = None,
    x_label: Optional[str] = None,
    y_label: Optional[str] = None,
) -> Drawing:
    """
    Create a vertical bar chart Drawing.

    Args:
        data: Nested list where each inner list represents a data series.
        categories: Labels for the x-axis categories.
        series_names: Names for each data series.
        width: Drawing width in points.
        height: Drawing height in points.
        title: Optional chart title.
        x_label: Optional x-axis label.
        y_label: Optional y-axis label.

    Returns:
        Drawing object ready for inclusion in a PDF.
    """
    if not data or not categories:
        raise ValueError("Data and categories must not be empty.")

    drawing = Drawing(width, height)
    chart = VerticalBarChart()
    chart.x = 50
    chart.y = 50
    chart.width = width - 80
    chart.height = height - 80
    chart.data = data
    chart.categoryAxis.categoryNames = categories
    chart.categoryAxis.labels.boxAnchor = "ne"
    chart.categoryAxis.labels.angle = 45
    chart.valueAxis.valueMin = 0

    # Color cycle
    palette = [colors.HexColor(c) for c in ("#4472C4", "#ED7D31", "#A5A5A5")]
    for i, _ in enumerate(data):
        if i < len(palette):
            chart.bars[i].fillColor = palette[i]
            chart.bars[i].strokeColor = colors.white

    if title:
        drawing.add(
            String(width / 2, height - 20, title, textAnchor="middle", fontSize=12)
        )
    if x_label:
        drawing.add(String(width / 2, 20, x_label, textAnchor="middle", fontSize=10))
    if y_label:
        drawing.add(String(20, height / 2, y_label, textAnchor="middle", fontSize=10, angle=90))

    drawing.add(chart)
    return drawing


def _create_line_chart(
    data: List[List[Tuple]],
    categories: List[str],
    series_names: List[str],
    width: int = 400,
    height: int = 250,
    title: Optional[str] = None,
    x_label: Optional[str] = None,
    y_label: Optional[str] = None,
) -> Drawing:
    """
    Create a horizontal line chart Drawing.

    Args:
        data: Nested list where each inner list is a data series.
        categories: Labels for the x-axis categories.
        series_names: Names for each data series.
        width: Drawing width in points.
        height: Drawing height in points.
        title: Optional chart title.
        x_label: Optional x-axis label.
        y_label: Optional y-axis label.

    Returns:
        Drawing object.
    """
    if not data or not categories:
        raise ValueError("Data and categories must not be empty.")

    drawing = Drawing(width, height)
    chart = HorizontalLineChart()
    chart.x = 50
    chart.y = 50
    chart.width = width - 80
    chart.height = height - 80
    chart.data = data
    chart.categoryAxis.categoryNames = categories
    chart.categoryAxis.labels.angle = 45

    palette = [colors.Hex(c) for c in ("#4472C4", "#ED7D31", "#A5A5A5")]
    for i, series in enumerate(data):
        if i < len(palette):
            chart.lines[i].strokeColor = palette[i]
            chart.lines[i].strokeWidth = 2

    if title:
        drawing.add(String(width / 2, height - 20, title, textAnchor="middle", fontSize=12))
    if x_label:
        drawing.add(String(width / 2, 20, x_label, textAnchor="middle", fontSize=10))
    if y_label:
        drawing.add(String(20, height / 2, y_label, textAnchor="middle", fontSize=10, angle=90))

    drawing.add(chart)
    return drawing


def _create_pie_chart(
    data: List[float],
    labels: List[str],
    width: int = 300,
    height: int = 300,
    title: Optional[str] = None,
) -> Drawing:
    """
    Create a pie chart Drawing.

    Args:
        data: List of numeric values for each slice.
        labels: Labels for each slice.
        width: Drawing width in points.
        height: Drawing height in points.
        title: Optional chart title.

    Returns:
        Drawing object.
    """
    if not data or not labels:
        raise ValueError("Data and labels must not be empty.")
    if len(data) != len(labels):
        raise ValueError("Data and labels must have the same length.")

    drawing = Drawing(width, height)
    pie = Pie()
    pie.x = 50
    pie.y = 50
    pie.width = width - 100
    pie.height = height - 100
    pie.data = data
    pie.labels = labels
    pie.slices.strokeWidth = 0.5
    pie.slices.strokeColor = colors.white

    if title:
        drawing.add(String(width / 2, height - 20, title, textAnchor="middle", fontSize=12))

    drawing.add(pie)
    return drawing


# ---------------------------------------------------------------------------
# Page template with header and footer
# ---------------------------------------------------------------------------


def _header_footer(canvas: canvas.Canvas, doc: BaseDocTemplate) -> None:
    """
    Draw header and footer on each page.

    Args:
        canvas: ReportLab canvas.
        doc: The document being built.
    """
    canvas.saveState()
    # Header
    header_text = getattr(doc, "header_text", "Report")
    canvas.setFont("Helvetica-Bold", 10)
    canvas.drawString(doc.leftMargin, doc.height + doc.topMargin - 15, header_text)

    # Footer
    footer_text = f"Page {canvas.getPageNumber()}"
    canvas.setFont("Helvetica", 8)
    canvas.drawRightString(
        doc.width + doc.leftMargin,
        doc.bottomMargin - 15,
        footer_text,
    )
    canvas.restoreState()


# ---------------------------------------------------------------------------
# Main PDF Report Generator
# ---------------------------------------------------------------------------


class PDFReportGenerator:
    """
    Build a PDF report with headers, footers, tables, and charts.

    Usage:
        report = PDFReportGenerator("Monthly Report", page_size=A4)
        report.add_paragraph("Introduction text...")
        report.add_table([["Col1", "Col2"], ["A", "B"]])
        report.add_bar_chart(...)
        report.generate("output.pdf")
    """

    def __init__(
        self,
        title: str = "Report",
        author: str = "PDFReportGenerator",
        page_size: Tuple[float, float] = A4,
        margins: Tuple[float, float, float, float] = (36, 36, 36, 36),
    ) -> None:
        """
        Initialize the report generator.

        Args:
            title: Document title (used in metadata and default header).
            author: Document author metadata.
            page_size: Page size as (width, height) in points (default A4).
            margins: Margins as (left, right, top, bottom) in points.
        """
        self.title: str = title
        self.author: str = author
        self.page_size: Tuple[float, float] = page_size
        self.margins: Tuple[float, float, float, float] = margins

        # Collect content as a list of flowables
        self._elements: List[Flowable] = []

        # Styles
        self.styles = getSampleStyleSheet()
        self._body_style = self.styles["BodyText"]
        self._heading_style = self.styles["Heading1"]

        # Chart dimensions (can be adjusted)
        self.chart_width: int = 400
        self.chart_height: int = 250

    def add_heading(self, text: str, level: int = 1) -> None:
        """
        Add a heading to the report.

        Args:
            text: Heading text.
            level: Heading level (1-3).

        Raises:
            ValueError: If level is unsupported.
        """
        if level not in (1, 2, 3):
            raise ValueError(f"Unsupported heading level: {level}")

        style_map = {1: "Heading1", 2: "Heading2", 3: "Heading3"}
        self._elements.append(Paragraph(text, self.styles[style_map[level]]))
        self._elements.append(Spacer(1, 12))

    def add_paragraph(self, text: str) -> None:
        """
        Add a paragraph of text.

        Args:
            text: Paragraph text.
        """
        self._elements.append(Paragraph(text, self._style_style))
        self._elements.append(Spacer(1, 6))

    def add_table(
        self,
        data: List[List[Any]],
        col_widths: Optional[List[float]] = None,
        repeat_header: bool = True,
    ) -> None:
        """
        Add a data table to the report.

        Args:
            data: Table data with the first row as header.
            col_widths: Optional column widths in points.
            repeat_header: Whether to repeat the header on each page.

        Raises:
            ValueError: If data is empty.
        """
        if not data:
            raise ValueError("Table data must not be empty.")

        # Convert all cells to Paragraphs for better styling
        formatted_data = [
            [Paragraph(str(cell), self._style_style) for cell in row]
            for row in data
        ]

        table = Table(formatted_data, colWidths=col_widths, repeatRows=1 if repeat_header else 0)

        style_cmds = [
            ("BACKGROUND", (0, 0), (-1, 0), colors.Hex("#4472C4")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("ALIGN", (0, 0), (-1, 0), "CENTER"),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 10),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
            ("TOPPADDING", (0, 0), (-1, 0), 8),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.Hex("#F2F2F2")]),
        ]
        table.setStyle(TableStyle(style_cmds))

        self._elements.append(table)
        self._elements.append(Spacer(1, 12))

    def add_bar_chart(
        self,
        data: List[List[Tuple[int, float]]],
        categories: List[str],
        series_names: Optional[List[str]] = None,
        title: Optional[str] = None,
        x_label: Optional[str] = None,
        y_label: Optional[str] = None,
    ) -> None:
        """
        Add a vertical bar chart.

        Args:
            data: List of series, each series being a list of (category_index, value).
            categories: Category labels.
            series_names: Names for each series.
            title: Chart title.
            x_label: X-axis label.
            y_label: Y-axis label.
        """
        if not series_names:
            series_names = [f"Series {i + 1}" for i in range(len(data))]

        drawing = _create_bar_chart(
            data=data,
            categories=categories,
            series_names=series_names,
            width=self.chart_width,
            height=self.chart_height,
            title=title,
            x_label=x_label,
            y_label=y_label,
        )
        self._elements.append(ChartFlowable(drawing, self.chart_width, self.chart_height))
        self._elements.append(Spacer(1, 12))

    def add_line_chart(
        self,
        data: List[List[Tuple[int, float]]],
        categories: List[str],
        series_names: Optional[List[str]] = None,
        title: Optional[str] = None,
        x_label: Optional[str] = None,
        y_label: Optional[str] = None,
    ) -> None:
        """
        Add a line chart.

        Args:
            data: List of series.
            categories: Category labels.
            series_names: Names for each series.
            title: Chart title.
            x_label: X-axis label.
            y_label: Y-axis label.
        """
        if not series_names:
            series_names = [f"Series {i + 1}" for i in range(len(data))]

        drawing = _create_line_chart(
            data=data,
            categories=categories,
            series_names=series_names,
            width=self.chart_width,
            height=self.chart_height,
            title=title,
            x_label=x_label,
            y_label=y_label,
        )
        self._elements.append(ChartFlowable(drawing, self.chart_width, self.chart_height))
        self._elements.append(Spacer(1, 12))

    def add_pie_chart(
        self,
        data: List[float],
        labels: List[str],
        title: Optional[str] = None,
    ) -> None:
        """
        Add a pie chart.

        Args:
            data: Slice values.
            labels: Slice labels.
            title: Chart title.
        """
        drawing = _create_pie_chart(
            data=data,
            labels=labels,
            width=300,
            height=300,
            title=title,
        )
        self._elements.append(ChartFlowable(drawing, 300, 300))
        self._elements.append(Spacer(1, 12))

    def add_page_break(self) -> None:
        """Insert a page break."""
        self._elements.append(PageBreak())

    def generate(self, file_path: str) -> None:
        """
        Generate the PDF report and write it to a file.

        Args:
            file_path: Output file path.

        Raises:
            IOError: If writing fails.
            RuntimeError: If report generation encounters an error.
        """
        try:
            doc = BaseDocTemplate(
                file_path,
                pagesize=self.page_size,
                left_margin=self.margins[0],
                right_margin=self.margin[1],
                top_margin=self.margins[2],
                bottom_margin=self.margins[3],
                title=self.title,
                author=self.author,
                subject=self.title,
            )

            # Attach header text to the doc
            doc.header_text = self.title

            # Create a single frame that fills the page
            frame = Frame(
                doc.left_margin,
                doc.bottom_margin,
                doc.width,
                doc.height,
                id="normal",
            )

            template = PageTemplate(
                id="main",
                frames=[frame],
                onPage=_header_footer,
            )
            doc.addPageTemplates([template])

            # Build the document
            doc.build(self._elements)

            logger.info(f"PDF report generated successfully: {file_path}")

        except Exception as exc:
            logger.error(f"Failed to generate PDF: {exc}", exc_info=True)
            raise RuntimeError(f"PDF generation failed: {exc}") from exc

    def generate_to_bytes(self) -> bytes:
        """
        Generate the PDF report and return it as bytes.

        Returns:
            PDF content as bytes.

        Raises:
            RuntimeError: If generation fails.
        """
        try:
            buffer = io.BytesIO()
            self.generate(buffer)
            buffer.seek(0)
            return buffer.read()
        except Exception as exc:
            raise RuntimeError(f"Failed to generate PDF to bytes: {exc}") from exc


# ---------------------------------------------------------------------------
# Example usage (executed only when run directly)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Create a sample report
    report = PDFReportGenerator(title="Monthly Sales Report", author="Acme Corp")
    report.add_heading("Executive Summary", level=1)
    report.add_paragraph(
        "This report summarizes the monthly sales performance across various regions."
    )
    report.add_heading("Sales Data", level=2)

    table_data = [
        ["