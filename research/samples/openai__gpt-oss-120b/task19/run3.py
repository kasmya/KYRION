"""
pdf_report_generator.py

A lightweight PDF report generator supporting page headers/footers,
data tables, and chart insertion (bar, line, pie). Designed for
multi‑page reports using only the Python standard library and the
widely‑used `reportlab` and `matplotlib` packages.

Features
--------
- Configurable page size (default: LETTER)
- Automatic pagination
- Header/footer rendering on every page
- Table rendering with optional column widths
- Chart rendering from data dictionaries or sequences
- Comprehensive type hints, docstrings, and error handling
"""

from __future__ import annotations

import io
import os
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Table,
    TableStyle,
)
import matplotlib.pyplot as plt


class PDFReportGenerator:
    """
    Core class for building PDF reports.

    Parameters
    ----------
    filename : str
        Destination file path for the generated PDF.
    pagesize : Tuple[float, float], optional
        Page size in points (default is LETTER). Use `reportlab.lib.pagesizes.A4`
        for A4 size.
    """

    def __init__(self, filename: str, pagesize: Tuple[float, float] = LETTER) -> None:
        self._validate_filepath(filename)
        self.filename = filename
        self.pagesize = pagesize
        self._elements: List[Any] = []
        self._header: Optional[Tuple[str, int]] = None
        self._footer: Optional[Tuple[str, int]] = None
        self._styles = getSampleStyleSheet()
        self._default_style = self._styles["Normal"]

    # --------------------------------------------------------------------- #
    # Public API
    # --------------------------------------------------------------------- #
    def set_header(self, text: str, font_size: int = 12) -> None:
        """
        Define a header that will appear on every page.

        Parameters
        ----------
        text : str
            Header text.
        font_size : int, optional
            Font size in points (default is 12).
        """
        self._header = (text, font_size)

    def set_footer(self, text: str, font_size: int = 10) -> None:
        """
        Define a footer that will appear on every page.

        Parameters
        ----------
        text : str
            Footer text.
        font_size : int, optional
            Font size in points (default is 10).
        """
        self._footer = (text, font_size)

    def add_paragraph(self, text: str, style: Optional[ParagraphStyle] = None) -> None:
        """
        Append a paragraph to the report.

        Parameters
        ----------
        text : str
            Paragraph content (HTML‑like markup supported).
        style : ParagraphStyle, optional
            Custom paragraph style; defaults to the library's normal style.
        """
        para_style = style or self._default_style
        self._elements.append(Paragraph(text, para_style))

    def add_table(
        self,
        data: List[List[Any]],
        col_widths: Optional[Sequence[float]] = None,
        style: Optional[TableStyle] = None,
    ) -> None:
        """
        Add a table to the report.

        Parameters
        ----------
        data : List[List[Any]]
            2‑D list representing table rows.
        col_widths : Sequence[float], optional
            Widths for each column in points. If omitted, columns are sized
            automatically.
        style : TableStyle, optional
            Custom ReportLab TableStyle; a sensible default is applied if omitted.
        """
        if not data or not all(isinstance(row, list) for row in data):
            raise ValueError("`data` must be a non‑empty 2‑D list.")
        tbl = Table(data, colWidths=col_widths)
        tbl.setStyle(style or self._default_table_style())
        self._elements.append(tbl)

    def add_chart(
        self,
        chart_type: str,
        data: Union[Dict[str, float], Sequence[float]],
        title: str = "",
        xlabel: str = "",
        ylabel: str = "",
        width: int = 400,
        height: int = 300,
    ) -> None:
        """
        Render a chart and embed it as an image.

        Parameters
        ----------
        chart_type : str
            One of ``'bar'``, ``'line'`` or ``'pie'``.
        data : dict or sequence
            For ``'pie'`` a mapping of labels to values is required.
            For ``'bar'`` and ``'line'`` a sequence of numeric values is accepted.
        title : str, optional
            Chart title.
        xlabel : str, optional
            X‑axis label (ignored for pie charts).
        ylabel : str, optional
            Y‑axis label (ignored for pie charts).
        width : int, optional
            Width of the chart image in pixels (default 400).
        height : int, optional
            Height of the chart image in pixels (default 300).
        """
        chart_type = chart_type.lower()
        fig = plt.figure(figsize=(width / 100, height / 100))
        ax = fig.add_subplot(111)

        if chart_type == "pie":
            if not isinstance(data, dict):
                raise ValueError("Pie charts require a dict of label->value.")
            labels, sizes = zip(*data.items())
            ax.pie(sizes, labels=labels, autopct="%1.1f%%")
        elif chart_type in {"bar", "line"}:
            if not isinstance(data, (list, tuple)):
                raise ValueError(f"{chart_type.title()} chart requires a sequence of numbers.")
            x = list(range(1, len(data) + 1))
            if chart_type == "bar":
                ax.bar(x, data)
            else:
                ax.plot(x, data, marker="o")
            ax.set_xlabel(xlabel)
            ax.set_ylabel(ylabel)
        else:
            plt.close(fig)
            raise ValueError("Unsupported chart_type. Choose 'bar', 'line', or 'pie'.")

        ax.set_title(title)
        plt.tight_layout()

        img_buffer = io.BytesIO()
        fig.savefig(img_buffer, format="png")
        plt.close(fig)
        img_buffer.seek(0)

        img = Image(img_buffer, width=width * 0.75, height=height * 0.75)  # convert px to points
        self._elements.append(img)

    def add_page_break(self) -> None:
        """Insert a manual page break."""
        self._elements.append(PageBreak())

    def build(self) -> None:
        """
        Generate the PDF file at the path supplied during initialization.
        """
        doc = SimpleDocTemplate(
            self.filename,
            pagesize=self.pagesize,
            rightMargin=inch,
            leftMargin=inch,
            topMargin=inch,
            bottomMargin=inch,
        )
        doc.build(self._elements, onFirstPage=self._draw_header_footer, onLaterPages=self._draw_header_footer)

    # --------------------------------------------------------------------- #
    # Private helpers
    # --------------------------------------------------------------------- #
    @staticmethod
    def _validate_filepath(path: str) -> None:
        """
        Ensure the output path is safe and writable.

        Raises
        ------
        ValueError
            If the directory does not exist or is not writable.
        """
        directory = os.path.abspath(os.path.dirname(path) or ".")
        if not os.path.isdir(directory):
            raise ValueError(f"The directory '{directory}' does not exist.")
        if not os.access(directory, os.W_OK):
            raise ValueError(f"The directory '{directory}' is not writable.")

    def _draw_header_footer(self, canvas, doc) -> None:
        """
        Internal callback for ReportLab to render headers and footers.
        """
        canvas.saveState()
        width, height = self.pagesize

        if self._header:
            text, size = self._header
            canvas.setFont("Helvetica-Bold", size)
            canvas.drawString(inch, height - 0.75 * inch, text)

        if self._footer:
            text, size = self._footer
            canvas.setFont("Helvetica-Oblique", size)
            canvas.drawString(inch, 0.5 * inch, text)

        canvas.restoreState()

    @staticmethod
    def _default_table_style() -> TableStyle:
        """
        Returns a default TableStyle for consistent appearance.
        """
        return TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ]
        )