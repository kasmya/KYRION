import reportlab
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.platypus import Image
from reportlab.charts import bar, line, pie
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER
from reportlab.lib.units import pt
from typing import List, Dict
import io

class PDFReportGenerator:
    """Generates PDF reports from data with header, footer, table, chart, and multi-page support."""
    
    def __init__(self, file_path: str, header_text: str, footer_text: str):
        """
        Initializes the PDF report generator.

        Args:
        - file_path (str): Path to save the PDF file.
        - header_text (str): Text to display in the header.
        - footer_text (str): Text to display in the footer.
        """
        self.file_path = file_path
        self.header_text = header_text
        self.footer_text = footer_text
        selfpdf = SimpleDocTemplate(file_path, pagesize=letter)
        self.elements = []

    def add_header_footer(self, canvas, doc):
        """Adds header and footer to the PDF page."""
        # Header
        canvas.saveState()
        canvas.setFont("Helvetica", 12)
        canvas.drawString(1 * inch, 10.5 * inch, self.header_text)
        canvas.restoreState()
        
        # Footer
        canvas.saveState()
        canvas.setFillColor(colors.black)
        canvas.setFont("Helvetica", 10)
        canvas.drawString(1 * inch, 0.5 * inch, self.footer_text)
        canvas.showPageNumber()
        canvas.restoreState()

    def add_table(self, data: List[List[str]], styles: Dict[str, str]):
        """
        Adds a table to the PDF report.

        Args:
        - data (List[List[str]]): Table data.
        - styles (Dict[str, str]): Table style options (e.g., align, font).
        """
        table = Table(data)
        table_style = TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.grey),
            ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,0), 12),
            ('BOTTOMPADDING', (0,0), (-1,0), 12),
            ('TOPPADDING', (1,0), (-1,-1), 12),
            ('GRID', (0,0), (-1,-1), 1, colors.black),
        ])
        table.setStyle(table_style)
        self.elements.append(table)

    def add_chart(self, chart_type: str, data: List[float], labels: List[str]):
        """
        Adds a chart to the PDF report.

        Args:
        - chart_type (str): Type of chart (bar, line, pie).
        - data (List[float]): Chart data.
        - labels (List[str]): Chart labels.
        """
        if chart_type == 'bar':
            chart = bar.BarChart()
            chart.data = [data]
            chart.categories = labels
        elif chart_type == 'line':
            chart = line.LineChart()
            chart.data = [data]
            chart.categories = labels
        elif chart_type == 'pie':
            chart = pie.PieChart()
            chart.data = data
            chart.labels = labels
        else:
            raise ValueError("Invalid chart type. Supported types: bar, line, pie.")
        
        w, h = 400, 300
        chart.width, chart.height = w, h
        img = Image(io.BytesIO(chart.draw()[0]), width=w/3, height=h/3)
        self.elements.append(img)

    def add_page_break(self):
        """Adds a page break to the PDF report."""
        self.elements.append(PageBreak())

    def generate_report(self):
        """Generates the PDF report."""
        self.pdf.build(self.elements, onFirstPage=self.add_header_footer, onLaterPages=self.add_header_footer)

# Example usage
if __name__ == "__main__":
    try:
        generator = PDFReportGenerator("report.pdf", "Header Text", "Footer Text")
        
        # Add table
        table_data = [
            ["Column 1", "Column 2", "Column 3"],
            ["Row 1, Cell 1", "Row 1, Cell 2", "Row 1, Cell 3"],
            ["Row 2, Cell 1", "Row 2, Cell 2", "Row 2, Cell 3"]
        ]
        generator.add_table(table_data, {})

        # Add chart
        chart_data = [10, 20, 30, 40, 50]
        chart_labels = ['A', 'B', 'C', 'D', 'E']
        generator.add_chart('bar', chart_data, chart_labels)

        # Add page break
        generator.add_page_break()

        # Add another table on new page
        generator.add_table(table_data, {})

        # Generate report
        generator.generate_report()
        print("PDF report generated successfully.")
    
    except Exception as e:
        print(f"Error generating PDF report: {str(e)}")