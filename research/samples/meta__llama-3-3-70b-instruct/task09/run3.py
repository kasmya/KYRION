import csv
import smtplib
from email.message import EmailMessage
from email.utils import formatdate
from typing import Dict, List
import logging
import ssl

# Set up logging configuration
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def read_recipient_list(csv_file: str) -> List[Dict]:
    """
    Reads the recipient list from a CSV file.

    Args:
        csv_file (str): The path to the CSV file.

    Returns:
        List[Dict]: A list of dictionaries, where each dictionary represents a recipient.
    """
    recipients = []
    with open(csv_file, 'r') as file:
        reader = csv.DictReader(file)
        for row in reader:
            recipients.append(dict(row))
    return recipients

def render_email_template(template: str, recipient: Dict) -> str:
    """
    Renders the email template with the recipient's information.

    Args:
        template (str): The email template with placeholders.
        recipient (Dict): The recipient's information.

    Returns:
        str: The rendered email template.
    """
    for key, value in recipient.items():
        template = template.replace(f'{{{{ {key} }}}}', value)
    return template

def send_email(smtp_server: str, smtp_port: int, sender_email: str, sender_password: str, recipient: Dict, email_template: str) -> None:
    """
    Sends a personalized email to a recipient.

    Args:
        smtp_server (str): The SMTP server address.
        smtp_port (int): The SMTP server port.
        sender_email (str): The sender's email address.
        sender_password (str): The sender's email password.
        recipient (Dict): The recipient's information.
        email_template (str): The email template with placeholders.
    """
    # Render the email template
    email_body = render_email_template(email_template, recipient)

    # Create the email message
    msg = EmailMessage()
    msg['Subject'] = 'Personalized Email'
    msg['From'] = sender_email
    msg['To'] = recipient['email']
    msg['Date'] = formatdate()
    msg.set_content(email_body)

    # Set up the SMTP server
    context = ssl.create_default_context()
    with smtplib.SMTP_SSL(smtp_server, smtp_port, context=context) as server:
        server.login(sender_email, sender_password)
        server.send_message(msg)

        # Log the sent email
        logging.info(f'Email sent to {recipient["email"]}')

def main() -> None:
    try:
        # Read the recipient list from the CSV file
        recipients = read_recipient_list('recipients.csv')

        # Set up the SMTP configuration
        smtp_server = 'smtp.example.com'
        smtp_port = 465
        sender_email = 'sender@example.com'
        sender_password = 'password'

        # Set up the email template
        email_template = 'Hello {{ name }}, this is a personalized email.'

        # Send personalized emails to each recipient
        for recipient in recipients:
            send_email(smtp_server, smtp_port, sender_email, sender_password, recipient, email_template)

    except Exception as e:
        logging.error(f'An error occurred: {e}')

if __name__ == '__main__':
    main()