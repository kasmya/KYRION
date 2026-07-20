import csv
import logging
from dataclasses import dataclass
from email.message import EmailMessage
from smtplib import SMTPSSL
from typing import Dict, List

# Configuration
CONFIG = {
    "SMTP_HOST": "smtp.example.com",
    "SMTP_PORT": 465,
    "FROM_EMAIL": "bot@example.com",
    "PASSWORD": "secure_password",  # Use environment variables in production
    "CSV_FILE": "recipients.csv",
    "TEMPLATE_FILE": "email_template.txt"
}

# Logging Setup
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

@dataclass
class Recipient:
    """Represents a recipient with email and custom data for templating."""
    email: str
    data: Dict[str, str]

def load_recipients(csv_file: str) -> List[Recipient]:
    """
    Loads recipients from a CSV file.

    :param csv_file: Path to the CSV file containing recipient data.
    :return: List of Recipient objects.
    """
    recipients = []
    with open(csv_file, mode="r", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        for row in reader:
            # Assuming the first column is email, and the rest are custom data
            email = row["email"]
            data = {key: value for key, value in row.items() if key != "email"}
            recipients.append(Recipient(email, data))
    return recipients

def render_template(template_file: str, data: Dict[str, str]) -> str:
    """
    Renders an email template with placeholders.

    :param template_file: Path to the template file.
    :param data: Dictionary of placeholders and their values.
    :return: Rendered email body.
    """
    with open(template_file, mode="r", encoding="utf-8") as file:
        template = file.read()
        for key, value in data.items():
            template = template.replace(f"{{{{ {key} }}}}", value)
    return template

def send_email(smtp_host: str, smtp_port: int, from_email: str, password: str, recipient: Recipient, email_body: str) -> None:
    """
    Sends a personalized email to a recipient via SMTP.

    :param smtp_host: SMTP server host.
    :param smtp_port: SMTP server port.
    :param from_email: Sender's email.
    :param password: Sender's password.
    :param recipient: Recipient object.
    :param email_body: Rendered email body.
    """
    try:
        with SMTPSSL(smtp_host, smtp_port) as smtp:
            smtp.login(from_email, password)
            msg = EmailMessage()
            msg.set_content(email_body)
            msg["subject"] = "Personalized Email"  # Dynamic subject can be added
            msg["from"] = from_email
            msg["to"] = recipient.email
            smtp.send_message(msg)
            logger.info(f"Email sent to {recipient.email}")
    except Exception as e:
        logger.error(f"Failed to send email to {recipient.email}: {e}")

def main() -> None:
    """Main entry point for the email automation bot."""
    recipients = load_recipients(CONFIG["CSV_FILE"])
    for recipient in recipients:
        email_body = render_template(CONFIG["TEMPLATE_FILE"], recipient.data)
        send_email(
            CONFIG["SMTP_HOST"],
            CONFIG["SMTP_PORT"],
            CONFIG["FROM_EMAIL"],
            CONFIG["PASSWORD"],
            recipient,
            email_body
        )

if __name__ == "__main__":
    main()