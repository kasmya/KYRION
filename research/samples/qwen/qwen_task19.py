"""PDF Report Generator with ReportLab, Pandas, and CLI."""
import os, argparse, logging
from typing import List, Dict
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch

logging.basicConfig(level=logging.INFO)

def create_pdf_report(data: pd.DataFrame, output_path: str, title: str = "Report"):
    """Generate a PDF report with tables, headers, and footers."""
    doc = SimpleDocTemplate(output_path, pagesize=letter,
                            rightMargin=72, leftMargin=72,
                            topMargin=72, bottomMargin=18)
    
    elements = []
    styles = getSampleStyleSheet()
    
    # Title
    elements.append(Paragraph(title, styles['Title']))
    elements.append(Spacer(1, 0.2*inch))
    
    # Summary stats
    summary = data.describe().reset_index()
    summary_table = Table(summary.values.tolist(), colWidths=[1.5*inch]*len(summary.columns))
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    elements.append(Paragraph("Summary Statistics", styles['Heading2']))
    elements.append(summary_table)
    elements.append(Spacer(1, 0.2*inch))
    
    # Data table (first 10 rows)
    elements.append(Paragraph("Data Sample", styles['Heading2']))
    data_table = Table([data.columns.tolist()] + data.head(10).values.tolist(), 
                       colWidths=[1.2*inch]*min(len(data.columns), 5))
    data_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.blue),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    elements.append(data_table)
    
    # Build PDF with header/footer
    def header_footer(canvas, doc):
        canvas.saveState()
        canvas.setFont('Helvetica', 10)
        canvas.drawString(inch, letter[1] - 0.5*inch, f"Generated Report: {title}")
        canvas.drawRightInch(letter[0] - inch, 0.5*inch, f"Page {doc.page}")
        canvas.restoreState()
        
    doc.build(elements, onFirstPage=header_footer, onLaterPages=header_footer)
    logging.info(f"PDF generated: {output_path}")

def main():
    parser = argparse.ArgumentParser(description="PDF Report Generator")
    parser.add_argument("input_csv", help="Input CSV file")
    parser.add_argument("output_pdf", help="Output PDF file")
    parser.add_argument("--title", default="Data Report", help="Report title")
    
    args = parser.parse_args()
    
    try:
        df = pd.read_csv(args.input_csv)
        create_pdf_report(df, args.output_pdf, args.title)
    except Exception as e:
        logging.error(f"Failed to generate report: {e}")

if __name__ == "__main__":
    main()