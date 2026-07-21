"""
pdf_report.py

A simple, secure PDF report generator using ReportLab and Matplotlib.

Features
--------
* Header & footer rendering (auto‑page numbering)
* Table generation from a list of dicts / list of lists
* Chart insertion – bar, line, and pie charts
* Multi‑page support (tables split across pages automatically)
* Type hints, comprehensive docstrings and error handling
"""

from __future__ import annotations

import io
import pathlib
from dataclasses import dataclass, field
from typing import Any, Iterable, List, Mapping, Sequence, Tuple, Union

import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape, portrait
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm, inch
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    Image,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

# --------------------------------------------------------------------------- #
# Helper Types
# --------------------------------------------------------------------------- #

Cell = Union[str, int, float, None]
Row = Sequence[Cell]
TableData = Sequence[Row]
ChartType = Literal["bar", "line", "pie"]
# --------------------------------------------------------------------------- #

def _sanitize_text(text: str) -> str:
    """
    Very basic sanitisation to avoid injection attacks in PDF metadata/content.
    Strips control characters and limits length.
    """
    if not isinstance(text, str):
        raise TypeError("Text must be a string")
    cleaned = "".join(ch for ch in text if ch.isprintable())
    return cleaned[:5000]  # arbitrary safety limit


def _fig_to_image(fig: Figure) -> Image:
    """
    Convert a Matplotlib figure to a ReportLab Image object using an in‑memory buffer.
    """
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=150)
    buf.seek(0)
    img = Image(buf)
    return img


# --------------------------------------------------------------------------- #
# Core PDF Report Generator
# --------------------------------------------------------------------------- #

@dataclass
class PDFReportGenerator:
    """
    PDF report generator that supports headers, footers, tables, and charts.

    Parameters
    ----------
    filename : str | pathlib.Path
        Output PDF file path.
    title : str, optional
        Title displayed in header (defaults to empty).
    page_size : tuple, optional
        Page size (default A4). Use reportlab.lib.pagesizes constants.
    orientation : str, optional
        ``"portrait"`` or ``"landscape"``.
    margin : float, optional
        Margin in centimeters (applied on all sides).
    """

    filename: Union[str, pathlib.Path]
    title: str = ""
    page_size: Tuple[float, float] = A4
    orientation: str = "portrait"
    margin: float = 2.0

    # Internal fields (not part of public API)
    _doc: BaseDocTemplate = field(init=False, repr=False)
    _story: List[Any] = field(default_factory=list, init=False, repr=False)
    _header_style: ParagraphStyle = field(init=False, repr=False)
    _footer_style: ParagraphStyle = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.title = _sanitize_text(self.title)
        self.filename = pathlib.Path(self.filename)

        # Apply orientation
        if self.orientation == "landscape":
            self.page_size = landscape(self.page_size)
        elif self.orientation != "portrait":
            raise ValueError("orientation must be 'portrait' or 'landscape'")

        # Prepare document template
        self._doc = BaseDocTemplate(
            str(self.filename),
            pagesize=self.page_size,
            leftMargin=self.margin * cm,
            rightMargin=self.margin * cm,
            topMargin=self.margin * cm,
            bottomMargin=self.margin * cm,
        )
        frame = Frame(
            self._doc.leftMargin,
            self._doc.bottomMargin,
            self._doc.width,
            self._doc.height,
            id="normal",
        )
        template = PageTemplate(id="default", frames=[frame], onPage=self._add_page_decor)
        self._doc.addPageTemplates([template])

        # Define styles
        self._header_style = ParagraphStyle(
            name="Header",
            fontSize=12,
            leading=14,
            alignment=1,  # centered
            spaceAfter=12,
            textColor=colors.darkblue,
        )
        self._footer_style = ParagraphStyle(
            name="Footer",
            fontSize=9,
            leading=11,
            alignment=1,
            textColor=colors.grey,
        )

    # ----------------------------------------------------------------------- #
    # Page Decorators (header & footer)
    # ----------------------------------------------------------------------- #

    def _add_page_decor(self, canvas, doc) -> None:
        """
        Draw header and footer on each page.
        """
        canvas.saveState()
        # Header
        if self.title:
            header = Paragraph(_sanitize_text(self.title), self._header_style)
            w, h = header.wrap(doc.width, doc.topMargin)
            header.drawOn(canvas, doc.leftMargin, doc.height + doc.topMargin - h + 0.5 * cm)

        # Footer – page number
        footer_text = f"Page {canvas.getPageNumber()}"
        footer = Paragraph(_sanitize_text(footer_text), self._footer_style)
        w, h = footer.wrap(doc.width, doc.bottomMargin)
        footer.drawOn(canvas, doc.leftMargin, h - 0.5 * cm)
        canvas.restoreState()

    # ----------------------------------------------------------------------- #
    # Public API – Adding Content
    # ----------------------------------------------------------------------- #

    def add_paragraph(self, text: str, style: ParagraphStyle | None = None) -> None:
        """
        Add a paragraph to the report.

        Parameters
        ----------
        text : str
            Paragraph text (HTML‑like markup allowed).
        style : ParagraphStyle, optional
            Custom style; if omitted, default style is used.
        """
        if not isinstance(text, str):
            raise TypeError("Paragraph text must be a string")
        paragraph = Paragraph(_sanitize_text(text), style or self._default_paragraph_style())
        self._story.append(paragraph)
        self._story.append(Spacer(1, 0.2 * cm))

    def _default_paragraph_style(self) -> ParagraphStyle:
        return ParagraphStyle(name="Body", fontSize=10, leading=12)

    def add_table(
        self,
        data: TableData,
        col_widths: Sequence[float] | None = None,
        repeat_header: bool = True,
        style: TableStyle | None = None,
    ) -> None:
        """
        Add a table to the report. Handles automatic splitting across pages.

        Parameters
        ----------
        data : TableData
            Table data as list of rows (first row may be header).
        col_widths : Sequence[float] | None
            Column widths in centimeters. If omitted, equal distribution is used.
        repeat_header : bool
            If True, first row is repeated on each split table page.
        style : TableStyle | None
            Custom TableStyle; otherwise a default is applied.
        """
        if not data or not isinstance(data, (list, tuple)):
            raise ValueError("Table data must be a non‑empty list/tuple")

        # Convert column widths to points
        if col_widths:
            col_widths_pt = [w * cm for w in col_widths]
        else:
            col_widths_pt = None

        tbl_style = style or self._default_table_style()
        tbl = Table(data, colWidths=col_widths_pt, repeatRows=1 if repeat_header else 0, hAlign="LEFT")
        tbl.setStyle(tbl_style)
        self._story.append(tbl)
        self._story.append(Spacer(1, 0.3 * cm))

    def _default_table_style(self) -> TableStyle:
        return TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
            ]
        )

    def add_chart(
        self,
        chart_type: ChartType,
        data: Mapping[str, Sequence[float]] | Sequence[float],
        labels: Sequence[str] | None = None,
        title: str = "",
        size: Tuple[float, float] = (15, 10),
    ) -> None:
        """
        Create a chart with Matplotlib and insert it into the PDF.

        Parameters
        ----------
        chart_type : {"bar", "line", "pie"}
            Type of chart to render.
        data : Mapping or Sequence
            If ``chart_type`` is "pie", ``data