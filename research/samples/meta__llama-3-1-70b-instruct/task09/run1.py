import csv
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Dict, List
import smtplib
import ssl
from pathlib import Path

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def read_recipients(csv_file: str) -> List[Dict[str, str]]:
    """
    Reads recipient list from a CSV file.

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

def render_template(template_file: str, recipient: Dict[str, str]) -> str:
    """
    Renders an email template with placeholders.

    Args:
    template_file (str): Path to the template file.
    recipient (Dict[str, str]): Dictionary containing recipient information.

    Returns:
    str: Rendered email content.
    """
    with open(template_file, 'r') as file:
        template = file.read()
    for key, value in recipient.items():
        template = template.replace('{{ ' + key + ' }}', value)
    return template

def send_email(
    recipient: str, 
    subject: str, 
    body: str, 
    smtp_server: str, 
    smtp_port: int, 
    sender: str, 
    password: str
) -> None:
    """
    Sends an email using SMTP.

    Args:
    recipient (str): Recipient email address.
    subject (str): Email subject.
    body (str): Email body.
    smtp_server (str): SMTP server address.
    smtp_port (int): SMTP server port.
    sender (str): Sender email address.
    password (str): Sender email password.
    """
    message = MIMEMultipart()
    message['From'] = sender
    message['To'] = recipient
    message['Subject'] = subject
    message.attach(MIMEText(body, 'plain'))

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL(smtp_server, smtp_port, context=context) as server:
        server.login(sender, password)
        server.sendmail(sender, recipient, message.as_string())

def main() -> None:
    csv_file = 'recipients.csv'
    template_file = 'template.txt'
    smtp_server = 'smtp.example.com'
    smtp_port = 465
    sender = 'sender@example.com'
    password = 'password'

    recipients = read_recipients(csv_file)

    for recipient in recipients:
        subject = 'Hello ' + recipient['name']
        body = render_template(template_file, recipient)
        try:
            send_email(
                recipient['email'], 
                subject, 
                body, 
                smtp_server, 
                smtp_port, 
                sender, 
                password
            )
            logging.info(f'Email sent to {recipient["email"]}')
        except Exception as e:
            logging.error(f'Error sending email to {recipient["email"]}: {str(e)}')

if __name__ == '__main__':
    main()