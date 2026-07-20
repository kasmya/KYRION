from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.lib.colors import black, white
from reportlab.graphics import renderPM
from reportlab.graphics.shapes import Drawing, Rect, String
from reportlab.graphics.charts.piecharts import Pie
from reportlab.graphics.charts.barcharts import BarChart
from reportlab.graphics.charts.linecharts import LineChart
from typing import List, Dict
import sys

def create_report(filename: str, data: Dict) -> None:
    """
    Create a PDF report from the given data.

    Args:
    filename (str): The filename of the report.
    data (Dict): A dictionary containing the data for the report.
    """
    # Create the PDF file
    pdf_file = SimpleDocTemplate(filename, pagesize=letter)

    # Create the styles
    styles = getSampleStyleSheet()
    style_normal = ParagraphStyle(
        name='Normal',
        fontSize=12,
        leading=14,
        alignment=TA_LEFT,
        textColor=black,
        backgroundColor=white,
    )
    style_header = ParagraphStyle(
        name='Header',
        fontSize=18,
        leading=20,
        alignment=TA_CENTER,
        textColor=black,
        backgroundColor=white,
    )

    # Create the header and footer
    def header_footer(canvas, doc):
        # Header
        canvas.saveState()
        canvas.setFont("Helvetica", 12)
        canvas.drawString(1 * inch, 10.5 * inch, "Header")
        canvas.restoreState()

        # Footer
        canvas.saveState()
        canvas.setFont("Helvetica", 12)
        canvas.drawString(1 * inch, 0.5 * inch, "Footer")
        canvas.restoreState()

    # Create the table
    def create_table(data: List[List[str]]) -> Table:
        """
        Create a table from the given data.

        Args:
        data (List[List[str]]): A 2D list containing the data for the table.

        Returns:
        Table: The created table.
        """
        table = Table(data)
        table_style = TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.5, black),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 12),
        ])
        table.setStyle(table_style)
        return table

    # Create the chart
    def create_chart(data: List[int], chart_type: str) -> Drawing:
        """
        Create a chart from the given data.

        Args:
        data (List[int]): A list containing the data for the chart.
        chart_type (str): The type of chart to create (bar, line, pie).

        Returns:
        Drawing: The created chart.
        """
        if chart_type == "bar":
            chart = BarChart()
            chart.data = data
        elif chart_type == "line":
            chart = LineChart()
            chart.data = data
        elif chart_type == "pie":
            chart = Pie()
            chart.data = data
        else:
            raise ValueError("Invalid chart type")

        drawing = Drawing(400, 200)
        drawing.add(chart)
        return drawing

    # Create the report elements
    elements = []
    elements.append(Paragraph("Report", style_header))
    elements.append(Spacer(1, 12))

    # Add tables
    tables_data = data.get("tables", [])
    for table_data in tables_data:
        table = create_table(table_data)
        elements.append(table)
        elements.append(Spacer(1, 12))

    # Add charts
    charts_data = data.get("charts", [])
    for chart_data in charts_data:
        chart_type = chart_data.get("type", "")
        chart_data_values = chart_data.get("data", [])
        chart = create_chart(chart_data_values, chart_type)
        elements.append(chart)
        elements.append(Spacer(1, 12))

    # Build the PDF
    try:
        pdf_file.build(elements, onFirstPage=header_footer, onLaterPages=header_footer)
    except Exception as e:
        print(f"An error occurred: {e}")
        sys.exit(1)

# Example usage:
if __name__ == "__main__":
    data = {
        "tables": [
            ["Column 1", "Column 2", "Column 3"],
            ["Row 1, Column 1", "Row 1, Column 2", "Row 1, Column 3"],
            ["Row 2, Column 1", "Row 2, Column 2", "Row 2, Column 3"],
        ],
        "charts": [
            {"type": "bar", "data": [10, 20, 30]},
            {"type": "line", "data": [40, 50, 60]},
            {"type": "pie", "data": [70, 80, 90]},
        ],
    }
    create_report("report.pdf", data)