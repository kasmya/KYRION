from typing import List, Tuple, Dict
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch, mm
from reportlab.pdfgen import canvas
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.graphics.charts.lineplots import LinePlot
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.charts.piecharts import PieChart
from reportlab.graphics.shapes import Drawing
from io import BytesIO
import logging

logging.basicConfig(level=logging.INFO)

class PDFReport:
    def __init__(self, filename: str):
        self.filename = filename
        self.styles = self._create_styles()
        self.doc = SimpleDocTemplate(filename, pagesize=A4)
        self.story = []

    def _create_styles(self) -> Dict[str, ParagraphStyle]:
        styles = {
            'header': ParagraphStyle(
                name='header',
                fontSize=12,
                leading=14,
                alignment=1,
                textColor=colors.black,
                backColor=colors.lightgrey,
                borderPadding=1,
                borderColor=colors.black,
                borderWidth=0.5,
            ),
            'footer': ParagraphStyle(
                name='footer',
                fontSize=10,
                leading=12,
                alignment=1,
                textColor=colors.black,
                backColor=colors.lightgrey,
                borderPadding=1,
                borderColor=colors.black,
                borderWidth=0.5,
            ),
            'table_header': ParagraphStyle(
                name='table_header',
                fontSize=10,
                leading=12,
                alignment=1,
                textColor=colors.black,
                backColor=colors.lightgrey,
                borderPadding=1,
                borderColor=colors.black,
                borderWidth=0.5,
            ),
            'table_data': ParagraphStyle(
                name='table_data',
                fontSize=10,
                leading=12,
                alignment=0,
                textColor=colors.black,
            ),
        }
        return styles

    def add_header(self, text: str) -> None:
        self.story.append(Paragraph(text, self.styles['header']))
        self.story.append(Spacer(1, 12))

    def add_footer(self, text: str) -> None:
        self.story.append(Spacer(1, 12))
        self.story.append(Paragraph(text, self.styles['footer']))

    def add_table(self, data: List[List[str]], headers: List[str]) -> None:
        table = Table(data, style=[
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
        ])
        for i, header in enumerate(headers):
            table.setStyle(TableStyle([
                ('ALIGN', (i, 1), (i, -1), 'LEFT'),
            ]))
        self.story.append(table)

    def add_line_chart(self, data: List[Tuple[str, int]]) -> None:
        drawing = Drawing(400, 200)
        line_plot = LinePlot()
        line_plot.data = [list(map(lambda x: x[1], data))]
        line_plot.x = 50
        line_plot.y = 50
        line_plot.height = 125
        line_plot.width = 300
        line_plot.joinedLines = 1
        line_plot.lines.symbol = None
        line_plot.lineWidth = 2
        line_plot.barLabels.timestamp = 0
        line_plot.barLabels.fontSize = 8
        line_plot.barLabels.fontName = 'Helvetica'
        line_plot.barLabels.fillColor = colors.black
        line_plot.barLabels.dy = 0
        line_plot.barLabels.dx = -15
        line_plot.categoryAxis.labels.rightPadding = 15
        line_plot.valueAxis.valueMin = 0
        drawing.add(line_plot)
        self.story.append(drawing)

    def add_bar_chart(self, data: List[Tuple[str, int]]) -> None:
        drawing = Drawing(400, 200)
        bar_chart = VerticalBarChart()
        bar_chart.data = [list(map(lambda x: x[1], data))]
        bar_chart.x = 50
        bar_chart.y = 50
        bar_chart.height = 125
        bar_chart.width = 300
        bar_chart.barSpacing = 1
        bar_chart.barWidth = 20
        bar_chart.barColors = [colors.blue]
        bar_chart.valueAxis.valueMin = 0
        drawing.add(bar_chart)
        self.story.append(drawing)

    def add_pie_chart(self, data: List[Tuple[str, int]]) -> None:
        drawing = Drawing(200, 200)
        pie_chart = PieChart()
        pie_chart.data = list(map(lambda x: x[1], data))
        pie_chart.labels = list(map(lambda x: x[0], data))
        pie_chart.x = 50
        pie_chart.y = 50
        pie_chart.width = 150
        pie_chart.height = 150
        pie_chart.slices.strokeWidth = 1
        pie_chart.slices.strokeColor = colors.black
        pie_chart.slices.fontName = 'Helvetica'
        pie_chart.slices.fontSize = 8
        pie_chart.slices.popout = 5
        pie_chart.simpleLabels = 0
        drawing.add(pie_chart)
        self.story.append(drawing)

    def save(self) -> None:
        self.doc.build(self.story)

def main():
    report = PDFReport('report.pdf')
    report.add_header('PDF Report')
    report.add_table([['Column 1', 'Column 2'], ['Data 1', 'Data 2']], ['Column 1', 'Column 2'])
    report.add_line_chart([('Jan', 10), ('Feb', 15), ('Mar', 20)])
    report.add_bar_chart([('Jan', 10), ('Feb', 15), ('Mar', 20)])
    report.add_pie_chart([('Jan', 10), ('Feb', 15), ('Mar', 20)])
    report.add_footer('Page 1')
    report.save()

if __name__ == '__main__':
    main()