import csv
import logging
from email.message import EmailMessage
import smtplib
from typing import Dict, List
import getpass

# Configure Logging
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

def read_recipient_list(csv_file: str) -> List[Dict[str, str]]:
    """
    Reads recipient list from a CSV file.

    Args:
    - csv_file (str): Path to the CSV file containing recipient information.
        Expected format: name,email,subject_placeholder (one recipient per row)

    Returns:
    - List[Dict[str, str]]: List of dictionaries containing 'name', 'email', and 'subject' for each recipient.
    """
    recipients = []
    try:
        with open(csv_file, 'r') as file:
            reader = csv.DictReader(file)
            for row in reader:
                # Basic validation
                if 'name' in row and 'email' in row and 'subject' in row:
                    recipients.append({'name': row['name'], 'email': row['email'], 'subject': row['subject']})
                else:
                    logging.warning(f"Skipping row due to missing required fields: {row}")
    except FileNotFoundError:
        logging.error(f"CSV file not found: {csv_file}")
    except csv.Error as e:
        logging.error(f"Error reading CSV: {e}")
    return recipients

def render_email_template(template_path: str, placeholders: Dict[str, str]) -> str:
    """
    Renders an email template by replacing placeholders.

    Args:
    - template_path (str): Path to the email template file.
    - placeholders (Dict[str, str]): Dictionary of placeholders and their values.

    Returns:
    - str: Rendered email content.
    """
    try:
        with open(template_path, 'r') as file:
            template = file.read()
            for key, value in placeholders.items():
                template = template.replace(f"{{{{ {key} }}}}", value)
            return template
    except FileNotFoundError:
        logging.error(f"Template file not found: {template_path}")
        return ""

def send_email(smtp_config: Dict[str, str], to_email: str, subject: str, email_content: str) -> bool:
    """
    Sends an email using the provided SMTP configuration.

    Args:
    - smtp_config (Dict[str, str]): Dictionary containing 'host', 'port', 'username', 'password'.
    - to_email (str): Recipient's email address.
    - subject (str): Email subject.
    - email_content (str): Email body content.

    Returns:
    - bool: True if email is sent successfully, False otherwise.
    """
    msg = EmailMessage()
    msg.set_content(email_content)
    msg['Subject'] = subject
    msg['From'] = smtp_config['username']
    msg['To'] = to_email

    try:
        with smtplib.SMTP_SSL(smtp_config['host'], smtp_config['port']) as smtp:
            smtp.login(smtp_config['username'], smtp_config['password'])
            smtp.send_message(msg)
            logging.info(f"Email sent to {to_email}")
            return True
    except smtplib.SMTPException as e:
        logging.error(f"Failed to send email to {to_email}: {e}")
        return False

def main():
    # Configuration
    csv_file_path = "recipients.csv"
    email_template_path = "email_template.txt"
    smtp_config = {
        'host': 'smtp.example.com',
        'port': 465,  # Typical SSL port
        'username': input("Enter SMTP Username: "),
        'password': getpass.getpass("Enter SMTP Password: ")  # Secure password input
    }

    recipients = read_recipient_list(csv_file_path)
    if not recipients:
        logging.error("No valid recipients found.")
        return

    for recipient in recipients:
        placeholders = {'name': recipient['name']}  # Example placeholder
        email_content = render_email_template(email_template_path, placeholders)
        if email_content:
            send_email(smtp_config, recipient['email'], recipient['subject'], email_content)
        else:
            logging.warning(f"Skipping {recipient['email']}: Empty email content.")

if __name__ == "__main__":
    main()