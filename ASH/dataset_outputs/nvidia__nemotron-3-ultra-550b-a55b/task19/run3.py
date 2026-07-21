"""
PDF Report Generator Module

This module provides a comprehensive PDF report generation system with support for:
- Customizable page headers and footers
- Formatted data tables with automatic pagination
- Chart insertion (bar, line, pie) using matplotlib
- Multi-page document support
- Professional styling and layout management

Dependencies:
- fpdf2 (pip install fpdf2)
- matplotlib (pip install matplotlib)
- numpy (pip install numpy)

Usage Example:
    report = PDFReport(title="Monthly Sales Report", author="Analytics Team")
    report.add_page()
    report.add_header("Sales Summary", level=1)
    report.add_table(headers=["Product", "Units", "Revenue"], data=sales_data)
    report.add_chart("bar", data=monthly_sales, labels=months, title="Monthly Sales")
    report.output("report.pdf")
"""

import io
import os
import tempfile
import warnings
from typing import List, Dict, Any, Optional, Union, Sequence, Tuple
from pathlib import Path

try:
    from fpdf import FPDF
    from fpdf.enums import XPos, YPos
except ImportError:
    raise ImportError("fpdf2 is required. Install with: pip install fpdf2")

try:
    import matplotlib
    matplotlib.use('Agg')  # Non-interactive backend
    import matplotlib.pyplot as plt
    import numpy as np
except ImportError:
    raise ImportError("matplotlib and numpy are required. Install with: pip install matplotlib numpy")


