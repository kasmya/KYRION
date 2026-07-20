# pdf_report_generator.py
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    PageBreak
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.graphics.charts import charts, bar, line, pie
from reportlab.graphics import renderPDF
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from dataclasses import dataclass
from typing import List

@dataclass
class TableRow:
    """Represents a row in the report table."""
    name: str
    value1: int
    value2: int

@dataclass
class ChartData:
    """Represents data for a chart in the report."""
    labels: List[str]
    values: List[int]
    chart_type: str  # 'bar', 'line', 'pie'

class PDFReportGenerator:
    """
    Generates PDF reports with header, footer, tables, charts, and multi-page support.

    Attributes:
    - report_path: Path to save the generated PDF report.
    - header_text: Text to display in the report header.
    - footer_text: Text to display in the report footer.
    - data: List of TableRow objects for table generation.
    - charts: List of ChartData objects for chart insertion.
    """

    def __init__(self, report_path: str, header_text: str, footer_text: str):
        """
        Initializes the PDFReportGenerator.

        :param report_path: Path to save the generated PDF report.
        :param header_text: Text to display in the report header.
        :param footer_text: Text to display in the report footer.
        """
        self.report_path = report_path
        self.header_text = header_text
        self.footer_text = footer_text
        self.data: List[TableRow] = []
        self.charts: List[ChartData] = []

    def add_table_data(self, row: TableRow):
        """Adds a row to the table data."""
        self.data.append(row)

    def add_chart(self, chart: ChartData):
        """Adds a chart to the report."""
        if chart.chart_type not in ['bar', 'line', 'pie']:
            raise ValueError("Invalid chart type. Supported types: bar, line, pie")
        self.charts.append(chart)

    def _generate_header_footer_styles(self):
        """Generates styles for header and footer."""
        styles = getSampleStyleSheet()
        header_style = ParagraphStyle(
            name='Header',
            fontSize=16,
            leading=18,
            textAlign=TA_CENTER,
            spaceBefore=12,
            spaceAfter=12
        )
        footer_style = ParagraphStyle(
            name='Footer',
            fontSize=12,
            leading=14,
            textAlign=TA_CENTER,
            spaceBefore=6,
            spaceAfter=6
        )
        return styles, header_style, footer_style

    def _build_table(self):
        """Builds the table element for the report."""
        if not self.data:
            return []
        table_data = [
            ["Name", "Value 1", "Value 2"],
            *[row.__dict__.values() for row in self.data]
        ]
        table = Table(table_data, colWidths=[3 * inch, 1.5 * inch, 1.5 * inch])
        table_style = TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('TOPPADDING', (0, 1), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 5),
            ('LINEABOVE', (0, 0), (-1, 0), 1, colors.black),
            ('LINEBELOW', (0, -1), (-1, -1), 1, colors.black),
            ('GRID', (0, 1), (-1, -1), 1, colors.black)
        ])
        table.applyStyle(table_style)
        return [table]

    def _generate_charts(self):
        """Generates charts based on provided data."""
        chart_elements = []
        for idx, chart in enumerate(self.charts):
            if chart.chart_type == 'bar':
                c = bar.BarChart()
            elif chart.chart_type == 'line':
                c = line.LineChart()
            else:  # pie
                c = pie.PieChart()
            
            c.data = [chart.values]
            c.labels = chart.labels
            c.width = 400
            c.height = 200
            # For demonstration, charts are placed sequentially without complex layout management
            chart_elements.append(Spacer(1, 12))  # Spacer before each chart
            chart_elements.append(renderPDF.drawNoSave(c))
            if idx < len(self.charts) - 1:  # Add page break between charts if not last
                chart_elements.append(PageBreak())
        return chart_elements

    def generate_report(self):
        """
        Generates the PDF report.

        :raises Exception: If report generation fails.
        """
        try:
            styles, header_style, footer_style = self._generate_header_footer_styles()
            header = Paragraph(self.header_text, header_style)
            footer = Paragraph(self.footer_text, footer_style)

            elements = [header]
            elements.extend(self._build_table())
            elements.extend(self._generate_charts())
            elements.append(Spacer(1, 48))  # Spacer before footer
            elements.append(footer)

            doc = SimpleDocTemplate(self.report_path, pagesize=letter)
            doc.build(elements, onFirstPage=True, onLaterPages=True)

        except Exception as e:
            print(f"Report generation failed: {e}")
            raise

# Example Usage
if __name__ == "__main__":
    generator = PDFReportGenerator("example_report.pdf", "Report Header", "Report Footer")

    # Adding table data
    generator.add_table_data(TableRow("Item 1", 10, 20))
    generator.add_table_data(TableRow("Item 2", 30, 40))

    # Adding charts
    chart_data = ChartData(["A", "B"], [15, 25], 'bar')
    generator.add_chart(chart_data)
    generator.add_chart(ChartData(["X", "Y"], [5, 10], 'pie'))  # Demo with pie chart

    # Generate report
    generator.generate_report()