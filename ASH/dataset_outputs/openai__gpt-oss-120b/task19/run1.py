"""
pdf_report_generator.py

A lightweight PDF report generator using ReportLab and Matplotlib.

Features:
- Automatic page headers and footers (including page numbers)
- Insertion of data tables with optional styling
- Embedding of bar, line, and pie charts generated from data
- Multi‑page support with automatic page breaks

Only the Python standard library and the widely‑used PyPI packages
`reportlab` and `matplotlib` are required.

Example
-------
    from pdf_report_generator import PDFReport, ReportError

    report = PDFReport(
        title="Sales Summary",
        output_path="sales_report.pdf",
        author="Acme Corp",
    )
    report.add_header("Acme Corp – Confidential")
    report.add_footer("Generated on 2026-07-20")
    report.add_table(
        data=[["Region", "Q1", "Q2", "Q3", "Q4"], ["North", 120, 130, 115, 140]],
        column_widths=[100, 50, 50, 50, 50],
    )
    report.add_chart(
        chart_type="bar",
        data={"North": 120, "South": 95, "East": 110, "West": 130},
        title="Quarterly Sales",
    )
    report.build()
"""

from __future__ import annotations

import io
import pathlib
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple, Union

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape, portrait
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, inch
from reportlab.platypus import (
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
import matplotlib.pyplot as plt

# ---------------------------------------------------------------------------

class ReportError(Exception):
    """Base exception for all report generation errors."""


# ---------------------------------------------------------------------------

class PDFReport:
    """
    PDF report builder.

    Parameters
    ----------
    title : str
        Title of the report; appears in the document metadata.
    output_path : str | pathlib.Path
        Destination file for the generated PDF.
    author : str, optional
        Author name for PDF metadata.
    page_size : tuple, optional
        Page size in points (width, height). Defaults to A4 portrait.
    margin : float, optional
        Page margin in centimeters. Defaults to 2 cm.
    """

    def __init__(
        self,
        *,
        title: str,
        output_path: Union[str, pathlib.Path],
        author: str = "",
        page_size: Tuple[float, float] = A4,
        margin: float = 2.0,
    ) -> None:
        self.title = title
        self.author = author
        self.page_size = page_size
        self.margin = margin * cm

        try:
            self.output_path = pathlib.Path(output_path).expanduser().resolve(strict=False)
            if self.output_path.is_dir():
                raise ReportError(f"Output path '{self.output_path}' is a directory.")
        except Exception as exc:
            raise ReportError(f"Invalid output path: {exc}") from exc

        self._elements: List[Any] = []
        self._header: str = ""
        self._footer: str = ""

        # Styles
        self._styles = getSampleStyleSheet()
        self._styles.add(
            ParagraphStyle(
                name="HeaderFooter",
                fontSize=9,
                alignment=1,  # center
                textColor=colors.grey,
            )
        )
        self._styles.add(
            ParagraphStyle(
                name="Title",
                fontSize=18,
                leading=22,
                alignment=1,
                spaceAfter=12,
            )
        )

    # -----------------------------------------------------------------------

    def add_header(self, text: str) -> None:
        """
        Set the header text displayed on every page.

        Parameters
        ----------
        text : str
            Header content.
        """
        if not isinstance(text, str):
            raise ReportError("Header text must be a string.")
        self._header = text

    def add_footer(self, text: str) -> None:
        """
        Set the footer text displayed on every page (excluding the page number).

        Parameters
        ----------
        text : str
            Footer content.
        """
        if not isinstance(text, str):
            raise ReportError("Footer text must be a string.")
        self._footer = text

    # -----------------------------------------------------------------------

    def add_table(
        self,
        data: Sequence[Sequence[Any]],
        column_widths: Sequence[float] | None = None,
        style: TableStyle | None = None,
        repeat_rows: int = 1,
    ) -> None:
        """
        Append a table to the report.

        Parameters
        ----------
        data : sequence of sequences
            Table data; first row is treated as a header.
        column_widths : sequence of float, optional
            Width of each column in centimeters. If omitted, widths are auto‑scaled.
        style : reportlab.platypus.TableStyle, optional
            Custom table style. If omitted, a default style is applied.
        repeat_rows : int, default 1
            Number of top rows to repeat on each new page.
        """
        if not data or not isinstance(data, (list, tuple)):
            raise ReportError("Table data must be a non‑empty list or tuple.")
        if column_widths:
            if len(column_widths) != len(data[0]):
                raise ReportError("Column widths length must match number of columns.")
            col_widths_pt = [w * cm for w in column_widths]
        else:
            col_widths_pt = None

        table_style = style or TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
            ]
        )

        tbl = Table(data, colWidths=col_widths_pt, repeatRows=repeat_rows, hAlign="LEFT")
        tbl.setStyle(table_style)

        self._elements.append(tbl)
        self._elements.append(Spacer(1, 0.2 * inch))

    # -----------------------------------------------------------------------

    def add_chart(
        self,
        chart_type: str,
        data: Mapping[str, float] | Sequence[float],
        title: str = "",
        xlabel: str = "",
        ylabel: str = "",
        size: Tuple[float, float] = (6, 4),
    ) -> None:
        """
        Generate a chart with Matplotlib and embed it in the PDF.

        Parameters
        ----------
        chart_type : {'bar', 'line', 'pie'}
            Type of chart to render.
        data : mapping or sequence
            For ``bar`` and ``line`` charts, a mapping of labels to values.
            For ``pie`` charts, a sequence of numeric values.
        title : str, optional
            Chart title.
        xlabel : str, optional
            X‑axis label (ignored for pie charts).
        ylabel : str, optional
            Y‑axis label (ignored for pie charts).
        size : tuple of float, optional
            Figure size in inches (width, height). Default is (6, 4).
        """
        if chart_type not in {"bar", "line", "pie"}:
            raise ReportError(f"Unsupported chart type: {chart_type}")

        fig, ax = plt.subplots(figsize=size)
        try:
            if chart_type == "pie":
                if not isinstance(data, (list, tuple)):
                    raise ReportError("Pie chart data must be a sequence of numbers.")
                ax.pie(data, autopct="%1.1f%%", startangle=90)
                ax.axis("equal")
            else:
                if not isinstance(data, Mapping):
                    raise ReportError(f"{chart_type.title()} chart data must be a mapping.")
                labels = list(data.keys())
                values = list(data.values())
                indices = range(len(labels))
                if chart_type == "bar":
                    ax.bar(indices, values, tick_label=labels)
                elif chart_type == "line":
                    ax.plot(indices, values, marker="o")
                    ax.set_xticks(indices)
                    ax.set_xticklabels(labels)
                ax.set_xlabel(xlabel)
                ax.set_ylabel(ylabel)

            if title:
                ax.set_title(title)

            buf = io.BytesIO()
            plt.tight_layout()
            fig.savefig(buf, format="png")
            buf.seek(0)
            img = Image(buf, width=size[0] * inch, height=size[1] * inch)
            self._elements.append(img)
            self._elements.append(Spacer(1, 0.2 * inch))
        finally:
            plt.close(fig)

    # -----------------------------------------------------------------------

    def build(self) -> None:
        """
        Assemble the document and write the PDF file.

        Raises
        ------
        ReportError
            If the PDF cannot be generated or written.
        """
        try:
            doc = SimpleDocTemplate(
                filename=str(self.output_path),
                pagesize=self.page_size,
                leftMargin=self.margin,
                rightMargin=self.margin,
                topMargin=self.margin,
                bottomMargin=self.margin,
                title=self.title,
                author=self.author,
            )
            doc.build(
                self._elements,
                onFirstPage=self._make_page_decorator(page_number=False),
                onLaterPages=self._make_page_decorator(page_number=True),
            )
        except Exception as exc:
            raise ReportError(f"Failed to build PDF: {exc}") from exc

    # -----------------------------------------------------------------------

    def _make_page_decorator(self, page_number: bool):
        """
        Create a callable for ReportLab's onPage/onPageEnd hook.

        Parameters
        ----------
        page_number : bool
            Whether to include the page number in the footer.

        Returns
        -------
        Callable
            Function that draws header/footer on the canvas.
        """

        def decorator(canvas, doc):
            canvas.saveState()
            width, height = self.page_size

            # Header
            if self._header:
                canvas.setFont("Helvetica", 9)
                canvas.setFillColor(colors.grey)
                canvas.drawCentredString(width / 2.0, height - self.margin + 0.5 * cm, self._header)

            # Footer
            footer_y = self.margin - 0.75 * cm
            if self._footer:
                canvas.setFont("Helvetica", 9)
                canvas.setFillColor(colors.grey)
                canvas.drawCentredString(width / 2.0, footer_y, self._footer)

            # Page number
            if page_number:
                canvas.setFont("Helvetica", 9)
                canvas.setFillColor(colors.grey)
                page_str = f"Page {doc.page}"
                canvas.drawRightString(width - self.margin, footer_y, page_str)

            canvas.restoreState()

        return decorator