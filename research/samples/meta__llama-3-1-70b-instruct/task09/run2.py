import csv
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Dict, List
import logging
from logging.handlers import RotatingFileHandler
from ssl import create_default_context, Purpose
import os

class EmailAutomationBot:
    def __init__(self, smtp_config: Dict[str, str], logger: logging.Logger):
        self.smtp_config = smtp_config
        self.logger = logger

    def read_recipients_from_csv(self, csv_file_path: str) -> List[Dict[str, str]]:
        """
        Reads recipient list from a CSV file.

        Args:
            csv_file_path (str): Path to the CSV file.

        Returns:
            List[Dict[str, str]]: List of recipients with their details.
        """
        recipients = []
        with open(csv_file_path, 'r') as file:
            reader = csv.DictReader(file)
            for row in reader:
                recipients.append(dict(row))
        return recipients

    def render_email_template(self, template_path: str, recipient: Dict[str, str]) -> str:
        """
        Renders the email template with placeholders replaced.

        Args:
            template_path (str): Path to the email template file.
            recipient (Dict[str, str]): Recipient details.

        Returns:
            str: Rendered email content.
        """
        with open(template_path, 'r') as file:
            template = file.read()
        for key, value in recipient.items():
            template = template.replace(f"{{{key}}}", value)
        return template

    def send_email(self, recipient: Dict[str, str], subject: str, content: str) -> None:
        """
        Sends an email to the recipient.

        Args:
            recipient (Dict[str, str]): Recipient details.
            subject (str): Email subject.
            content (str): Email content.
        """
        msg = MIMEMultipart()
        msg['From'] = self.smtp_config['from']
        msg['To'] = recipient['email']
        msg['Subject'] = subject

        body = content
        msg.attach(MIMEText(body, 'plain'))

        context = create_default_context(Purpose.SERVER_AUTH)
        with smtplib.SMTP_SSL(self.smtp_config['host'], self.smtp_config['port'], context=context) as server:
            server.login(self.smtp_config['username'], self.smtp_config['password'])
            text = msg.as_string()
            server.sendmail(self.smtp_config['from'], recipient['email'], text)
        self.logger.info(f"Email sent to {recipient['email']}")

    def run(self, csv_file_path: str, template_path: str, subject: str) -> None:
        """
        Runs the email automation bot.

        Args:
            csv_file_path (str): Path to the CSV file.
            template_path (str): Path to the email template file.
            subject (str): Email subject.
        """
        recipients = self.read_recipients_from_csv(csv_file_path)
        for recipient in recipients:
            content = self.render_email_template(template_path, recipient)
            self.send_email(recipient, subject, content)

if __name__ == "__main__":
    logger = logging.getLogger('email_automation_bot')
    logger.setLevel(logging.INFO)

    handler = RotatingFileHandler('email_automation_bot.log', maxBytes=1000000, backupCount=1)
    logger.addHandler(handler)

    smtp_config = {
        'host': 'smtp.gmail.com',
        'port': 465,
        'username': os.environ.get('EMAIL_USERNAME'),
        'password': os.environ.get('EMAIL_PASSWORD'),
        'from': 'your_email@gmail.com'
    }

    bot = EmailAutomationBot(smtp_config, logger)
    bot.run('recipients.csv', 'template.txt', 'Test Email')