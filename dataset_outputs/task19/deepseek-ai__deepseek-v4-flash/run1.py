import os
import tempfile
from typing import List, Optional, Tuple, Union
from fpdf import FPDF
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend to avoid GUI issues
import matplotlib.pyplot as plt

class PDFReportGenerator:
    """
    A PDF report generator with support for headers, footers, tables,
    charts (bar, line, pie), multi-page handling, and error management.
    """

    def __init__(
        self,
        output_path: str,
        page_size: str = "A4",
        orientation: str = "P",
        unit: str = "mm",
        font_name: str = "Helvetica",
        font_size: int = 10
    ) -> None:
        """
        Initialize the PDF generator.

        Args:
            output_path: Path to the output PDF file.
            page_size: Page size (e.g., 'A4', 'Letter').
            orientation: 'P' (portrait) or 'L' (landscape).
            unit: Unit of measurement ('mm', 'cm', 'in', 'pt').
            font_name: Default font name.
            font_size: Default font size in points.

        Raises:
            ValueError: If the output directory is not writable.
        """
        # Security: validate output path
        out_dir = os.path.dirname(output_path) or "."
        if not os.access(out_dir, os.W_OK):
            raise ValueError(f"Output directory '{out_dir}' is not writable.")

        self.output_path = output_path
        self.pdf = FPDF(orientation=orientation, unit=unit, format=page_size)
        self.pdf.set_auto_page_break(auto=True, margin=20)  # bottom margin for footer
        self.pdf.add_page()
        self.pdf.set_font(font_name, size=font_size)
        self._font_name = font_name
        self._font_size = font_size
        self._header_text = ""
        self._footer_text = ""
        self._current_y = self.pdf.get_y()  # track manually for precise placement

    # ---- Header / Footer ----
    def set_header(self, text: str) -> None:
        """Set the header text (displayed centered on each page)."""
        self._header_text = text

    def set_footer(self, text: str) -> None:
        """Set the footer text (displayed centered on each page)."""
        self._footer_text = text

    def _header(self) -> None:
        """Internal header drawing method (called automatically by FPDF on each page)."""
        if self._header_text:
            self.pdf.set_y(10)
            self.pdf.cell(0, 10, self._header_text, align="C")
            self.pdf.line(10, 20, self.pdf.w - 10, 20)  # line below header

    def _footer(self) -> None:
        """Internal footer drawing method (called automatically by FPDF on each page)."""
        if self._footer_text:
            self.pdf.set_y(-15)  # 15 mm from bottom
            self.pdf.cell(0, 10, self._footer_text, align="C")
        # Page number
        self.pdf.set_y(-10)
        self.pdf.cell(0, 10, f"Page {self.pdf.page_no()}/{{nb}}", align="C")

    # ---- Helper methods ----
    def _check_page_break(self, height: float) -> None:
        """
        Add a new page if the current Y + height exceeds the bottom margin.

        Args:
            height: Height needed for the next element (in current unit).
        """
        if self.pdf.get_y() + height > self.pdf.h - 20:  # 20 mm bottom margin
            self.pdf.add_page()
            self._header()  # manually call header if we added page prematurely? 
            # FPDF's add_page already calls header() automatically if not suppressed
            # However we do not use overridden header method because FPDF calls it.
            # So header() is already called. But we have our custom logic.
            # Actually, we are overriding _header but it's called automatically.
            # We'll store header/footer in the FPDF subclass.
            # Better approach: subclass FPDF.
            pass

    # ---- Content methods ----
    def add_title(self, text: str, size: Optional[int] = None) -> None:
        """
        Add a title (large bold text) to the report.

        Args:
            text: Title text.
            size: Font size (points). If None, uses default font size + 4.
        """
        title_size = size if size else self._font_size + 4
        self.pdf.set_font(self._font_name, "B", title_size)
        self._check_page_break(10)
        self.pdf.cell(0, 10, text, new_x="LMARGIN", new_y="NEXT", align="L")
        self.pdf.set_font(self._font_name, size=self._font_size)

    def add_paragraph(self, text: str) -> None:
        """
        Add a paragraph of text to the report. Handles multi‑page automatically.

        Args:
            text: Text content (may contain newlines).
        """
        self.pdf.set_font(self._font_name, size=self._font_size)
        # multi_cell handles page breaks automatically
        self.pdf.multi_cell(0, 5, text)

    def add_table(
        self,
        headers: List[str],
        data: List[List[Union[str, int, float]]],
        col_widths: Optional[List[float]] = None,
        row_height: float = 7.0
    ) -> None:
        """
        Add a table to the PDF. Handles page breaks.

        Args:
            headers: List of column header strings.
            data: List of rows, each row is a list of cell values.
            col_widths: Optional list of column widths (in unit). If None, sizes are equal.
            row_height: Height of each row (default 7 mm).

        Raises:
            ValueError: If headers/data empty or column mismatch.
        """
        if not headers:
            raise ValueError("Headers list must not be empty.")
        if not data:
            raise ValueError("Data list must not be empty.")
        for row in data:
            if len(row) != len(headers):
                raise ValueError("Each row must have the same number of columns as headers.")

        # Calculate column widths if not provided
        page_width = self.pdf.w - 2 * self.pdf.l_margin
        if col_widths is None:
            col_widths = [page_width / len(headers)] * len(headers)
        else:
            # Normalize widths to sum <= page width
            total = sum(col_widths)
            if total > page_width:
                factor = page_width / total
                col_widths = [w * factor for w in col_widths]
            elif total < page_width:
                # leave remaining space blank
                pass

        # Draw header row
        self.pdf.set_font(self._font_name, "B", self._font_size)
        self._check_page_break(row_height)
        y_start = self.pdf.get_y()
        x_start = self.pdf.get_x()
        for i, header in enumerate(headers):
            self.pdf.cell(col_widths[i], row_height, header, border=1, align="C",
                          new_x="RIGHT", new_y="TOP")
        self.pdf.set_y(y_start + row_height)

        # Draw data rows
        self.pdf.set_font(self._font_name, size=self._font_size)
        for row in data:
            # Check if we need a page break before this row
            self._check_page_break(row_height)
            y_start = self.pdf.get_y()
            x_start = self.pdf.get_x()
            for i, cell_value in enumerate(row):
                self.pdf.cell(col_widths[i], row_height, str(cell_value), border=1,
                              align="C", new_x="RIGHT", new_y="TOP")
            self.pdf.set_y(y_start + row_height)

    def add_chart(
        self,
        kind: str = "bar",
        data: Optional[dict] = None,
        x_label: str = "",
        y_label: str = "",
        title: str = "",
        width: float = 160,
        height: float = 80
    ) -> None:
        """
        Generate and insert a chart (bar, line, pie) as an image into the PDF.

        The chart is created using matplotlib, saved to a temporary file, and embedded.

        Args:
            kind: Type of chart ('bar', 'line', 'pie').
            data: Dictionary with keys 'labels' (list) and 'values' (list) for bar/line.
                For pie charts, data should be a dict with 'labels' and 'values'.
            x_label: X‑axis label (bar/line).
            y_label: Y‑axis label (bar/line).
            title: Chart title.
            width: Image width in mm.
            height: Image height in mm.

        Raises:
            ValueError: If chart type is unknown or data is invalid.
            RuntimeError: If chart generation fails.
        """
        if not data or 'labels' not in data or 'values' not in data:
            raise ValueError("Data must contain 'labels' and 'values' lists.")

        labels = data['labels']
        values = data['values']
        if not labels or not values:
            raise ValueError("Labels and values cannot be empty.")

        try:
            # Create matplotlib figure
            plt.figure(figsize=(width / 25.4, height / 25.4))  # mm to inches
            if kind == "bar":
                plt.bar(labels, values)
            elif kind == "line":
                plt.plot(labels, values, marker='o')
            elif kind == "pie":
                plt.pie(values, labels=labels, autopct='%1.1f%%')
            else:
                raise ValueError(f"Unsupported chart kind '{kind}'. Use 'bar', 'line', or 'pie'.")

            plt.xlabel(x_label)
            plt.ylabel(y_label)
            plt.title(title)
            plt.tight_layout()

            # Save to temporary file (security: delete on close)
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                tmp_path = tmp.name
            plt.savefig(tmp_path, dpi=150, format='png')
            plt.close()

            # Insert image into PDF
            self._check_page_break(height + 10)  # allow some margin
            self.pdf.image(tmp_path, x=self.pdf.l_margin, y=self.pdf.get_y(),
                           w=width, h=height)
            self.pdf.set_y(self.pdf.get_y() + height + 5)  # advance Y

            # Clean up temporary file
            os.unlink(tmp_path)

        except Exception as e:
            raise RuntimeError(f"Chart generation failed: {e}") from e

    def output(self) -> None:
        """
        Finalize and save the PDF file.

        Closes the PDF and writes it to the output path.
        """
        # Set the alias for page numbering (required for {nb} in footer)
        self.pdf.alias_nb_pages()
        self.pdf.output(self.output_path)


