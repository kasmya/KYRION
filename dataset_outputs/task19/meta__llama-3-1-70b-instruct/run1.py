from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.enums import TA_CENTER
from reportlab.lib import colors
from reportlab.graphics.shapes import Drawing
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.charts.linecharts import HorizontalLineChart
from reportlab.graphics.charts.piecharts import Pie
from reportlab.graphics.charts.legends import Legend
from io import BytesIO
from typing import List, Tuple, Dict

class PDFReportGenerator:
    """
    A class used to generate PDF reports with the following features:
    - header and footer support
    - table generation with data
    - chart insertion (bar, line, pie)
    - multi-page support

    Attributes:
    ----------
    data : List[Tuple[str, str, str]]
        The data to be included in the report.
    styles : Dict[str, ParagraphStyle]
        The styles used for the report.
    """

    def __init__(self, data: List[Tuple[str, str, str]]) -> None:
        """
        Parameters:
        ----------
        data : List[Tuple[str, str, str]]
            The data to be included in the report.
        """
        self.data = data
        self.styles = getSampleStyleSheet()
        self.styles.add(ParagraphStyle(
            name='Title',
            fontSize=18,
            leading=22,
            alignment=TA_CENTER,
            textColor=colors.black,
            backColor=colors.white,
            textAnchor='normal'
        ))

    def _create_header_footer(self, canvas: canvas.Canvas, doc: SimpleDocTemplate) -> None:
        """
        Creates the header and footer for the report.

        Parameters:
        ----------
        canvas : canvas.Canvas
            The canvas used for drawing.
        doc : SimpleDocTemplate
            The document template.
        """
        canvas.saveState()
        canvas.setFont('Helvetica', 10)
        canvas.drawString(50 * mm, 25 * mm, f"Page {doc.page}")
        canvas.restoreState()

    def _create_table(self, story: List[object]) -> Table:
        """
        Creates a table from the data.

        Parameters:
        ----------
        story : List[object]
            The list of paragraphs and tables to be included in the report.

        Returns:
        -------
        Table
            The created table.
        """
        table_data = [list(x) for x in self.data]
        table = Table(table_data, style=TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
            ('BOX', (0, 0), (-1, -1), 0.5, colors.black),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
        ]))
        story.append(table)
        return table

    def _create_bar_chart(self, story: List[object]) -> None:
        """
        Creates a bar chart.

        Parameters:
        ----------
        story : List[object]
            The list of paragraphs and tables to be included in the report.
        """
        drawing = Drawing(400, 200)
        chart = VerticalBarChart()
        chart.x = 50
        chart.y = 50
        chart.height = 125
        chart.width = 300
        chart.data = [[10, 20, 30, 40, 50]]
        chart.valueAxis.valueMin = 0
        chart.valueAxis.valueMax = 60
        chart.valueAxis.valueStep = 10
        chart.categoryAxis.labels.boxAnchor = 'n'
        drawing.add(chart)
        story.append(drawing)

    def _create_line_chart(self, story: List[object]) -> None:
        """
        Creates a line chart.

        Parameters:
        ----------
        story : List[object]
            The list of paragraphs and tables to be included in the report.
        """
        drawing = Drawing(400, 200)
        chart = HorizontalLineChart()
        chart.x = 50
        chart.y = 50
        chart.height = 125
        chart.width = 300
        chart.data = [[10, 20, 30, 40, 50]]
        chart.valueAxis.valueMin = 0
        chart.valueAxis.valueMax = 60
        chart.valueAxis.valueStep = 10
        chart.categoryAxis.labels.boxAnchor = 'n'
        drawing.add(chart)
        story.append(drawing)

    def _create_pie_chart(self, story: List[object]) -> None:
        """
        Creates a pie chart.

        Parameters:
        ----------
        story : List[object]
            The list of paragraphs and tables to be included in the report.
        """
        drawing = Drawing(400, 200)
        pie = Pie()
        pie.x = 150
        pie.y = 100
        pie.width = 100
        pie.height = 100
        pie.data = [10, 20, 30, 40]
        pie.labels = ['A', 'B', 'C', 'D']
        drawing.add(pie)
        story.append(drawing)

    def generate_report(self, filename: str) -> None:
        """
        Generates the report.

        Parameters:
        ----------
        filename : str
            The filename of the report.
        """
        doc = SimpleDocTemplate(filename, pagesize=letter)
        story = [Paragraph('Report', self.styles['Title'])]
        story.append(Spacer(1, 20 * mm))
        self._create_table(story)
        story.append(Spacer(1, 20 * mm))
        self._create_bar_chart(story)
        story.append(Spacer(1, 20 * mm))
        self._create_line_chart(story)
        story.append(Spacer(1, 20 * mm))
        self._create_pie_chart(story)
        doc.build(story, onFirstPage=self._create_header_footer, onLaterPages=self._create_header_footer)

# Example usage
if __name__ == "__main__":
    data = [('Column 1', 'Column 2', 'Column 3'), ('Value 1', 'Value 2', 'Value 3'), ('Value 4', 'Value 5', 'Value 6')]
    generator = PDFReportGenerator(data)
    generator.generate_report('report.pdf')