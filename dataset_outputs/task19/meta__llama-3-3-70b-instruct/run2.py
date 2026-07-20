from typing import List, Tuple, Dict
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.graphics.shapes import Drawing, Rect, String
from reportlab.graphics import renderPDF
from reportlab.graphics.charts.barcharts import HorizontalBarChart
from reportlab.graphics.charts.linecharts import LineChart
from reportlab.graphics.charts.piecharts import Pie
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
import os

class PDFReportGenerator:
    def __init__(self, filename: str, data: List[Dict[str, str]], 
                 header: str, footer: str, charts: List[Dict[str, str]]):
        """
        Initializes the PDF report generator.

        Args:
        filename (str): The filename for the generated PDF.
        data (List[Dict[str, str]]): The data to be used in the report.
        header (str): The header text.
        footer (str): The footer text.
        charts (List[Dict[str, str]]): The charts to be inserted.
        """
        self.filename = filename
        self.data = data
        self.header = header
        self.footer = footer
        self.charts = charts

    def generate_report(self) -> None:
        """
        Generates the PDF report.
        """
        # Create a PDF file
        pdf_file = SimpleDocTemplate(self.filename, pagesize=letter)

        # Create styles
        styles = getSampleStyleSheet()
        style = ParagraphStyle(name='BodyText', parent=styles['Normal'], alignment=TA_LEFT)
        style.fontName = 'Helvetica'
        style.fontSize = 12

        # Create elements
        elements: List = []

        # Add header
        header_para = Paragraph(self.header, style=styles['Heading1'])
        elements.append(header_para)
        elements.append(Spacer(1, 12))

        # Add data table
        table_data = []
        for row in self.data:
            table_row = []
            for col in row.values():
                table_row.append(col)
            table_data.append(table_row)
        table = Table(table_data, style=TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
        ]))
        elements.append(table)
        elements.append(Spacer(1, 12))

        # Add charts
        for chart in self.charts:
            if chart['type'] == 'bar':
                chart_obj = HorizontalBarChart()
                chart_obj.x = 50
                chart_obj.y = 50
                chart_obj.height = 200
                chart_obj.width = 300
                chart_obj.data = [tuple([int(x) for x in chart['data']])]
                drawing = Drawing(400, 200)
                drawing.add(chart_obj)
                elements.append(drawing)
            elif chart['type'] == 'line':
                chart_obj = LineChart()
                chart_obj.x = 50
                chart_obj.y = 50
                chart_obj.height = 200
                chart_obj.width = 300
                chart_obj.data = [tuple([int(x) for x in chart['data']])]
                drawing = Drawing(400, 200)
                drawing.add(chart_obj)
                elements.append(drawing)
            elif chart['type'] == 'pie':
                chart_obj = Pie()
                chart_obj.x = 50
                chart_obj.y = 50
                chart_obj.height = 200
                chart_obj.width = 300
                chart_obj.data = [tuple([int(x) for x in chart['data']])]
                drawing = Drawing(400, 200)
                drawing.add(chart_obj)
                elements.append(drawing)

        # Add footer
        footer_para = Paragraph(self.footer, style=styles['Normal'])
        elements.append(footer_para)

        # Build the PDF
        pdf_file.build(elements)

def main() -> None:
    data = [
        {'Name': 'John', 'Age': '25'},
        {'Name': 'Jane', 'Age': '30'}
    ]
    header = 'PDF Report Header'
    footer = 'PDF Report Footer'
    charts = [
        {'type': 'bar', 'data': '10,20,30'},
        {'type': 'line', 'data': '40,50,60'},
        {'type': 'pie', 'data': '70,80,90'}
    ]

    generator = PDFReportGenerator('report.pdf', data, header, footer, charts)
    generator.generate_report()

if __name__ == '__main__':
    main()