"""
PDF Report Generator Module

This module provides a comprehensive PDF report generation system with support for:
- Page headers and footers
- Data tables with formatting
- Chart insertion (bar, line, pie charts)
- Multi-page document support
- Professional styling and layout

Dependencies:
    - reportlab: PDF generation library
    - matplotlib: Chart generation
    - pillow: Image processing (for chart embedding)

Example:
    >>> from pdf_report_generator import PDFReportGenerator
    >>> generator = PDFReportGenerator("report.pdf")
    >>> generator.add_header("Monthly Sales Report")
    >>> generator.add_table(headers=["Product", "Sales"], data=[["A", 100], ["B", 200]])
    >>> generator.add_bar_chart(categories=["A", "B"], values=[100, 200], title="Sales")
    >>> generator.build()
"""

import os
import tempfile
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import matplotlib
matplotlib.use('Agg')  # Non-interactive backend for security
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from PIL import Image

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4, letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch, mm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    Image as RLImage,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.flowables import Flowable


# Type aliases for clarity
TableData = List[List[Any]]
ChartData = Dict[str, Any]
ColorType = Union[Tuple[float, float, float], Tuple[float, float, float, float], str]
PageSize = Tuple[float, float]


class PDFReportGenerator:
    """
    A comprehensive PDF report generator with support for headers, footers,
    tables, charts, and multi-page documents.
    
    Attributes:
        output_path: Path where the PDF will be saved.
        page_size: Tuple of (width, height) in points.
        margin: Page margins in points.
    """
    
    def __init__(
        self,
        output_path: Union[str, Path],
        page_size: PageSize = A4,
        margins: Optional[Dict[str, float]] = None,
        title: str = "",
        author: str = "",
    ) -> None:
        """
        Initialize the PDF report generator.
        
        Args:
            output_path: Path to save the generated PDF.
            page_size: Page dimensions (width, height) in points. Defaults to A4.
            margins: Dictionary with keys 'left', 'right', 'top', 'bottom' in points.
            title: Document title for metadata.
            author: Document author for metadata.
            
        Raises:
            ValueError: If output_path is invalid or margins contain negative values.
            PermissionError: If output directory is not writable.
        """
        self._validate_output_path(output_path)
        self._validate_margins(margins or {})
        
        self.output_path = Path(output_path)
        self.page_size = page_size
        self.margins = margins or {
            'left': 72, 'right': 72, 'top': 72, 'bottom': 72
        }
        self.title = title
        self.author = author
        
        # Document state
        self._story: List[Flowable] = []
        self._header_content: Optional[str] = None
        self._footer_content: Optional[str] = None
        self._page_number: int = 0
        self._total_pages: int = 0
        
        # Styles
        self._styles = getSampleStyleSheet()
        self._setup_custom_styles()
        
        # Chart counter for unique filenames
        self._chart_counter: int = 0
        self._temp_files: List[Path] = []
    
    def _validate_output_path(self, path: Union[str, Path]) -> None:
        """Validate that the output path is writable."""
        path_obj = Path(path)
        parent = path_obj.parent
        
        if not parent.exists():
            raise ValueError(f"Output directory does not exist: {parent}")
        
        if not os.access(parent, os.W_OK):
            raise PermissionError(f"Output directory is not writable: {parent}")
        
        # Check if file exists and is writable
        if path_obj.exists() and not os.access(path_obj, os.W_OK):
            raise PermissionError(f"Output file is not writable: {path_obj}")
    
    def _validate_margins(self, margins: Dict[str, float]) -> None:
        """Validate margin values."""
        required_keys = {'left', 'right', 'top', 'bottom'}
        if not required_keys.issubset(margins.keys()):
            missing = required_keys - margins.keys()
            raise ValueError(f"Missing margin keys: {missing}")
        
        for key, value in margins.items():
            if value < 0:
                raise ValueError(f"Margin '{key}' cannot be negative: {value}")
    
    def _setup_custom_styles(self) -> None:
        """Set up custom paragraph styles."""
        self._styles.add(ParagraphStyle(
            name='ReportTitle',
            parent=self._styles['Title'],
            fontSize=18,
            leading=22,
            alignment=TA_CENTER,
            spaceAfter=12,
            textColor=colors.HexColor('#1a1a2e'),
        ))
        
        self._styles.add(ParagraphStyle(
            name='SectionHeader',
            parent=self._styles['Heading1'],
            fontSize=14,
            leading=18,
            alignment=TA_LEFT,
            spaceBefore=12,
            spaceAfter=6,
            textColor=colors.HexColor('#16213e'),
            borderWidth=0,
            borderPadding=0,
        ))
        
        self._styles.add(ParagraphStyle(
            name='SubSectionHeader',
            parent=self._styles['Heading2'],
            fontSize=12,
            leading=16,
            alignment=TA_LEFT,
            spaceBefore=8,
            spaceAfter=4,
            textColor=colors.HexColor('#0f3460'),
        ))
        
        self._styles.add(ParagraphStyle(
            name='TableHeader',
            parent=self._styles['Normal'],
            fontSize=10,
            leading=12,
            alignment=TA_CENTER,
            textColor=colors.white,
            fontName='Helvetica-Bold',
        ))
        
        self._styles.add(ParagraphStyle(
            name='TableCell',
            parent=self._styles['Normal'],
            fontSize=9,
            leading=11,
            alignment=TA_LEFT,
        ))
        
        self._styles.add(ParagraphStyle(
            name='FooterStyle',
            parent=self._styles['Normal'],
            fontSize=8,
            leading=10,
            alignment=TA_CENTER,
            textColor=colors.grey,
        ))
        
        self._styles.add(ParagraphStyle(
            name='HeaderStyle',
            parent=self._styles['Normal'],
            fontSize=10,
            leading=12,
            alignment=TA_CENTER,
            textColor=colors.HexColor('#1a1a2e'),
            fontName='Helvetica-Bold',
        ))
    
    def add_header(self, text: str, style: Optional[str] = None) -> None:
        """
        Set the page header content.
        
        Args:
            text: Header text to display on each page.
            style: Optional style name. Defaults to 'HeaderStyle'.
        """
        self._header_content = text
    
    def add_footer(self, text: str, style: Optional[str] = None) -> None:
        """
        Set the page footer content.
        
        Args:
            text: Footer text to display on each page.
            style: Optional style name. Defaults to 'FooterStyle'.
        """
        self._footer_content = text
    
    def add_title(self, title: str, subtitle: Optional[str] = None) -> None:
        """
        Add a title page or section title to the report.
        
        Args:
            title: Main title text.
            subtitle: Optional subtitle text.
        """
        self._story.append(Paragraph(title, self._styles['ReportTitle']))
        if subtitle:
            self._story.append(Paragraph(subtitle, self._styles['SectionHeader']))
        self._story.append(Spacer(1, 20))
    
    def add_section_header(self, text: str, level: int = 1) -> None:
        """
        Add a section header.
        
        Args:
            text: Header text.
            level: Header level (1 or 2). Defaults to 1.
        """
        style = 'SectionHeader' if level == 1 else 'SubSectionHeader'
        self._story.append(Paragraph(text, self._styles[style]))
    
    def add_paragraph(self, text: str, style: str = 'Normal') -> None:
        """
        Add a paragraph of text.
        
        Args:
            text: Paragraph text (supports ReportLab markup).
            style: Style name from stylesheet. Defaults to 'Normal'.
        """
        self._story.append(Paragraph(text, self._styles[style]))
        self._story.append(Spacer(1, 6))
    
    def add_spacer(self, height: float = 12) -> None:
        """
        Add vertical space.
        
        Args:
            height: Space height in points.
        """
        self._story.append(Spacer(1, height))
    
    def add_page_break(self) -> None:
        """Force a page break."""
        self._story.append(PageBreak())
    
    def add_table(
        self,
        headers: List[str],
        data: TableData,
        col_widths: Optional[List[float]] = None,
        style: Optional[TableStyle] = None,
        header_style: Optional[str] = None,
        cell_style: Optional[str] = None,
        alternating_rows: bool = True,
    ) -> None:
        """
        Add a formatted data table to the report.
        
        Args:
            headers: List of column header strings.
            data: List of rows, each row is a list of cell values.
            col_widths: Optional list of column widths in points.
            style: Optional custom TableStyle.
            header_style: Style name for header cells. Defaults to 'TableHeader'.
            cell_style: Style name for data cells. Defaults to 'TableCell'.
            alternating_rows: Whether to use alternating row colors. Defaults to True.
            
        Raises:
            ValueError: If headers and data column counts don't match.
        """
        if not headers:
            raise ValueError("Headers list cannot be empty")
        
        if data and len(data[0]) != len(headers):
            raise ValueError(
                f"Data columns ({len(data[0])}) don't match headers ({len(headers)})"
            )
        
        header_style = header_style or 'TableHeader'
        cell_style = cell_style or 'TableCell'
        
        # Prepare table data with Paragraph objects for styling
        table_data = [[Paragraph(str(h), self._styles[header_style]) for h in headers]]
        
        for row in data:
            table_data.append([
                Paragraph(str(cell), self._styles[cell_style]) for cell in row
            ])
        
        # Calculate column widths if not provided
        if col_widths is None:
            available_width = (
                self.page_size[0] - self.margins['left'] - self.margins['right']
            )
            col_widths = [available_width / len(headers)] * len(headers)
        
        # Create table
        table = Table(table_data, colWidths=col_widths, repeatRows=1)
        
        # Apply default styling if no custom style provided
        if style is None:
            style = self._get_default_table_style(alternating_rows)
        
        table.setStyle(style)
        self._story.append(table)
        self._story.append(Spacer(1, 12))
    
    def _get_default_table_style(self, alternating_rows: bool) -> TableStyle:
        """Create default table style."""
        style_commands = [
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a1a2e')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('TOPPADDING', (0, 0), (-1, 0), 8),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cccccc')),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('TOPPADDING', (0, 1), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
        ]
        
        if alternating_rows:
            for i in range(1, 100, 2):  # Support up to 100 rows
                style_commands.append(
                    ('BACKGROUND', (0, i), (-1, i), colors.HexColor('#f5f5f5'))
                )
        
        return TableStyle(style_commands)
    
    def add_bar_chart(
        self,
        categories: List[str],
        values: List[float],
        title: str = "",
        xlabel: str = "",
        ylabel: str = "",
        colors_list: Optional[List[ColorType]] = None,
        width: float = 6 * inch,
        height: float = 4 * inch,
        dpi: int = 150,
    ) -> None:
        """
        Add a bar chart to the report.
        
        Args:
            categories: List of category labels.
            values: List of numerical values.
            title: Chart title.
            xlabel: X-axis label.
            ylabel: Y-axis label.
            colors_list: Optional list of colors for bars.
            width: Chart width in points.
            height: Chart height in points.
            dpi: Image resolution.
            
        Raises:
            ValueError: If categories and values length mismatch.
        """
        if len(categories) != len(values):
            raise ValueError(
                f"Categories ({len(categories)}) and values ({len(values)}) length mismatch"
            )
        
        fig, ax = plt.subplots(figsize=(width / 72, height / 72), dpi=dpi)
        
        bars = ax.bar(categories, values, color=colors_list or '#0f3460', edgecolor='white', linewidth=0.5)
        
        if title:
            ax.set_title(title, fontsize=14, fontweight='bold', pad=15, color='#1a1a2e')
        if xlabel:
            ax.set_xlabel(xlabel, fontsize=11, color='#333333')
        if ylabel:
            ax.set_ylabel(ylabel, fontsize=11, color='#333333')
        
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['left'].set_color('#cccccc')
        ax.spines['bottom'].set_color('#cccccc')
        ax.tick_params(colors='#333333', labelsize=9)
        ax.set_axisbelow(True)
        ax.yaxis.grid(True, color='#eeeeee', linewidth=0.5)
        ax.xaxis.grid(False)
        
        # Add value labels on bars
        for bar in bars:
            height_val = bar.get_height()
            ax.annotate(
                f'{height_val:,.0f}',
                xy=(bar.get_x() + bar.get_width() / 2, height_val),
                xytext=(0, 3),
                textcoords="offset points",
                ha='center', va='bottom',
                fontsize=8, color='#333333'
            )
        
        plt.tight_layout()
        self._embed_chart(fig, width, height)
    
    def add_line_chart(
        self,
        x_values: List[Any],
        y_values: List[float],
        title: str = "",
        xlabel: str = "",
        ylabel: str = "",
        color: ColorType = '#0f3460',
        marker: str = 'o',
        line_style: str = '-',
        width: float = 6 * inch,
        height: float = 4 * inch,
        dpi: int = 150,
    ) -> None:
        """
        Add a line chart to the report.
        
        Args:
            x_values: List of x-axis values.
            y_values: List of y-axis values.
            title: Chart title.
            xlabel: X-axis label.
            ylabel: Y-axis label.
            color: Line color.
            marker: Marker style.
            line_style: Line style.
            width: Chart width in points.
            height: Chart height in points.
            dpi: Image resolution.
            
        R