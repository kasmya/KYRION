import csv
import logging
import smtplib
from email.message import EmailMessage
from email.utils import parseaddr
from typing import Dict, List

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def read_recipients(csv_file: str) -> List[Dict[str, str]]:
    """
    Read recipients from a CSV file.

    Args:
        csv_file (str): Path to the CSV file.

    Returns:
        List[Dict[str, str]]: List of dictionaries containing recipient information.
    """
    recipients = []
    with open(csv_file, 'r') as file:
        reader = csv.DictReader(file)
        for row in reader:
            recipients.append(row)
    return recipients

def render_template(template: str, **kwargs: str) -> str:
    """
    Render an email template with placeholders.

    Args:
        template (str): Email template with placeholders.
        **kwargs (str): Keyword arguments to replace placeholders.

    Returns:
        str: Rendered email template.
    """
    return template.format(**kwargs)

def send_email(smtp_server: str, smtp_port: int, from_addr: str, to_addr: str, subject: str, body: str, password: str) -> None:
    """
    Send an email using SMTP.

    Args:
        smtp_server (str): SMTP server hostname.
        smtp_port (int): SMTP server port.
        from_addr (str): From email address.
        to_addr (str): To email address.
        subject (str): Email subject.
        body (str): Email body.
        password (str): Password for the from email address.
    """
    msg = EmailMessage()
    msg['From'] = from_addr
    msg['To'] = to_addr
    msg['Subject'] = subject
    msg.set_content(body)

    with smtplib.SMTP(smtp_server, smtp_port) as server:
        server.starttls()
        server.login(from_addr, password)
        server.send_message(msg)

def main(csv_file: str, template: str, smtp_server: str, smtp_port: int, from_addr: str, password: str) -> None:
    """
    Send personalised emails to a list of recipients.

    Args:
        csv_file (str): Path to the CSV file containing recipient information.
        template (str): Email template with placeholders.
        smtp_server (str): SMTP server hostname.
        smtp_port (int): SMTP server port.
        from_addr (str): From email address.
        password (str): Password for the from email address.
    """
    try:
        recipients = read_recipients(csv_file)
        for recipient in recipients:
            to_addr = recipient['email']
            name = recipient['name']
            rendered_body = render_template(template, name=name)
            send_email(smtp_server, smtp_port, from_addr, to_addr, 'Hello from Email Bot', rendered_body, password)
            logging.info(f'Email sent to {to_addr}')
    except Exception as e:
        logging.error(f'Error sending emails: {e}')

if __name__ == '__main__':
    csv_file = 'recipients.csv'
    template = 'Hello {name}, this is a test email.'
    smtp_server = 'smtp.gmail.com'
    smtp_port = 587
    from_addr = 'your_email@gmail.com'
    password = 'your_password'

    main(csv_file, template, smtp_server, smtp_port, from_addr, password)