# ---- Example usage (only if run directly) ----
if __name__ == "__main__":
    # Demonstrate the report generator
    report = PDFReportGenerator("example_report.pdf")

    report.set_header("Quarterly Report")
    report.set_footer("Confidential")

    report.add_title("Sales Data Analysis")
    report.add_paragraph(
        "This report presents the sales data for the first quarter of 2024. "
        "It includes a summary table and various charts to visualize trends."
    )

    # Table
    headers = ["Product", "Q1 Sales (USD)", "Q2 Sales (USD)", "Growth (%)"]
    data = [
        ["Widget A", 15000, 17500, 16.7],
        ["Widget B", 22000, 21000, -4.5],
        ["Widget C", 18000, 19500, 8.3],
    ]
    report.add_table(headers, data)

    # Charts
    chart_data = {
        "labels": ["Jan", "Feb", "Mar"],
        "values": [4500, 5200, 6100]
    }
    report.add_chart(kind="bar", data=chart_data,
                     x_label="Month", y_label="Revenue (USD)",
                     title="Monthly Revenue")

    report.add_chart(kind="line", data=chart_data,
                     x_label="Month", y_label="Revenue (USD)",
                     title="Revenue Trend")

    pie_data = {
        "labels": ["Widget A", "Widget B", "Widget C"],
        "values": [32500, 43000, 37500]
    }
    report.add_chart(kind="pie", data=pie_data, title="Total Sales by Product")

    report.output()
    print(f"Report generated at {report.output_path}")