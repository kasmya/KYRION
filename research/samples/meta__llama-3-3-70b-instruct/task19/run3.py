from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
from reportlab.lib.colors import Color
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.graphics import renderPDF
from reportlab.graphics.shapes import Drawing
from reportlab.graphics.charts.barcharts import HorizontalBarChart
from reportlab.graphics.charts.linecharts import LineChart
from reportlab.graphics.charts.piecharts import Pie
from typing import List, Dict

class PDFReportGenerator:
    def __init__(self, filename: str, data: Dict[str, List[float]], header: str, footer: str):
        """
        Initialize the PDF report generator.

        Args:
            filename (str): The filename of the generated PDF report.
            data (Dict[str, List[float]]): A dictionary containing the data to be used in the report.
            header (str): The header text to be displayed at the top of each page.
            footer (str): The footer text to be displayed at the bottom of each page.
        """
        self.filename = filename
        self.data = data
        self.header = header
        self.footer = footer
        self.styles = getSampleStyleSheet()

    def generate_report(self):
        """
        Generate the PDF report.
        """
        doc = SimpleDocTemplate(self.filename, pagesize=letter)
        elements = []
        self.add_header_footer(elements)
        self.add_table(elements)
        self.add_charts(elements)
        doc.build(elements)

    def add_header_footer(self, elements: List):
        """
        Add the header and footer to the report.

        Args:
            elements (List): The list of elements to be added to the report.
        """
        header_style = ParagraphStyle(name='header', fontSize=18, alignment=TA_CENTER)
        footer_style = ParagraphStyle(name='footer', fontSize=12, alignment=TA_LEFT)
        elements.append(Paragraph(self.header, header_style))
        elements.append(Spacer(1, 12))
        elements.append(Paragraph(self.footer, footer_style))

    def add_table(self, elements: List):
        """
        Add a table to the report.

        Args:
            elements (List): The list of elements to be added to the report.
        """
        table_data = []
        for key, values in self.data.items():
            table_data.append([key] + values)
        table = Table(table_data, style=TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.5, Color(0, 0, 0)),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
        ]))
        elements.append(table)
        elements.append(Spacer(1, 12))

    def add_charts(self, elements: List):
        """
        Add charts to the report.

        Args:
            elements (List): The list of elements to be added to the report.
        """
        # Bar chart
        drawing = Drawing(400, 200)
        bar_chart = HorizontalBarChart()
        bar_chart.x = 50
        bar_chart.y = 50
        bar_chart.height = 125
        bar_chart.width = 300
        bar_chart.data = [self.data['bar']]
        bar_chart.categoryAxis.labels.boxAnchor = 'c'
        bar_chart.categoryAxis.labels.dx = 8
        bar_chart.categoryAxis.labels.dy = -10
        bar_chart.bars[0].fillColor = Color(0.4, 0.5, 0.6, 0.8)
        drawing.add(bar_chart)
        elements.append(drawing)
        elements.append(Spacer(1, 12))

        # Line chart
        drawing = Drawing(400, 200)
        line_chart = LineChart()
        line_chart.x = 50
        line_chart.y = 50
        line_chart.height = 125
        line_chart.width = 300
        line_chart.data = [self.data['line']]
        line_chart.categoryAxis.labels.boxAnchor = 'c'
        line_chart.categoryAxis.labels.dx = 8
        line_chart.categoryAxis.labels.dy = -10
        line_chart.lines[0].strokeColor = Color(0.4, 0.5, 0.6, 0.8)
        drawing.add(line_chart)
        elements.append(drawing)
        elements.append(Spacer(1, 12))

        # Pie chart
        drawing = Drawing(400, 200)
        pie_chart = Pie()
        pie_chart.x = 50
        pie_chart.y = 50
        pie_chart.height = 125
        pie_chart.width = 300
        pie_chart.data = self.data['pie']
        drawing.add(pie_chart)
        elements.append(drawing)

# Example usage:
if __name__ == '__main__':
    data = {
        'bar': [10, 20, 30],
        'line': [40, 50, 60],
        'pie': [70, 80, 90]
    }
    generator = PDFReportGenerator('report.pdf', data, 'Header', 'Footer')
    generator.generate_report()