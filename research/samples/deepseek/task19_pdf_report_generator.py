"""
PDF Report Generator with ReportLab for creating professional reports.

Features:
- Generate PDF from templates
- Add tables, charts, images
- Headers, footers, page numbers
- CSV data import
- Custom styling and layouts
"""

import os
import sys
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple
from pathlib import Path
import argparse
import tempfile

import pandas as pd
import numpy as np
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch, mm, cm
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    Image, PageBreak, KeepTogether, Frame, PageTemplate,
    BaseDocTemplate
)
from reportlab.platypus.flowables import HRFlowable
from reportlab.graphics.shapes import Drawing, Rect, String, Line
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.charts.piecharts import Pie
from reportlab.graphics.charts.linecharts import HorizontalLineChart
from reportlab.graphics.charts.legends import Legend
from reportlab.graphics import renderPDF
from reportlab.pdfgen import canvas
import matplotlib.pyplot as plt
from io import BytesIO

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('pdf_generator.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class PDFReport:
    """Generate professional PDF reports with ReportLab."""
    
    def __init__(
        self,
        filename: str,
        pagesize: Tuple = A4,
        title: str = "Report",
        author: str = "PDF Generator"
    ):
        """
        Initialize PDF report.
        
        Args:
            filename: Output PDF filename
            pagesize: Page size tuple
            title: Report title
            author: Report author
        """
        self.filename = filename
        self.title = title
        self.author = author
        self.pagesize = pagesize
        self.width, self.height = pagesize
        
        # Setup document
        self.doc = SimpleDocTemplate(
            filename,
            pagesize=pagesize,
            rightMargin=72,
            leftMargin=72,
            topMargin=72,
            bottomMargin=72,
            title=title,
            author=author
        )
        
        # Story (content elements)
        self.story = []
        
        # Styles
        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()
        
        # Page number
        self.page_number = 0
    
    def _setup_custom_styles(self) -> None:
        """Setup custom paragraph styles."""
        self.styles.add(ParagraphStyle(
            name='CustomTitle',
            parent=self.styles['Title'],
            fontSize=28,
            spaceAfter=30,
            textColor=colors.HexColor('#1a1a2e'),
            alignment=TA_CENTER
        ))
        
        self.styles.add(ParagraphStyle(
            name='CustomHeading1',
            parent=self.styles['Heading1'],
            fontSize=20,
            spaceAfter=12,
            textColor=colors.HexColor('#16213e'),
            borderWidth=0,
            borderPadding=0
        ))
        
        self.styles.add(ParagraphStyle(
            name='CustomHeading2',
            parent=self.styles['Heading2'],
            fontSize=16,
            spaceAfter=10,
            textColor=colors.HexColor('#0f3460')
        ))
        
        self.styles.add(ParagraphStyle(
            name='CustomNormal',
            parent=self.styles['Normal'],
            fontSize=11,
            leading=16,
            spaceAfter=8
        ))
        
        self.styles.add(ParagraphStyle(
            name='TableCell',
            parent=self.styles['Normal'],
            fontSize=10,
            leading=14
        ))
        
        self.styles.add(ParagraphStyle(
            name='Footer',
            parent=self.styles['Normal'],
            fontSize=8,
            textColor=colors.gray
        ))
    
    def _on_first_page(self, canvas, doc) -> None:
        """Draw header/footer on first page."""
        canvas.saveState()
        
        # Title on first page
        canvas.setFont('Helvetica-Bold', 12)
        canvas.drawString(
            72, self.height - 40, self.title
        )
        
        # Line under header
        canvas.line(72, self.height - 45, self.width - 72, self.height - 45)
        
        canvas.restoreState()
    
    def _on_later_pages(self, canvas, doc) -> None:
        """Draw header/footer on later pages."""
        canvas.saveState()
        
        # Header
        canvas.setFont('Helvetica', 10)
        canvas.drawString(72, self.height - 40, self.title)
        
        # Page number
        canvas.setFont('Helvetica', 9)
        canvas.drawRightString(
            self.width - 72, self.height - 40, f"Page {doc.page}"
        )
        
        # Footer line
        canvas.line(72, 50, self.width - 72, 50)
        
        # Footer
        canvas.setFont('Helvetica', 8)
        canvas.setFillColor(colors.gray)
        canvas.drawString(
            72, 35,
            f"Generated on {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        )
        canvas.drawRightString(
            self.width - 72, 35,
            f"Confidential"
        )
        
        canvas.restoreState()
    
    def add_title_page(self, subtitle: Optional[str] = None) -> None:
        """
        Add a title page.
        
        Args:
            subtitle: Optional subtitle
        """
        self.story.append(Spacer(1, 2 * inch))
        self.story.append(Paragraph(self.title, self.styles['CustomTitle']))
        
        if subtitle:
            self.story.append(Paragraph(subtitle, self.styles['CustomNormal']))
        
        self.story.append(Spacer(1, 1 * inch))
        self.story.append(Paragraph(
            f"Author: {self.author}", self.styles['CustomNormal']
        ))
        self.story.append(Paragraph(
            f"Date: {datetime.now().strftime('%B %d, %Y')}",
            self.styles['CustomNormal']
        ))
        self.story.append(PageBreak())
    
    def add_heading(self, text: str, level: int = 1) -> None:
        """
        Add a heading.
        
        Args:
            text: Heading text
            level: Heading level (1 or 2)
        """
        style = self.styles[f'CustomHeading{level}']
        self.story.append(Paragraph(text, style))
    
    def add_paragraph(self, text: str, bold: bool = False) -> None:
        """
        Add a paragraph.
        
        Args:
            text: Paragraph text
            bold: Make text bold
        """
        style = self.styles['CustomNormal']
        if bold:
            style = ParagraphStyle(
                'Bold', parent=style, fontName='Helvetica-Bold'
            )
        self.story.append(Paragraph(text, style))
    
    def add_table(
        self,
        data: List[List[Any]],
        headers: Optional[List[str]] = None,
        col_widths: Optional[List[float]] = None,
        style: Optional[List[Tuple]] = None
    ) -> None:
        """
        Add a table to the report.
        
        Args:
            data: Table data (list of rows)
            headers: Column headers
            col_widths: Column widths
            style: Additional table style commands
        """
        if headers:
            data = [headers] + data
        
        # Convert data to Paragraphs for styling
        formatted_data = []
        for row in data:
            formatted_row = []
            for cell in row:
                if not isinstance(cell, Paragraph):
                    cell = Paragraph(str(cell), self.styles['TableCell'])
                formatted_row.append(cell)
            formatted_data.append(formatted_row)
        
        # Calculate column widths if not provided
        if not col_widths:
            available_width = self.width - 144  # Margins
            col_widths = [available_width / len(data[0])] * len(data[0])
        
        table = Table(formatted_data, colWidths=col_widths, repeatRows=1)
        
        # Default table style
        table_style = [
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#16213e')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 11),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('TOPPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f5f5f5')),
            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#cccccc')),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 1), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 8),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ]
        
        # Alternate row colors
        for i in range(1, len(data)):
            if i % 2 == 0:
                table_style.append(
                    ('BACKGROUND', (0, i), (-1, i), colors.HexColor('#e8e8e8'))
                )
        
        # Apply custom style if provided
        if style:
            table_style.extend(style)
        
        table.setStyle(TableStyle(table_style))
        
        self.story.append(Spacer(1, 6))
        self.story.append(table)
        self.story.append(Spacer(1, 12))
    
    def add_bar_chart(
        self,
        data: Dict[str, float],
        title: str = "Bar Chart",
        width: int = 450,
        height: int = 250
    ) -> None:
        """
        Add a bar chart.
        
        Args:
            data: Dictionary of label-value pairs
            title: Chart title
            width: Chart width
            height: Chart height
        """
        drawing = Drawing(width, height)
        
        # Create bar chart
        chart = VerticalBarChart()
        chart.x = 60
        chart.y = 30
        chart.width = width - 80
        chart.height = height - 60
        
        # Data
        chart.data = [list(data.values())]
        chart.categoryAxis.categoryNames = list(data.keys())
        
        # Styling
        chart.bars[0].fillColor = colors.HexColor('#4ec9b0')
        chart.bars[0].strokeColor = colors.HexColor('#3aa88e')
        chart.categoryAxis.labels.angle = 45
        chart.categoryAxis.labels.fontSize = 8
        chart.valueAxis.valueMin = 0
        
        # Title
        title_obj = String(0, height - 20, title)
        title_obj.fontSize = 14
        title_obj.fontName = 'Helvetica-Bold'
        title_obj.fillColor = colors.HexColor('#16213e')
        title_obj.x = (width - title_obj.getBounds()[2]) / 2
        
        drawing.add(title_obj)
        drawing.add(chart)
        
        self.story.append(Spacer(1, 12))
        self.story.append(drawing)
        self.story.append(Spacer(1, 12))
    
    def add_pie_chart(
        self,
        data: Dict[str, float],
        title: str = "Pie Chart",
        width: int = 400,
        height: int = 300
    ) -> None:
        """
        Add a pie chart.
        
        Args:
            data: Dictionary of label-value pairs
            title: Chart title
            width: Chart width
            height: Chart height
        """
        drawing = Drawing(width, height)
        
        # Create pie chart
        pie = Pie()
        pie.x = width / 2 - 75
        pie.y = 50
        pie.width = 150
        pie.height = 150
        
        pie.data = list(data.values())
        pie.labels = list(data.keys())
        
        # Colors
        pie_colors = [
            colors.HexColor('#4ec9b0'),
            colors.HexColor('#569cd6'),
            colors.HexColor('#e94560'),
            colors.HexColor('#f0c040'),
            colors.HexColor('#a855f7'),
        ]
        
        for i, slice in enumerate(pie.slices):
            slice.fillColor = pie_colors[i % len(pie_colors)]
            slice.strokeColor = colors.white
            slice.strokeWidth = 2
            slice.labelRadius = 1.3
        
        # Legend
        legend = Legend()
        legend.x = width - 130
        legend.y = 150
        legend.alignment = 'right'
        legend.fontSize = 9
        
        legend_items = []
        for i, (label, value) in enumerate(data.items()):
            legend_items.append((pie_colors[i % len(pie_colors)], label))
        
        legend.colorNamePairs = legend_items
        
        # Title
        title_obj = String(0, height - 20, title)
        title_obj.fontSize = 14
        title_obj.fontName = 'Helvetica-Bold'
        title_obj.fillColor = colors.HexColor('#16213e')
        title_obj.x = (width - title_obj.getBounds()[2]) / 2
        
        drawing.add(title_obj)
        drawing.add(pie)
        drawing.add(legend)
        
        self.story.append(Spacer(1, 12))
        self.story.append(drawing)
        self.story.append(Spacer(1, 12))
    
    def add_matplotlib_chart(self, fig) -> None:
        """
        Add a matplotlib chart as image.
        
        Args:
            fig: Matplotlib figure
        """
        # Save figure to buffer
        buf = BytesIO()
        fig.savefig(buf, format='png', dpi=150, bbox_inches='tight')
        buf.seek(0)
        
        # Create Image flowable
        img = Image(buf, width=450, height=300)
        
        self.story.append(Spacer(1, 12))
        self.story.append(img)
        self.story.append(Spacer(1, 12))
        
        plt.close(fig)
    
    def add_image(
        self,
        image_path: str,
        width: Optional[float] = None,
        height: Optional[float] = None,
        caption: Optional[str] = None
    ) -> None:
        """
        Add an image.
        
        Args:
            image_path: Path to image file
            width: Image width
            height: Image height
            caption: Image caption
        """
        if not os.path.exists(image_path):
            logger.warning(f"Image not found: {image_path}")
            return
        
        img = Image(image_path)
        
        # Scale image
        if width and height:
            img = Image(image_path, width=width, height=height)
        elif width:
            aspect = img.imageHeight / img.imageWidth
            img = Image(image_path, width=width, height=width * aspect)
        elif height:
            aspect = img.imageWidth / img.imageHeight
            img = Image(image_path, width=height * aspect, height=height)
        
        self.story.append(Spacer(1, 12))
        self.story.append(img)
        
        if caption:
            caption_style = ParagraphStyle(
                'Caption',
                parent=self.styles['Normal'],
                fontSize=9,
                textColor=colors.gray,
                alignment=TA_CENTER
            )
            self.story.append(Paragraph(caption, caption_style))
        
        self.story.append(Spacer(1, 12))
    
    def add_horizontal_line(self) -> None:
        """Add a horizontal line."""
        self.story.append(HRFlowable(
            width="100%",
            thickness=1,
            color=colors.HexColor('#cccccc')
        ))
        self.story.append(Spacer(1, 6))
    
    def add_page_break(self) -> None:
        """Add a page break."""
        self.story.append(PageBreak())
    
    def add_summary_box(
        self,
        metrics: Dict[str, Any],
        title: str = "Summary"
    ) -> None:
        """
        Add a summary/metrics box.
        
        Args:
            metrics: Dictionary of metric name-value pairs
            title: Box title
        """
        # Create a colored box with metrics
        data = [[title, '']]
        for key, value in metrics.items():
            data.append([key, str(value)])
        
        table = Table(data, colWidths=[200, 200])
        table.setStyle(TableStyle([
            ('SPAN', (0, 0), (-1, 0)),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#16213e')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 14),
            ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f0f8ff')),
            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#b0c4de')),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ]))
        
        self.story.append(Spacer(1, 12))
        self.story.append(table)
        self.story.append(Spacer(1, 12))
    
    def build(self) -> str:
        """
        Build and save the PDF report.
        
        Returns:
            Path to generated PDF
        """
        try:
            # Add page templates
            first_page = PageTemplate(
                id='First', frames=[Frame(
                    72, 72, self.width - 144, self.height - 144
                )],
                onPage=self._on_first_page
            )
            
            later_pages = PageTemplate(
                id='Later', frames=[Frame(
                    72, 72, self.width - 144, self.height - 144
                )],
                onPage=self._on_later_pages
            )
            
            self.doc.addPageTemplates([first_page, later_pages])
            
            # Build document
            self.doc.build(self.story)
            
            logger.info(f"PDF report generated: {self.filename}")
            return self.filename
            
        except Exception as e:
            logger.error(f"Error building PDF: {str(e)}", exc_info=True)
            raise
    
    @classmethod
    def from_csv(
        cls,
        csv_path: str,
        output_path: str,
        title: str = "Data Report",
        author: str = "PDF Generator"
    ) -> 'PDFReport':
        """
        Generate report from CSV data.
        
        Args:
            csv_path: Path to CSV file
            output_path: Output PDF path
            title: Report title
            author: Report author
            
        Returns:
            PDFReport instance
        """
        # Load CSV
        df = pd.read_csv(csv_path)
        
        # Create report
        report = cls(output_path, title=title, author=author)
        
        # Title page
        report.add_title_page(f"Data Analysis Report")
        
        # Summary
        report.add_heading("Data Summary", 1)
        report.add_paragraph(f"Total records: {len(df)}")
        report.add_paragraph(f"Total columns: {len(df.columns)}")
        
        # Data preview
        report.add_heading("Data Preview", 2)
        report.add_paragraph("First 10 rows of the dataset:")
        
        # Convert DataFrame to table data
        preview_data = df.head(10).values.tolist()
        report.add_table(
            preview_data,
            headers=df.columns.tolist()
        )
        
        # Numeric statistics
        numeric_cols = df.select_dtypes(include=[np.number]).columns
        if len(numeric_cols) > 0:
            report.add_heading("Numeric Statistics", 2)
            stats_df = df[numeric_cols].describe()
            stats_data = stats_df.round(2).reset_index().values.tolist()
            report.add_table(
                stats_data,
                headers=['Statistic'] + list(stats_df.columns)
            )
            
            # Create bar chart for means
            if len(numeric_cols) >= 2:
                means = df[numeric_cols].mean().to_dict()
                report.add_heading("Average Values", 2)
                report.add_bar_chart(means, "Average Values by Column")
        
        # Build report
        report.build()
        
        return report

def main():
    """CLI entry point for PDF generator."""
    parser = argparse.ArgumentParser(
        description='Generate PDF reports from data',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate report from CSV
  python pdf_generator.py from-csv -i data.csv -o report.pdf --title "Sales Report"
  
  # Generate sample report
  python pdf_generator.py sample -o sample_report.pdf
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # CSV report command
    csv_parser = subparsers.add_parser('from-csv', help='Generate report from CSV')
    csv_parser.add_argument('-i', '--input', required=True, help='Input CSV file')
    csv_parser.add_argument('-o', '--output', required=True, help='Output PDF file')
    csv_parser.add_argument('--title', default='Data Report', help='Report title')
    csv_parser.add_argument('--author', default='PDF Generator', help='Report author')
    
    # Sample report command
    sample_parser = subparsers.add_parser('sample', help='Generate sample report')
    sample_parser.add_argument('-o', '--output', required=True, help='Output PDF file')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    try:
        if args.command == 'from-csv':
            report = PDFReport.from_csv(
                args.input, args.output, args.title, args.author
            )
            print(f"✅ Report generated: {args.output}")
            
        elif args.command == 'sample':
            # Generate sample report
            report = PDFReport(args.output, title="Sample Report", author="PDF Generator")
            
            # Title page
            report.add_title_page("A Demonstration of ReportLab Features")
            
            # Introduction
            report.add_heading("Introduction", 1)
            report.add_paragraph(
                "This is a sample report demonstrating the capabilities of the PDF Report Generator. "
                "It includes various elements such as tables, charts, and formatted text."
            )
            
            # Sample table
            report.add_heading("Sample Data Table", 2)
            sample_data = [
                ['Product A', 'Electronics', '$599.99', '120 units'],
                ['Product B', 'Clothing', '$49.99', '450 units'],
                ['Product C', 'Food', '$9.99', '1200 units'],
                ['Product D', 'Books', '$19.99', '340 units'],
                ['Product E', 'Sports', '$89.99', '210 units'],
            ]
            report.add_table(
                sample_data,
                headers=['Product', 'Category', 'Price', 'Sales']
            )
            
            # Sample chart
            report.add_heading("Sales by Category", 2)
            chart_data = {
                'Electronics': 45000,
                'Clothing': 32000,
                'Food': 28000,
                'Books': 15000,
                'Sports': 22000,
            }
            report.add_bar_chart(chart_data, "Revenue by Category")
            
            # Summary box
            report.add_heading("Key Metrics", 2)
            report.add_summary_box({
                'Total Revenue': '$142,000',
                'Total Products': '1,425',
                'Active Customers': '3,240',
                'Growth Rate': '+15.3%'
            })
            
            # Build
            report.build()
            print(f"✅ Sample report generated: {args.output}")
            
    except Exception as e:
        logger.error(f"Error generating report: {str(e)}", exc_info=True)
        print(f"❌ Error: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