class PDFReport(FPDF):
    """
    Extended FPDF class for professional report generation with headers, footers,
    tables, charts, and multi-page support.
    """

    def __init__(
        self,
        orientation: str = "P",
        unit: str = "mm",
        format: str = "A4",
        title: str = "Report",
        author: str = "Author",
        subject: str = "",
        keywords: str = "",
        header_text: str = "",
        footer_text: str = "",
        logo_path: Optional[str] = None,
        margin: float = 20,
        font_family: str = "Helvetica",
        font_size: int = 10,
        line_height: float = 5,
    ) -> None:
        """
        Initialize the PDF report generator.

        Args:
            orientation: Page orientation ('P' for portrait, 'L' for landscape)
            unit: Measurement unit ('mm', 'cm', 'in')
            format: Page format ('A4', 'Letter', etc.) or tuple (width, height)
            title: Document title metadata
            author: Document author metadata
            subject: Document subject metadata
            keywords: Document keywords metadata
            header_text: Default header text (left side)
            footer_text: Default footer text (left side)
            logo_path: Path to logo image for header
            margin: Page margin in units
            font_family: Default font family
            font_size: Default font size
            line_height: Default line height for text
        """
        super().__init__(orientation=orientation, unit=unit, format=format)
        self.set_auto_page_break(auto=True, margin=margin)
        self.set_margins(margin, margin, margin)
        
        # Metadata
        self.set_title(title)
        self.set_author(author)
        self.set_subject(subject)
        self.set_keywords(keywords)
        
        # Custom properties
        self._header_text = header_text
        self._footer_text = footer_text
        self._logo_path = logo_path
        self._font_family = font_family
        self._font_size = font_size
        self._line_height = line_height
        self._chart_counter = 0
        self._temp_files: List[str] = []
        
        # Style configurations
        self._header_font_size = 14
        self._subheader_font_size = 12
        self._table_header_font_size = 9
        self._table_data_font_size = 8
        self._footer_font_size = 8
        
        # Colors (R, G, B)
        self._primary_color = (0, 51, 102)
        self._secondary_color = (100, 100, 100)
        self._table_header_bg = (0, 51, 102)
        self._table_header_text = (255, 255, 255)
        self._table_row_alt = (240, 240, 240)
        self._table_border = (200, 200, 200)

    def header(self) -> None:
        """Draw page header with logo, title, and line separator."""
        try:
            # Logo
            if self._logo_path and os.path.exists(self._logo_path):
                self.image(self._logo_path, x=self.l_margin, y=self.t_margin, h=12)
                x_start = self.l_margin + 30
            else:
                x_start = self.l_margin
            
            # Header text
            self.set_font(self._font_family, 'B', self._header_font_size)
            self.set_text_color(*self._primary_color)
            self.set_xy(x_start, self.t_margin + 2)
            self.cell(0, 8, self._header_text or self.title, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            
            # Separator line
            self.set_draw_color(*self._primary_color)
            self.set_line_width(0.5)
            self.line(self.l_margin, self.get_y() + 2, self.w - self.r_margin, self.get_y() + 2)
            self.ln(6)
        except Exception as e:
            warnings.warn(f"Header rendering failed: {e}", RuntimeWarning)

    def footer(self) -> None:
        """Draw page footer with page number, date, and custom text."""
        try:
            self.set_y(-20)
            self.set_draw_color(*self._secondary_color)
            self.set_line_width(0.3)
            self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
            self.ln(2)
            
            self.set_font(self._font_family, 'I', self._footer_font_size)
            self.set_text_color(*self._secondary_color)
            
            # Left: Custom footer text
            if self._footer_text:
                self.cell(0, 5, self._footer_text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            
            # Center: Page number
            page_text = f"Page {self.page_no()}/{{nb}}"
            self.cell(0, 5, page_text, align='C', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            
            # Right: Date
            from datetime import datetime
            date_text = datetime.now().strftime("%Y-%m-%d %H:%M")
            self.cell(0, 5, date_text, align='R')
        except Exception as e:
            warnings.warn(f"Footer rendering failed: {e}", RuntimeWarning)

    def add_header(self, text: str, level: int = 1) -> None:
        """
        Add a section header to the document.

        Args:
            text: Header text
            level: Header level (1=main, 2=sub, 3=minor)
        """
        try:
            if level == 1:
                self.set_font(self._font_family, 'B', self._header_font_size)
                self.set_text_color(*self._primary_color)
                self.ln(4)
                self.cell(0, self._line_height * 1.5, text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                self.set_draw_color(*self._primary_color)
                self.set_line_width(0.4)
                self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
                self.ln(4)
            elif level == 2:
                self.set_font(self._font_family, 'B', self._subheader_font_size)
                self.set_text_color(*self._primary_color)
                self.ln(3)
                self.cell(0, self._line_height * 1.3, text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                self.ln(2)
            else:
                self.set_font(self._font_family, 'BI', self._font_size)
                self.set_text_color(*self._secondary_color)
                self.ln(2)
                self.cell(0, self._line_height, text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                self.ln(1)
        except Exception as e:
            raise RuntimeError(f"Failed to add header: {e}") from e

    def add_paragraph(self, text: str, bold: bool = False, italic: bool = False, 
                     font_size: Optional[int] = None, align: str = 'L') -> None:
        """
        Add a paragraph of text with word wrapping.

        Args:
            text: Paragraph text
            bold: Whether to use bold font
            italic: Whether to use italic font
            font_size: Custom font size (default: self._font_size)
            align: Text alignment ('L', 'C', 'R', 'J')
        """
        try:
            style = ''
            if bold: style += 'B'
            if italic: style += 'I'
            size = font_size or self._font_size
            self.set_font(self._font_family, style, size)
            self.set_text_color(*self._secondary_color)
            self.multi_cell(0, self._line_height, text, align=align)
            self.ln(2)
        except Exception as e:
            raise RuntimeError(f"Failed to add paragraph: {e}") from e

    def add_table(
        self,
        headers: List[str],
        data: List[List[Any]],
        col_widths: Optional[List[float]] = None,
        col_aligns: Optional[List[str]] = None,
        header_style: bool = True,
        alternate_rows: bool = True,
        border: bool = True,
    ) -> None:
        """
        Add a formatted data table with automatic pagination.

        Args:
            headers: List of column headers
            data: List of rows (each row is a list of cell values)
            col_widths: List of column widths (auto-calculated if None)
            col_aligns: List of alignments per column ('L', 'C', 'R')
            header_style: Whether to apply special header styling
            alternate_rows: Whether to alternate row background colors
            border: Whether to draw cell borders
        """
        if not headers or not data:
            return

        try:
            # Validate inputs
            num_cols = len(headers)
            for i, row in enumerate(data):
                if len(row) != num_cols:
                    raise ValueError(f"Row {i} has {len(row)} columns, expected {num_cols}")

            # Calculate column widths if not provided
            if col_widths is None:
                col_widths = self._calculate_col_widths(headers, data, num_cols)
            elif len(col_widths) != num_cols:
                raise ValueError(f"col_widths length ({len(col_widths)}) != num_cols ({num_cols})")

            # Default alignments
            if col_aligns is None:
                col_aligns = ['L'] * num_cols
            elif len(col_aligns) != num_cols:
                raise ValueError(f"col_aligns length ({len(col_aligns)}) != num_cols ({num_cols})")

            # Table dimensions
            table_width = sum(col_widths)
            available_width = self.w - self.l_margin - self.r_margin
            if table_width > available_width:
                # Scale down proportionally
                scale = available_width / table_width
                col_widths = [w * scale for w in col_widths]

            row_height = self._line_height * 1.4

            # Draw header
            if header_style:
                self.set_font(self._font_family, 'B', self._table_header_font_size)
                self.set_fill_color(*self._table_header_bg)
                self.set_text_color(*self._table_header_text)
                self.set_draw_color(*self._table_border)
            else:
                self.set_font(self._font_family, 'B', self._table_data_font_size)
                self.set_fill_color(255, 255, 255)
                self.set_text_color(*self._secondary_color)
                self.set_draw_color(*self._table_border)

            x_start = self.l_margin
            for i, (header, width, align) in enumerate(zip(headers, col_widths, col_aligns)):
                self.set_xy(x_start, self.get_y())
                self.cell(width, row_height, str(header), border=1 if border else 0, 
                         align=align, fill=header_style, new_x=XPos.RIGHT, new_y=YPos.TOP)
                x_start += width
            self.ln(row_height)

            # Draw data rows
            self.set_font(self._font_family, '', self._table_data_font_size)
            self.set_text_color(*self._secondary_color)
            
            for row_idx, row in enumerate(data):
                # Check if we need a new page
                if self.get_y() + row_height > self.h - self.b_margin:
                    self.add_page()
                    # Redraw header on new page
                    self.add_table(headers, [], col_widths, col_aligns, header_style, False, border)
                
                # Alternate row colors
                if alternate_rows and row_idx % 2 == 1:
                    self.set_fill_color(*self._table_row_alt)
                    fill = True
                else:
                    self.set_fill_color(255, 255, 255)
                    fill = False
                
                self.set_draw_color(*self._table_border)
                x_start = self.l_margin
                max_h = row_height
                
                # Calculate required height for multi-line cells
                cell_heights = []
                for cell_val, width, align in zip(row, col_widths, col_aligns):
                    # Estimate lines needed
                    text = str(cell_val)
                    char_width = self.get_string_width('x')
                    chars_per_line = max(1, int(width / char_width))
                    lines = max(1, (len(text) + chars_per_line - 1) // chars_per_line)
                    cell_heights.append(lines * self._line_height)
                
                max_h = max(max_h, max(cell_heights)) if cell_heights else row_height
                
                # Draw cells
                for cell_val, width, align in zip(row, col_widths, col_aligns):
                    self.set_xy(x_start, self.get_y())
                    self.multi_cell(width, self._line_height, str(cell_val), 
                                   border=1 if border else 0, align=align, fill=fill,
                                   new_x=XPos.RIGHT, new_y=YPos.TOP)
                    x_start += width
                self.ln(max_h)
            
            self.ln(4)
        except Exception as e:
            raise RuntimeError(f"Failed to add table: {e}") from e

    def _calculate_col_widths(
        self, 
        headers: List[str], 
        data: List[List[Any]], 
        num_cols: int
    ) -> List[float]:
        """Calculate optimal column widths based on content."""
        available_width = self.w - self.l_margin - self.r_margin
        min_width = available_width / num_cols
        col_widths = [min_width] * num_cols
        
        # Measure header widths
        self.set_font(self._font_family, 'B', self._table_header_font_size)
        for i, header in enumerate(headers):
            w = self.get_string_width(str(header)) + 4
            if w > col_widths[i]:
                col_widths[i] = min(w, available_width * 0.4)
        
        # Measure data widths (sample first 50 rows)
        self.set_font(self._font_family, '', self._table_data_font_size)
        for row in data[:50]:
            for i, cell in enumerate(row):
                w = self.get_string_width(str(cell)) + 4
                if