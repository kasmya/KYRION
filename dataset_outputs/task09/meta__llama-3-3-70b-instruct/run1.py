import csv
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Dict
import logging
from logging.handlers import RotatingFileHandler

# Set up logging configuration
logger = logging.getLogger('email_bot')
logger.setLevel(logging.INFO)

# Create a rotating file handler
handler = RotatingFileHandler('email_bot.log', maxBytes=1000000, backupCount=1)
handler.setLevel(logging.INFO)

# Create a formatter and attach it to the handler
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)

# Add the handler to the logger
logger.addHandler(handler)

def read_recipients_from_csv(file_path: str) -> List[Dict[str, str]]:
    """
    Reads recipient list from a CSV file.

    Args:
    file_path (str): Path to the CSV file.

    Returns:
    List[Dict[str, str]]: List of dictionaries containing recipient information.
    """
    recipients = []
    with open(file_path, 'r') as file:
        reader = csv.DictReader(file)
        for row in reader:
            recipients.append(row)
    return recipients

def render_email_template(template_path: str, recipient: Dict[str, str]) -> str:
    """
    Renders an email template with placeholders.

    Args:
    template_path (str): Path to the email template file.
    recipient (Dict[str, str]): Dictionary containing recipient information.

    Returns:
    str: Rendered email template.
    """
    with open(template_path, 'r') as file:
        template = file.read()
    for key, value in recipient.items():
        template = template.replace(f'{{{{ {key} }}}}', value)
    return template

def send_email(smtp_server: str, smtp_port: int, sender: str, recipient: str, subject: str, body: str, password: str) -> None:
    """
    Sends an email using SMTP.

    Args:
    smtp_server (str): SMTP server address.
    smtp_port (int): SMTP server port.
    sender (str): Sender's email address.
    recipient (str): Recipient's email address.
    subject (str): Email subject.
    body (str): Email body.
    password (str): Sender's email password.
    """
    msg = MIMEMultipart()
    msg['From'] = sender
    msg['To'] = recipient
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))

    server = smtplib.SMTP(smtp_server, smtp_port)
    server.starttls()
    server.login(sender, password)
    text = msg.as_string()
    server.sendmail(sender, recipient, text)
    server.quit()

    logger.info(f'Email sent to {recipient}')

def main() -> None:
    try:
        # Read recipient list from CSV
        recipients = read_recipients_from_csv('recipients.csv')

        # Render email template
        template_path = 'email_template.txt'
        smtp_server = 'smtp.gmail.com'
        smtp_port = 587
        sender = 'your_email@gmail.com'
        password = 'your_password'

        for recipient in recipients:
            rendered_template = render_email_template(template_path, recipient)
            subject = 'Personalised Email'
            send_email(smtp_server, smtp_port, sender, recipient['email'], subject, rendered_template, password)

    except Exception as e:
        logger.error(f'Error: {e}')

if __name__ == '__main__':
    main()