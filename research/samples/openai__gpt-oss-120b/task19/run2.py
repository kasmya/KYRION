"""
pdf_report.py

A lightweight PDF report generator supporting page headers/footers, data tables,
and chart insertion (bar, line, pie). The implementation relies on the
ReportLab library for PDF creation and Matplotlib for chart rendering.
All functions include type hints, docstrings, and explicit error handling.
"""

from __future__ import annotations

import io
import os
import tempfile
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import matplotlib.pyplot as plt
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

__all__ = [
    "PDFReportGenerator",
    "ReportGenerationError",
    "InvalidChartTypeError",
    "InvalidTableDataError",
]


class ReportGenerationError(RuntimeError):
    """Base exception for all report generation errors."""


class InvalidChartTypeError(ReportGenerationError):
    """Raised when an unsupported chart type is requested."""


class InvalidTableDataError(ReportGenerationError):
    """Raised when table data cannot be interpreted."""


@dataclass
class PDFReportGenerator:
    """
    Helper class to build PDF reports with optional headers, footers,
    tables, and charts. Content is added sequentially; the generator
    automatically handles pagination.
    """

    title: str = "Report"
    page_size: Tuple[float, float] = A4
    margin: float = 2 * cm
    header_text: Optional[str] = None
    footer_text: Optional[str] = None
    _elements: List[Any] = field(default_factory=list, init=False)
    _styles: Dict[str, ParagraphStyle] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        """Initialize internal styles used throughout the document."""
        stylesheet = getSampleStyleSheet()
        self._styles["title"] = stylesheet["Title"]
        self._styles["normal"] = stylesheet["BodyText"]
        self._styles["header"] = ParagraphStyle(
            name="Header",
            parent=stylesheet["Normal"],
            fontSize=9,
            alignment=1,  # center
            textColor=colors.grey,
        )
        self._styles["footer"] = ParagraphStyle(
            name="Footer",
            parent=stylesheet["Normal"],
            fontSize=9,
            alignment=1,  # center
            textColor=colors.grey,
        )

    # --------------------------------------------------------------------- #
    # Header / Footer handling
    # --------------------------------------------------------------------- #
    def set_header(self, text: str) -> None:
        """
        Set the header text displayed on each page.

        Args:
            text: Header string (plain text).

        Raises:
            ValueError: If ``text`` is empty or only whitespace.
        """
        if not text or not text.strip():
            raise ValueError("Header text must be a non‑empty string.")
        self.header_text = text

    def set_footer(self, text: str) -> None:
        """
        Set the footer text displayed on each page.

        Args:
            text: Footer string (plain text).

        Raises:
            ValueError: If ``text`` is empty or only whitespace.
        """
        if not text or not text.strip():
            raise ValueError("Footer text must be a non‑empty string.")
        self.footer_text = text

    # --------------------------------------------------------------------- #
    # Table handling
    # --------------------------------------------------------------------- #
    def add_table(
        self,
        data: Union[pd.DataFrame, Sequence[Dict[str, Any]]],
        col_widths: Optional[Sequence[float]] = None,
        style: Optional[TableStyle] = None,
    ) -> None:
        """
        Append a data table to the report.

        Args:
            data: Either a pandas DataFrame or a sequence of dictionaries
                  where each dict represents a row.
            col_widths: Optional column width specifications (in points).
            style: Optional ReportLab TableStyle; a default style is used if omitted.

        Raises:
            InvalidTableDataError: If ``data`` cannot be transformed into a table.
            ValueError: If ``col_widths`` length mismatches number of columns.
        """
        try:
            if isinstance(data, pd.DataFrame):
                df = data.copy()
            else:
                df = pd.DataFrame(list(data))
        except Exception as exc:
            raise InvalidTableDataError(f"Failed to convert input to DataFrame: {exc}") from exc

        if df.empty:
            raise InvalidTableDataError("Provided table data is empty.")

        # Prepare table data (header + rows)
        table_data = [list(df.columns)] + df.values.tolist()

        # Validate column widths
        if col_widths is not None:
            if len(col_widths) != len(df.columns):
                raise ValueError(
                    "Length of col_widths must match number of columns."
                )
            col_widths_seq = list(col_widths)
        else:
            # Distribute width evenly across the page width minus margins
            usable_width = self.page_size[0] - 2 * self.margin
            col_widths_seq = [usable_width / len(df.columns)] * len(df.columns)

        # Default style if none provided
        if style is None:
            style = TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ]
            )

        table = Table(table_data, colWidths=col_widths_seq, hAlign="LEFT")
        table.setStyle(style)
        self._elements.append(table)
        self._elements.append(Spacer(1, 0.3 * cm))

    # --------------------------------------------------------------------- #
    # Chart handling
    # --------------------------------------------------------------------- #
    def add_chart(
        self,
        data: Union[pd.DataFrame, Sequence[Dict[str, Any]]],
        chart_type: str,
        title: str = "",
        x_label: str = "",
        y_label: str = "",
        size: Tuple[int, int] = (6, 4),
    ) -> None:
        """
        Render a chart from ``data`` and embed it into the PDF.

        Args:
            data: Data source; either a DataFrame or a sequence of dicts.
            chart_type: One of ``"bar"``, ``"line"``, or ``"pie"``.
            title: Chart title.
            x_label: Label for the X‑axis (ignored for pie charts).
            y_label: Label for the Y‑axis (ignored for pie charts).
            size: Figure size in inches (width, height).

        Raises:
            InvalidChartTypeError: If ``chart_type`` is not supported.
            ValueError: If required columns are missing for the selected chart.
        """
        chart_type = chart_type.lower()
        if chart_type not in {"bar", "line", "pie"}:
            raise InvalidChartTypeError(
                f"Unsupported chart type '{chart_type}'. Choose from bar, line, pie."
            )

        # Convert data to DataFrame
        try:
            if isinstance(data, pd.DataFrame):
                df = data.copy()
            else:
                df = pd.DataFrame(list(data))
        except Exception as exc:
            raise ValueError(f"Unable to parse chart data: {exc}") from exc

        if df.empty:
            raise ValueError("Chart data is empty.")

        # Basic validation: expect at least two columns for bar/line
        if chart_type in {"bar", "line"} and df.shape[1] < 2:
            raise ValueError(
                f"{chart_type.title()} chart requires at least two columns (category and values)."
            )
        if chart_type == "pie" and df.shape[1] < 2:
            raise ValueError("Pie chart requires at least two columns (labels and sizes).")

        # Plot generation inside a safe temporary buffer
        fig, ax = plt.subplots(figsize=size)
        try:
            if chart_type == "bar":
                categories = df.iloc[:, 0].astype(str)
                values = df.iloc[:, 1]
                ax.bar(categories, values, color=plt.cm.tab20.colors)
                ax.set_xlabel(x_label or df.columns[0])
                ax.set_ylabel(y_label or df.columns[1])
            elif chart_type == "line":
                categories = df.iloc[:, 0]
                values = df.iloc[:, 1]
                ax.plot(categories, values, marker="o")
                ax.set_xlabel(x_label or df.columns[0])
                ax.set_ylabel(y_label or df.columns[1])
            elif chart_type == "pie":
                labels = df.iloc[:, 0].astype(str)
                sizes = df.iloc[:, 1]
                ax.pie(sizes, labels=labels, autopct="%1.1f%%", startangle=90)
                ax.axis("equal")
            if title:
                ax.set_title(title)
            plt.tight_layout()
            img_buffer = io.BytesIO()
            plt.savefig(img_buffer, format="png", dpi=150)
            img_buffer.seek(0)
        finally:
            plt.close(fig)

        # Embed the image
        img = Image(img_buffer, width=img_buffer.getbuffer().nbytes)  # placeholder width
        # Scale image to fit page width while preserving aspect ratio
        max_width = self.page_size[0] - 2 * self.margin
        img._restrictSize(max_width, max_width)  # type: ignore[attr-defined]
        self._elements.append(img)
        self._elements.append(Spacer(1, 0.3 * cm))

    # --------------------------------------------------------------------- #
    # PDF generation
    # --------------------------------------------------------------------- #
    def _header_footer_callback(self, canvas_obj, doc) -> None:
        """Internal callback to draw header/footer on each page."""
        canvas_obj.saveState()
        if self.header_text:
            header_para = Paragraph(self.header_text, self._styles["header"])
            w, h = header_para.wrap(doc.width, doc.topMargin)
            header_para.drawOn(canvas_obj, doc.leftMargin, doc.height + doc.topMargin - h + 0.5 * cm)
        if self.footer_text:
            footer_para = Paragraph(self.footer_text, self._styles["footer"])
            w, h = footer_para.wrap(doc.width, doc.bottomMargin)
            footer_para.drawOn(canvas_obj, doc.leftMargin, h - 0.5 * cm)
        canvas_obj.restoreState()

    def generate(self, output_path: str) -> None:
        """
        Build the PDF file and write it to ``output_path``.

        Args:
            output_path: Destination file path for the generated PDF.

        Raises:
            ReportGenerationError: For any I/O or rendering errors.
            ValueError: If ``output_path`` is not a writable location.
        """
        if not output_path.lower().endswith(".pdf"):
            raise ValueError("Output file must have a .pdf extension.")

        # Ensure directory exists and is writable
        output_dir = os.path.dirname(os.path.abspath(output_path)) or "."
        if not os.access(output_dir, os.W_OK):
            raise ValueError(f"Cannot write to directory: {output_dir}")

        doc = SimpleDocTemplate(
            output_path,
            pagesize=self.page_size,
            rightMargin=self.margin,
            leftMargin=self.margin,
            topMargin=self.margin,
            bottomMargin=self.margin,
        )

        # Insert title as first element
        title_para = Paragraph(self.title, self._styles["title"])
        self._elements.insert(0, title_para)
        self._elements.insert(1, Spacer(1, 0.5 * cm))

        try:
            doc.build(self._elements, onFirstPage=self._header_footer_callback, onLaterPages=self._header_footer_callback)
        except Exception as exc:
            raise ReportGenerationError(f"Failed to generate PDF: {exc}") from exc