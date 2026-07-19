"""
Task 19: Enterprise Corporate Document and Report Assembly Factory
Features: Precise tabular canvas grids, corporate colour palette, automated multi-page footer calculation scripts.
Requires: reportlab
"""

import os
import logging
from datetime import datetime
from typing import List, Dict, Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfgen import canvas

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class AutomatedNumberedCanvas(canvas.Canvas):
    """Dynamic two-pass document script used to inject page numbers after structural layouts freeze."""
    
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._saved_page_states: List[Dict[str, Any]] = []

    def showPage(self) -> None:
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self) -> None:
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, total_pages_count: int) -> None:
        """Renders header rules and bottom footers onto the active canvas sheet view blocks."""
        self.saveState()
        self.setFont("Helvetica", 9)
        self.setFillColor(colors.HexColor("#4A5568"))
        
        # Header Element Lines Setup
        self.drawString(54, 750, "Internal Operations Framework Report Summary")
        self.setStrokeColor(colors.HexColor("#CBD5E1"))
        self.setLineWidth(0.5)
        self.line(54, 742, 558, 742)

        # Footer Context Injection
        footer_string = f"Page {self._pageNumber} of {total_pages_count}"
        self.drawRightString(558, 40, footer_string)
        self.drawString(54, 40, f"Generated On: {datetime.now().strftime('%Y-%m-%d')} | Classified - Internal Corporate Review")
        self.restoreState()

class DocumentAssemblyFactory:
    """Compiles tabular data records arrays into highly structured corporate print files."""

    @staticmethod
    def generate_pdf_report(output_filename: str, report_title: str, dataset: List[Dict[str, Any]]) -> None:
        """Transforms structural dictionaries records into flowing story layouts files."""
        logger.info(f"Initializing ReportLab flowable framework template: {output_filename}")
        
        # Set boundaries coordinates margin rules layouts
        document_wrapper = SimpleDocTemplate(
            output_filename,
            pagesize=letter,
            leftMargin=54,
            rightMargin=54,
            topMargin=72,
            bottomMargin=72
        )

        style_sheet = getSampleStyleSheet()
        
        # Custom Corporate Style Sheet Layout Directives Override
        title_style = ParagraphStyle(
            'CorporateTitle',
            parent=style_sheet['Heading1'],
            fontName='Helvetica-Bold',
            fontSize=24,
            leading=28,
            textColor=colors.HexColor("#1E3A8A"),
            spaceAfter=15
        )
        
        body_style = ParagraphStyle(
            'CorporateBody',
            parent=style_sheet['Normal'],
            fontName='Helvetica',
            fontSize=10,
            leading=14,
            textColor=colors.HexColor("#334155"),
            spaceAfter=10
        )

        story_flowables = []

        # Add Header Title Text
        story_flowables.append(Paragraph(report_title, title_style))
        story_flowables.append(Paragraph(
            "This document compiles performance verification analytics across operational department units.", 
            body_style
        ))
        story_flowables.append(Spacer(1, 15))

        # Build Financial Audit Table Element Layers
        table_headers = [Paragraph("<b>Department Node ID</b>", body_style), 
                         Paragraph("<b>Lead Engineer</b>", body_style), 
                         Paragraph("<b>Quarter Efficiency Weight</b>", body_style)]
        
        structural_table_rows = [table_headers]
        for data_row in dataset:
            structural_table_rows.append([
                Paragraph(str(data_row.get("dept_id", "N/A")), body_style),
                Paragraph(str(data_row.get("manager", "N/A")), body_style),
                Paragraph(str(data_row.get("efficiency", "0.00%")), body_style)
            ])

        # Column scaling grid alignments vector parameters values
        metrics_table = Table(structural_table_rows, colWidths=[120, 220, 160])
        
        # Style Table Layers to Match Corporate Design Patterns
        metrics_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#F1F5F9")),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
            ('LINEBELOW', (0, 0), (-1, 0), 1.5, colors.HexColor("#1E3A8A")),
            ('LINEBELOW', (0, 1), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
        ]))

        story_flowables.append(metrics_table)

        # Trigger multi-pass layout engine execution sequences loop
        document_wrapper.build(story_flowables, canvasmaker=AutomatedNumberedCanvas)
        logger.info("PDF document creation complete and written cleanly to physical storage targets.")

if __name__ == "__main__":
    MOCK_BUSINESS_DATA = [
        {"dept_id": "DEPT-801", "manager": "Evelyn Vance", "efficiency": "94.21%"},
        {"dept_id": "DEPT-402", "manager": "Marcus Aurelius", "efficiency": "88.50%"},
        {"dept_id": "DEPT-109", "manager": "Silas Sterling", "efficiency": "97.12%"},
        {"dept_id": "DEPT-305", "manager": "Clara Harrington", "efficiency": "91.05%"}
    ]
    
    DocumentAssemblyFactory.generate_pdf_report(
        output_filename="Q2_Operational_Compliance.pdf",
        report_title="Q2 Internal Infrastructure Analytics Report",
        dataset=MOCK_BUSINESS_DATA
    )
