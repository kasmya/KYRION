import os
import logging
from typing import List, Optional, Tuple, Union
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    PageBreak,
    Flowable,
)
from reportlab.graphics.shapes import Drawing
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.charts.linecharts import LineChart
from reportlab.graphics.charts.piecharts import Pie
from reportlab.pdfgen import canvas

logger = logging.getLogger(__name__)


class PDFReportGenerator:
    """
    A flexible PDF report generator with header/footer, tables, and charts.
    Supports multi-page documents with automatic page breaks.
    """

    def __init__(
        self,
        filename: str,
        title: str = "Report",
        page_size: Tuple[float, float] = A4,
        left_margin: float = 20 * mm,
        right_margin: float = 20 * mm,
        top_margin: float = 20 * mm,
        bottom_margin: float = 18 * mm,
    ) -> None:
        """
        Initialize the PDF generator.

        Args:
            filename: Output PDF file path.
            title: Document title (displayed in header if not overridden).
            page_size: Tuple (width, height) in points.
            left_margin: Left margin in points.
            right_margin: Right margin in points.
            top_margin: Top margin in points.
            bottom_margin: Bottom margin in points.

        Raises:
            ValueError: If filename is empty or invalid.
        """
        if not filename:
            raise ValueError("Filename must not be empty.")
        self.filename = filename
        self.title = self._sanitize_text(title)
        self.page_size = page_size

        # Margins
        self.left_margin = left_margin
        self.right_margin = right_margin
        self.top_margin = top_margin
        self.bottom_margin = bottom_margin

        # Header and footer content
        self.header_text: Optional[str] = None
        self.footer_text: Optional[str] = None

        # Flowable container
        self.flowables: List[Flowable] = []

        # Styles
        self.styles = getSampleStyleSheet()
        self.title_style = self.styles["Title"]
        self.heading_style = self.styles["Heading2"]
        self.normal_style = self.styles["Normal"]

        # Document builder
        self.doc = SimpleDocTemplate(
            filename,
            pagesize=page_size,
            leftMargin=left_margin,
            rightMargin=right_margin,
            topMargin=top_margin,
            bottomMargin=bottom_margin,
        )

    def _sanitize_text(self, text: str) -> str:
        """
        Remove control characters that might cause PDF injection or rendering issues.

        Args:
            text: Input string.

        Returns:
            Sanitized string.
        """
        if not isinstance(text, str):
            text = str(text)
        # Remove all characters below 0x20 except tab, newline, carriage return
        sanitized = "".join(ch for ch in text if ord(ch) >= 0x20 or ch in ('\t', '\n', '\r'))
        return sanitized

    def _add_header_footer(self, canvas_obj: canvas.Canvas, doc: SimpleDocTemplate) -> None:
        """
        Callback function to draw header and footer on each page.

        Args:
            canvas_obj: ReportLab canvas.
            doc: Document object.
        """
        canvas_obj.saveState()
        # Header
        header = self.header_text if self.header_text else self.title
        if header:
            canvas_obj.setFont("Helvetica-Bold", 12)
            canvas_obj.drawCentredString(self.page_size[0] / 2, self.page_size[1] - 15 * mm,
                                         self._sanitize_text(header))

        # Footer
        footer = self.footer_text if self.footer_text else f"Page {doc.page}"
        if footer:
            canvas_obj.setFont("Helvetica", 9)
            canvas_obj.drawCentredString(self.page_size[0] / 2, 12 * mm,
                                         self._sanitize_text(footer))
        canvas_obj.restoreState()

    def set_header(self, text: str) -> None:
        """
        Set custom header text displayed on every page.

        Args:
            text: Header text.
        """
        self.header_text = self._sanitize_text(text)

    def set_footer(self, text: str) -> None:
        """
        Set custom footer text displayed on every page.

        Args:
            text: Footer text.
        """
        self.footer_text = self._sanitize_text(text)

    def add_paragraph(self, text: str, style: str = "Normal") -> None:
        """
        Add a paragraph of text.

        Args:
            text: Content.
            style: Style name from sample stylesheet ("Normal", "Heading2", "Title", etc.).
        """
        if style in self.styles:
            para = Paragraph(self._sanitize_text(text), self.styles[style])
        else:
            para = Paragraph(self._sanitize_text(text), self.normal_style)
        self.flowables.append(para)
        self.flowables.append(Spacer(1, 6 * mm))

    def add_table(
        self,
        data: List[List[Union[str, int, float]]],
        col_widths: Optional[List[float]] = None,
        header_first_row: bool = True,
        repeat_rows: int = 1,
    ) -> None:
        """
        Add a table to the report.

        Args:
            data: 2D list of table data.
            col_widths: List of column widths (in points). If None, automatic sizing.
            header_first_row: If True, first row is styled as header.
            repeat_rows: Number of rows to repeat at top when table spans pages.

        Raises:
            ValueError: If data is empty or rows have inconsistent column counts.
        """
        if not data or not all(isinstance(row, list) for row in data):
            raise ValueError("Data must be a non-empty list of lists.")
        row_lengths = {len(row) for row in data}
        if len(row_lengths) > 1:
            raise ValueError("All rows must have the same number of columns.")

        # Sanitize all text entries
        sanitized_data = []
        for row in data:
            sanitized_row = [
                self._sanitize_text(str(cell)) if isinstance(cell, str) else cell
                for cell in row
            ]
            sanitized_data.append(sanitized_row)

        table = Table(sanitized_data, colWidths=col_widths, repeatRows=repeat_rows)

        # Basic style
        style_cmds = [
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('PADDING', (0, 0), (-1, -1), 4),
        ]
        if header_first_row:
            style_cmds += [
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#D9E1F2')),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
            ]
        table.setStyle(TableStyle(style_cmds))
        self.flowables.append(Spacer(1, 4 * mm))
        self.flowables.append(table)
        self.flowables.append(Spacer(1, 6 * mm))

    def _create_drawing_chart(self, width: float = 400, height: float = 250) -> Drawing:
        """Create an empty Drawing object with standard size."""
        return Drawing(width, height)

    def add_bar_chart(
        self,
        data: List[float],
        labels: List[str],
        title: str = "",
        bar_color: colors.Color = colors.HexColor('#4F81BD'),
        width: float = 450,
        height: float = 250,
    ) -> None:
        """
        Add a vertical bar chart.

        Args:
            data: Numeric values for bars.
            labels: Corresponding category labels.
            title: Optional chart title.
            bar_color: Color for the bars.
            width: Chart width in points.
            height: Chart height in points.

        Raises:
            ValueError: If data and labels have different lengths or are empty.
        """
        if len(data) != len(labels):
            raise ValueError("Data and labels must have the same length.")
        if not data:
            raise ValueError("Data must not be empty.")

        drawing = self._create_drawing_chart(width, height)
        bc = VerticalBarChart()
        bc.x = 50
        bc.y = 50
        bc.width = drawing.width - 100
        bc.height = drawing.height - 80
        bc.data = [data]
        bc.categoryAxis.categoryNames = labels
        bc.categoryAxis.labels.fontSize = 8
        bc.valueAxis.valueMin = 0
        bc.valueAxis.valueStep = 1
        bc.bars[0].fillColor = bar_color
        bc.barWidth = 12

        # Add title
        if title:
            from reportlab.graphics.widgets.markers import makeMarker
            from reportlab.graphics import renderPDF
            from reportlab.platypus.flowables import Flowable
            # Using a simple label approach: create a string and place it
            # But easier: we can add a Paragraph above the chart.
            self.flowables.append(Paragraph(self._sanitize_text(title), self.heading_style))

        self.flowables.append(drawing)
        self.flowables.append(Spacer(1, 6 * mm))

    def add_line_chart(
        self,
        data_series: List[List[float]],
        labels: List[str],
        series_names: Optional[List[str]] = None,
        title: str = "",
        width: float = 450,
        height: float = 250,
    ) -> None:
        """
        Add a line chart with one or more series.

        Args:
            data_series: List of numeric series (each a list of values).
            labels: Category labels for the x-axis.
            series_names: Optional names for the legend.
            title: Optional chart title.
            width: Chart width.
            height: Chart height.

        Raises:
            ValueError: If any series length mismatches labels or data is empty.
        """
        if not data_series:
            raise ValueError("At least one data series is required.")
        for series in data_series:
            if len(series) != len(labels):
                raise ValueError("Each series must have the same length as labels.")
        if series_names and len(series_names) != len(data_series):
            raise ValueError("Number of series names must match number of series.")
        if not labels:
            raise ValueError("Labels must not be empty.")

        drawing = self._create_drawing_chart(width, height)
        lc = LineChart()
        lc.x = 50
        lc.y = 50
        lc.width = drawing.width - 100
        lc.height = drawing.height - 80
        lc.data = data_series
        lc.categoryAxis.categoryNames = labels
        lc.categoryAxis.labels.fontSize = 8
        lc.valueAxis.valueMin = 0
        # Style lines
        colors_list = [colors.HexColor('#4F81BD'), colors.HexColor('#C0504D'),
                       colors.HexColor('#9BBB59'), colors.HexColor('#8064A2')]
        for i in range(len(data_series)):
            lc.lines[i].strokeColor = colors_list[i % len(colors_list)]
            lc.lines[i].strokeWidth = 2

        if title:
            self.flowables.append(Paragraph(self._sanitize_text(title), self.heading_style))

        self.flowables.append(drawing)
        self.flowables.append(Spacer(1, 6 * mm))

    def add_pie_chart(
        self,
        data: List[float],
        labels: List[str],
        title: str = "",
        width: float = 400,
        height: float = 300,
    ) -> None:
        """
        Add a pie chart.

        Args:
            data: Numeric slice values.
            labels: Corresponding slice labels.
            title: Optional chart title.
            width: Chart width.
            height: Chart height.

        Raises:
            ValueError: If data and labels lengths differ or data is empty.
        """
        if len(data) != len(labels):
            raise ValueError("Data and labels must have the same length.")
        if not data:
            raise ValueError("Data must not be empty.")

        drawing = self._create_drawing_chart(width, height)
        pie = Pie()
        pie.x = 100
        pie.y = 40
        pie.width = drawing.width - 200
        pie.height = drawing.height - 100
        pie.data = data
        pie.labels = labels
        pie.slices.strokeWidth = 0.5
        # Coloring
        pie_colors = [colors.HexColor('#4F81BD'), colors.HexColor('#C0504D'),
                      colors.HexColor('#9BBB59'), colors.HexColor('#8064A2'),
                      colors.HexColor('#F79646'), colors.HexColor('#FFC000')]
        for i in range(len(data)):
            pie.slices[i].fillColor = pie_colors[i % len(pie_colors)]

        if title:
            self.flowables.append(Paragraph(self._sanitize_text(title), self.heading_style))

        self.flowables.append(drawing)
        self.flowables.append(Spacer(1, 6 * mm))

    def add_page_break(self) -> None:
        """Insert a page break."""
        self.flowables.append(PageBreak())

    def generate(self) -> str:
        """
        Build and save the PDF report.

        Returns:
            The output filename.

        Raises:
            IOError: If writing fails.
        """
        try:
            # Ensure output directory exists
            output_dir = os.path.dirname(self.filename)
            if output_dir and not os.path.exists(output_dir):
                os.makedirs(output_dir, exist_ok=True)

            self.doc.build(
                self.flowables,
                onFirstPage=self._add_header_footer,
                onLaterPages=self._add_header_footer,
            )
            logger.info("PDF generated successfully: %s", self.filename)
            return self.filename
        except Exception as e:
            logger.error("Failed to generate PDF: %s", str(e))
            raise IOError(f"Could not write PDF: {e}") from e


# Example usage (commented out to keep code concise)
# if __name__ == "__main__":
#     reporter = PDFReportGenerator("report.pdf", title="Sales Report")
#     reporter.add_paragraph("This is an example report with tables and charts.")
#     reporter.set_header("Confidential")
#     reporter.set_footer("Page ")
#     data = [["Item", "Q1", "Q2", "Q3", "Q4"],
#             ["Apples", 120, 150, 110, 130],
#             ["Bananas", 80, 90, 95, 85]]
#     reporter.add_table(data)
#     reporter.add_bar_chart([10, 20, 15], ["A", "B", "C"], "Bar Example")
#     reporter.add_line_chart([[5, 10, 8], [3, 7, 9]], ["Jan", "Feb", "Mar"],
#                             series_names=["Product X", "Product Y"])
#     reporter.add_pie_chart([30, 40, 30], ["Type 1", "Type 2", "Type 3"], "Pie Example")
#     reporter.generate()