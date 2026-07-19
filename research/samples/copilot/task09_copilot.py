"""
Email Automation Bot using SendGrid and Pandas.
Features:
- Read recipient list from CSV
- Personalise email content
- Send via SendGrid (stub if no API key)
- Track opens/clicks (stubbed)
- Handle bounces (stubbed)
"""

import pandas as pd
import logging
import os
from typing import Dict
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

# Configure logging
logging.basicConfig(level=logging.INFO)

CSV_FILE = "recipients.csv"
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")


def load_recipients(file: str) -> pd.DataFrame:
    """Load recipient list from CSV."""
    return pd.read_csv(file)


def personalize_message(row: Dict[str, str]) -> str:
    """Generate personalized email content."""
    return f"Hello {row['name']},\n\nWe have an exciting update for you!\n\nRegards,\nTeam"


def send_email(to_email: str, subject: str, content: str) -> None:
    """Send email via SendGrid or log if no API key."""
    if not SENDGRID_API_KEY:
        logging.info(f"[Stub] Email to {to_email}: {subject}\n{content}")
        return
    try:
        message = Mail(from_email="noreply@example.com", to_emails=to_email, subject=subject, plain_text_content=content)
        sg = SendGridAPIClient(SENDGRID_API_KEY)
        response = sg.send(message)
        logging.info(f"Email sent to {to_email}, status {response.status_code}")
    except Exception as e:
        logging.error(f"Failed to send email: {e}")


def main():
    """Main entry point for email automation."""
    try:
        recipients = load_recipients(CSV_FILE)
        for _, row in recipients.iterrows():
            content = personalize_message(row)
            send_email(row["email"], "Exciting Update!", content)
        logging.info("All emails processed.")
    except Exception as e:
        logging.error(f"Error in email automation: {e}")


if __name__ == "__main__":
    main()

