import csv
import logging
from email.message import EmailMessage
from typing import Dict, List, Tuple
import smtplib
from jinja2 import Template  # Note: Jinja2 is not a standard library, replaced with string formatting for compliance
import getpass
import ssl

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler("email_automation.log"), logging.StreamHandler()]
)

# SMTP Configuration
SMTP_CONFIG = {
    "host": "smtp.example.com",  # UPDATE THIS
    "port": 587,  # Typical port for STARTTLS
    "username": "",  # UPDATE THIS
    "password": "",  # Will be prompted for security
    "sender_email": "your_email@example.com"  # UPDATE THIS
}

# Email Template (Simplified to use string formatting instead of Jinja2 for standard library compliance)
EMAIL_TEMPLATE = """
Dear {{ recipient_name }},

This is a personalised email for you from {{ sender_name }}.

Best Regards,
{{ sender_name }}
"""

def load_recipient_list(csv_file: str) -> List[Dict[str, str]]:
    """
    Loads recipient list from a CSV file.

    :param csv_file: Path to the CSV file containing recipient data
    :return: List of dictionaries, each representing a recipient with their data
    """
    recipients = []
    try:
        with open(csv_file, 'r') as file:
            reader = csv.DictReader(file)
            for row in reader:
                recipients.append(row)
    except FileNotFoundError:
        logging.error(f"CSV file {csv_file} not found.")
        raise
    except csv.Error as e:
        logging.error(f"CSV read error: {e}")
        raise
    return recipients

def render_email_template(template: str, data: Dict[str, str]) -> str:
    """
    Renders the email template with the given data.

    :param template: Email template string with placeholders
    :param data: Dictionary containing data to replace placeholders
    :return: Rendered email body
    """
    # Simplified to use string formatting; originally intended for Jinja2
    try:
        return template.replace("{{ recipient_name }}", data["name"]).replace("{{ sender_name }}", SMTP_CONFIG["sender_email"])
    except KeyError as e:
        logging.error(f"Missing key in data: {e}")
        raise

def send_email(
    recipient_email: str, 
    email_body: str, 
    subject: str = "Personalised Email"
) -> None:
    """
    Sends an email to the recipient using the configured SMTP settings.

    :param recipient_email: Email address of the recipient
    :param email_body: Body of the email
    :param subject: Subject of the email (default: "Personalised Email")
    """
    global SMTP_CONFIG
    msg = EmailMessage()
    msg.set_content(email_body)
    msg["Subject"] = subject
    msg["From"] = SMTP_CONFIG["sender_email"]
    msg["To"] = recipient_email

    try:
        # Secure the connection
        context = ssl.create_default_context()
        with smtplib.SMTP(SMTP_CONFIG["host"], SMTP_CONFIG["port"]) as smtp:
            smtp.starttls(context=context)
            smtp.login(SMTP_CONFIG["username"], SMTP_CONFIG["password"])
            smtp.send_message(msg)
        logging.info(f"Email sent to {recipient_email}")
    except smtplib.SMTPAuthenticationError:
        logging.error("SMTP Authentication Failed. Check credentials.")
    except smtplib.SMTPException as e:
        logging.error(f"SMTP Error: {e}")
    except Exception as e:
        logging.error(f"Unexpected Error: {e}")

def main():
    """
    Main execution point for the email automation bot.
    """
    csv_file = "recipients.csv"  # UPDATE THIS
    SMTP_CONFIG["password"] = getpass.getpass("Enter SMTP Password: ")
    
    # Validate SMTP_CONFIG
    required_fields = ["host", "port", "username", "sender_email"]
    for field in required_fields:
        if not SMTP_CONFIG[field]:
            logging.error(f"SMTP_CONFIG missing required field: {field}")
            return
    
    try:
        recipients = load_recipient_list(csv_file)
    except Exception as e:
        logging.error(f"Failed to load recipients: {e}")
        return

    for recipient in recipients:
        required_fields = ["email", "name"]  # Assuming these are column names in your CSV
        if not all(field in recipient for field in required_fields):
            logging.warning("Skipping recipient due to missing data")
            continue
        
        email_body = render_email_template(EMAIL_TEMPLATE, recipient)
        send_email(recipient["email"], email_body)

if __name__ == "__main__":
    main()