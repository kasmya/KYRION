"""
PDF Report Generator Module

This module provides a comprehensive PDF report generation system with support for:
- Page headers and footers
- Data tables with automatic pagination
- Chart insertion (bar, line, pie charts)
- Multi-page document support
- Professional formatting and styling

Dependencies:
    fpdf2 (pip install fpdf2)
    matplotlib (pip install matplotlib)
    numpy (pip install numpy)

Security Considerations:
    - Input validation for all user-provided data
    - Safe file path handling
    - Memory-efficient chart generation
    - No arbitrary code execution vectors
"""

import io
import os
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import matplotlib
matplotlib.use('Agg')  # Non-interactive backend for security
import matplotlib.pyplot as plt
import numpy as np
from fpdf import FPDF
from fpdf.enums import XPos, YPos
from fpdf.fonts import FontFace

# Type aliases for clarity
TableData = List[List[Union[str, int, float]]]
ChartData = Dict[str, Union[List[float], List[str], str]]
Color = Tuple[int, int, int]


class PDFReport(FPDF):
    """
    Extended FPDF class for professional report generation.
    
    Provides header/footer management, table rendering, chart insertion,
    and automatic page handling.
    """
    
    def __init__(
        self,
        orientation: str = 'P',
        unit: str = 'mm',
        format: str = 'A4',
        title: str = 'Report',
        author: str = 'System',
        header_text: str = '',
        footer_text: str = '',
        logo_path: Optional[str] = None
    ) -> None:
        """
        Initialize the PDF report generator.
        
        Args:
            orientation: Page orientation ('P' for portrait, 'L' for landscape)
            unit: Measurement unit ('mm', 'cm', 'in')
            format: Page format ('A4', 'A3', 'Letter', etc.)
            title: Document title for metadata
            author: Document author for metadata
            header_text: Text to display in header
            footer_text: Text to display in footer
            logo_path: Optional path to logo image for header
            
        Raises:
            FileNotFoundError: If logo_path is provided but file doesn't exist
            ValueError: If invalid orientation or format provided
        """
        super().__init__(orientation=orientation, unit=unit, format=format)
        
        # Validate inputs
        if orientation not in ('P', 'L'):
            raise ValueError("Orientation must be 'P' (portrait) or 'L' (landscape)")
        
        if logo_path and not Path(logo_path).is_file():
            raise FileNotFoundError(f"Logo file not found: {logo_path}")
        
        # Document metadata
        self.set_title(title)
        self.set_author(author)
        self.set_creator('PDF Report Generator')
        
        # Header/footer configuration
        self._header_text = header_text
        self._footer_text = footer_text
        self._logo_path = logo_path
        self._page_number_format = 'Page {nb}'
        
        # Default styling
        self._header_font = FontFace(family='Helvetica', style='B', size=10)
        self._footer_font = FontFace(family='Helvetica', size=8)
        self._table_header_font = FontFace(family='Helvetica', style='B', size=9)
        self._table_body_font = FontFace(family='Helvetica', size=8)
        self._header_color: Color = (41, 65, 122)
        self._alternate_row_color: Color = (240, 245, 250)
        
        # Margins
        self.set_auto_page_break(auto=True, margin=25)
        self.set_margins(left=15, top=20, right=15)
        
        # Register custom fonts if needed
        self._setup_fonts()
    
    def _setup_fonts(self) -> None:
        """Configure font substitutions for better Unicode support."""
        try:
            self.add_font('DejaVu', '', 'DejaVuSans.ttf', uni=True)
            self.add_font('DejaVu', 'B', 'DejaVuSans-Bold.ttf', uni=True)
        except RuntimeError:
            # Fallback to built-in fonts if DejaVu not available
            pass
    
    def header(self) -> None:
        """Render page header with logo, title, and optional line."""
        if self.page_no() == 1 and not self._header_text:
            return  # Skip header on first page if no header text
        
        y_start = self.get_y()
        
        # Logo if provided
        if self._logo_path:
            try:
                self.image(self._logo_path, x=15, y=8, w=25)
                y_start = max(y_start, 20)
            except Exception:
                pass  # Silently ignore logo errors
        
        # Header text
        if self._header_text:
            self.set_font(**self._header_font._asdict())
            self.set_text_color(*self._header_color)
            self.set_y(10)
            self.cell(
                w=0,
                h=8,
                text=self._header_text,
                align='C',
                new_x=XPos.LMARGIN,
                new_y=YPos.NEXT
            )
        
        # Separator line
        self.set_draw_color(*self._header_color)
        self.set_line_width(0.5)
        self.line(15, self.get_y() + 2, self.w - 15, self.get_y() + 2)
        self.ln(6)
    
    def footer(self) -> None:
        """Render page footer with page number and optional text."""
        self.set_y(-20)
        self.set_font(**self._footer_font._asdict())
        self.set_text_color(128, 128, 128)
        
        # Footer text on left
        if self._footer_text:
            self.cell(w=0, h=10, text=self._footer_text, align='L')
        
        # Page number on right
        page_text = self._page_number_format.format(nb=self.page_no())
        self.cell(w=0, h=10, text=page_text, align='R')
    
    def add_table(
        self,
        headers: List[str],
        data: TableData,
        col_widths: Optional[List[float]] = None,
        title: Optional[str] = None,
        title_style: Optional[FontFace] = None,
        max_rows_per_page: Optional[int] = None
    ) -> None:
        """
        Add a formatted data table to the report.
        
        Args:
            headers: List of column header strings
            data: List of rows, each row is a list of cell values
            col_widths: Optional list of column widths (auto-calculated if None)
            title: Optional table title
            title_style: Optional FontFace for title
            max_rows_per_page: Optional max rows before forced page break
            
        Raises:
            ValueError: If headers/data length mismatch or invalid data
        """
        if not headers:
            raise ValueError("Headers list cannot be empty")
        if not data:
            return  # Nothing to render
        
        # Validate data consistency
        for i, row in enumerate(data):
            if len(row) != len(headers):
                raise ValueError(f"Row {i} has {len(row)} columns, expected {len(headers)}")
        
        # Calculate column widths if not provided
        if col_widths is None:
            col_widths = self._calculate_column_widths(headers, data)
        elif len(col_widths) != len(headers):
            raise ValueError("col_widths length must match headers length")
        
        # Table title
        if title:
            style = title_style or FontFace(family='Helvetica', style='B', size=12)
            self.set_font(**style._asdict())
            self.set_text_color(*self._header_color)
            self.cell(w=0, h=10, text=title, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.ln(2)
        
        # Render table with pagination
        self._render_table(headers, data, col_widths, max_rows_per_page)
    
    def _calculate_column_widths(
        self,
        headers: List[str],
        data: TableData,
        max_width: Optional[float] = None
    ) -> List[float]:
        """Calculate optimal column widths based on content."""
        available_width = self.w - self.l_margin - self.r_margin
        if max_width:
            available_width = min(available_width, max_width)
        
        # Start with header widths
        self.set_font(**self._table_header_font._asdict())
        col_widths = [
            max(self.get_string_width(h) + 4, 15) for h in headers
        ]
        
        # Check data widths (sample first 50 rows for performance)
        self.set_font(**self._table_body_font._asdict())
        for row in data[:50]:
            for i, cell in enumerate(row):
                cell_width = self.get_string_width(str(cell)) + 4
                if cell_width > col_widths[i]:
                    col_widths[i] = cell_width
        
        # Scale to fit page if needed
        total_width = sum(col_widths)
        if total_width > available_width:
            scale = available_width / total_width
            col_widths = [w * scale for w in col_widths]
        
        return col_widths
    
    def _render_table(
        self,
        headers: List[str],
        data: TableData,
        col_widths: List[float],
        max_rows_per_page: Optional[int] = None
    ) -> None:
        """Render table with header repetition on page breaks."""
        row_height = 6
        rows_per_page = max_rows_per_page or 9999
        rows_on_current_page = 0
        
        def draw_header() -> None:
            """Draw table header row."""
            self.set_font(**self._table_header_font._asdict())
            self.set_fill_color(*self._header_color)
            self.set_text_color(255, 255, 255)
            for i, header in enumerate(headers):
                self.cell(
                    w=col_widths[i],
                    h=row_height,
                    text=str(header),
                    border=1,
                    fill=True,
                    align='C'
                )
            self.ln()
        
        def draw_row(row: List[Any], row_idx: int) -> None:
            """Draw a single data row."""
            fill = row_idx % 2 == 1
            if fill:
                self.set_fill_color(*self._alternate_row_color)
            else:
                self.set_fill_color(255, 255, 255)
            
            self.set_font(**self._table_body_font._asdict())
            self.set_text_color(0, 0, 0)
            
            max_h = row_height
            # Calculate required height for multi-line cells
            for i, cell in enumerate(row):
                lines = self.multi_cell(
                    w=col_widths[i],
                    h=row_height,
                    text=str(cell),
                    border=0,
                    split_only=True
                )
                needed_h = len(lines) * row_height
                if needed_h > max_h:
                    max_h = needed_h
            
            # Check page break
            if self.get_y() + max_h > self.h - self.b_margin:
                self.add_page()
                draw_header()
                nonlocal rows_on_current_page
                rows_on_current_page = 0
            
            x_start = self.get_x()
            y_start = self.get_y()
            
            for i, cell in enumerate(row):
                x = x_start + sum(col_widths[:i])
                self.set_xy(x, y_start)
                self.multi_cell(
                    w=col_widths[i],
                    h=row_height,
                    text=str(cell),
                    border=1,
                    fill=fill,
                    align='L'
                )
            
            # Move to next row position
            self.set_xy(x_start, y_start + max_h)
            rows_on_current_page += 1
        
        # Draw initial header
        draw_header()
        
        # Draw data rows
        for idx, row in enumerate(data):
            if rows_on_current_page >= rows_per_page:
                self.add_page()
                draw_header()
                rows_on_current_page = 0
            draw_row(row, idx)
        
        self.ln(5)
    
    def add_chart(
        self,
        chart_type: str,
        data: ChartData,
        title: str = '',
        xlabel: str = '',
        ylabel: str = '',
        width: float = 180,
        height: float = 100,
        dpi: int = 150,
        colors: Optional[List[str]] = None
    ) -> None:
        """
        Generate and insert a chart into the report.
        
        Args:
            chart_type: Type of chart ('bar', 'line', 'pie')
            data: Dictionary containing chart data:
                - For bar/line: {'x': [...], 'y': [...], 'labels': [...]}
                - For pie: {'values': [...], 'labels': [...]}
            title: Chart title
            xlabel: X-axis label (bar/line only)
            ylabel: Y-axis label (bar/line only)
            width: Image width in mm
            height: Image height in mm
            dpi: Rendering DPI
            colors: Optional list of color strings
            
        Raises:
            ValueError: If chart_type unsupported or data invalid
            RuntimeError: If chart generation fails
        """
        if chart_type not in ('bar', 'line', 'pie'):
            raise ValueError(f"Unsupported chart type: {chart_type}")
        
        # Validate data structure
        self._validate_chart_data(chart_type, data)
        
        # Generate chart image
        img_buffer = io.BytesIO()
        try:
            self._generate_chart(chart_type, data, title, xlabel, ylabel, colors)
            plt.savefig(img_buffer, format='png', dpi=dpi, bbox_inches='tight')
            plt.close()
        except Exception as e:
            plt.close()
            raise RuntimeError(f"Chart generation failed: {e}") from e
        
        img_buffer.seek(0)
        
        # Check if we need a page break
        if self.get_y() + height > self.h - self.b_margin:
            self.add_page()
        
        # Insert image
        self.image(img_buffer, w=width, h=height)
        self.ln(5)
    
    def _validate_chart_data(self, chart_type: str, data: ChartData) -> None:
        """Validate chart data structure."""
        if chart_type in ('bar', 'line'):
            required = {'x', 'y'}
            if not all(k in data for k in required):
                raise ValueError(f"{chart_type} chart requires 'x' and 'y' keys in data")
            if len(data['x']) != len(data['y']):
                raise ValueError("'x' and 'y' must have same length")
        elif chart_type == 'pie':
            required = {'values', 'labels'}
            if not all(k in data for k in required):
                raise ValueError("Pie chart requires 'values' and 'labels' keys")
            if len(data['values']) != len(data['labels']):
                raise ValueError("'values' and 'labels' must have same length")
    
    def _generate_chart(
        self,
        chart_type: str,
        data: ChartData,
        title: str,
        xlabel: str,
        ylabel: str,
        colors: Optional[List[str]]
    ) -> None:
        """Generate matplotlib chart."""
        plt.figure(figsize=(width/25.4, height/25.4))  # Convert mm to inches
        plt.style.use('seaborn-v0_8-whitegrid')
        
        if colors:
            plt.rcParams['axes.prop_cycle'] = plt.cycler(color=colors)
        
        if chart_type ==