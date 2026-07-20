from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER
from reportlab.lib import colors
from reportlab.graphics.shapes import Drawing
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.charts.linecharts import HorizontalLineChart
from reportlab.graphics.charts.piecharts import Pie
from reportlab.graphics.charts.legends import Legend
from reportlab.lib.units import inch
from io import BytesIO
import matplotlib.pyplot as plt
from typing import List, Dict

def generate_pdf_report(data: Dict, output_file: str) -> None:
    """
    Generate a PDF report from the given data.

    Args:
    data (Dict): A dictionary containing the data to be included in the report.
    output_file (str): The file path to save the generated PDF report.
    """

    # Create a PDF document with a header and footer
    doc = SimpleDocTemplate(output_file, pagesize=letter)

    # Define the styles for the report
    styles = getSampleStyleSheet()
    style = styles['Normal']
    style.alignment = TA_CENTER

    # Create a title paragraph
    title = Paragraph('PDF Report', styles['Heading1'])
    elements = [title]

    # Add a spacer to separate the title from the rest of the content
    elements.append(Spacer(1, 12))

    # Add a table with the given data
    table_data = data.get('table_data', [])
    if table_data:
        table = Table(table_data, style=TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightblue),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ]))
        elements.append(table)

    # Add a bar chart
    bar_chart_data = data.get('bar_chart_data', [])
    if bar_chart_data:
        drawing = Drawing(400, 200)
        chart = VerticalBarChart()
        chart.x = 50
        chart.y = 50
        chart.height = 125
        chart.width = 300
        chart.data = bar_chart_data
        drawing.add(chart)
        elements.append(drawing)

    # Add a line chart
    line_chart_data = data.get('line_chart_data', [])
    if line_chart_data:
        drawing = Drawing(400, 200)
        chart = HorizontalLineChart()
        chart.x = 50
        chart.y = 50
        chart.height = 125
        chart.width = 300
        chart.data = line_chart_data
        drawing.add(chart)
        elements.append(drawing)

    # Add a pie chart
    pie_chart_data = data.get('pie_chart_data', [])
    if pie_chart_data:
        drawing = Drawing(400, 200)
        chart = Pie()
        chart.x = 150
        chart.y = 100
        chart.height = 100
        chart.width = 100
        chart.data = pie_chart_data
        drawing.add(chart)
        elements.append(drawing)

    # Add a legend for the charts
    chart_legend = Legend()
    chart_legend.x = 150
    chart_legend.y = 100
    chart_legend.height = 50
    chart_legend.width = 100
    elements.append(chart_legend)

    # Add a spacer to separate the content from the footer
    elements.append(Spacer(1, 12))

    # Create a footer paragraph
    footer = Paragraph('Footer', styles['BodyText'])
    elements.append(footer)

    # Build the PDF document
    doc.build(elements)

# Example usage
if __name__ == "__main__":
    data = {
        'table_data': [
            ['Column 1', 'Column 2', 'Column 3'],
            ['Row 1, Column 1', 'Row 1, Column 2', 'Row 1, Column 3'],
            ['Row 2, Column 1', 'Row 2, Column 2', 'Row 2, Column 3'],
        ],
        'bar_chart_data': [[10, 20, 30]],
        'line_chart_data': [[10, 20, 30]],
        'pie_chart_data': [10, 20, 30],
    }
    generate_pdf_report(data, 'example.pdf')