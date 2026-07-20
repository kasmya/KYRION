import csv
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Dict, List

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class EmailAutomationBot:
    def __init__(self, smtp_config: Dict[str, str], email_template: str, csv_file: str):
        """
        Initializes the email automation bot with SMTP configuration, email template, and CSV file.

        Args:
        smtp_config (Dict[str, str]): A dictionary containing SMTP configuration.
        email_template (str): The email template with placeholders.
        csv_file (str): The path to the CSV file containing the recipient list.
        """
        self.smtp_config = smtp_config
        self.email_template = email_template
        self.csv_file = csv_file

    def read_recipients(self) -> List[Dict[str, str]]:
        """
        Reads the recipient list from the CSV file.

        Returns:
        List[Dict[str, str]]: A list of dictionaries containing recipient information.
        """
        recipients = []
        try:
            with open(self.csv_file, 'r') as file:
                reader = csv.DictReader(file)
                for row in reader:
                    recipients.append(row)
        except FileNotFoundError:
            logging.error(f"CSV file '{self.csv_file}' not found.")
        except csv.Error as e:
            logging.error(f"Error reading CSV file: {e}")
        return recipients

    def render_email_template(self, recipient: Dict[str, str]) -> str:
        """
        Renders the email template with placeholders.

        Args:
        recipient (Dict[str, str]): A dictionary containing recipient information.

        Returns:
        str: The rendered email template.
        """
        try:
            return self.email_template.format(**recipient)
        except KeyError as e:
            logging.error(f"Missing placeholder '{e}' in recipient data.")

    def send_email(self, recipient: Dict[str, str], email_content: str) -> bool:
        """
        Sends an email to a recipient using the SMTP configuration.

        Args:
        recipient (Dict[str, str]): A dictionary containing recipient information.
        email_content (str): The email content.

        Returns:
        bool: True if the email is sent successfully, False otherwise.
        """
        try:
            server = smtplib.SMTP(self.smtp_config['host'], self.smtp_config['port'])
            server.starttls()
            server.login(self.smtp_config['username'], self.smtp_config['password'])
            msg = MIMEMultipart()
            msg['From'] = self.smtp_config['from']
            msg['To'] = recipient['email']
            msg['Subject'] = self.smtp_config['subject']
            msg.attach(MIMEText(email_content, 'plain'))
            server.sendmail(self.smtp_config['from'], recipient['email'], msg.as_string())
            server.quit()
            logging.info(f"Email sent to {recipient['email']}")
            return True
        except smtplib.SMTPException as e:
            logging.error(f"Error sending email: {e}")

    def run(self) -> None:
        """
        Runs the email automation bot.
        """
        recipients = self.read_recipients()
        for recipient in recipients:
            email_content = self.render_email_template(recipient)
            self.send_email(recipient, email_content)


if __name__ == '__main__':
    smtp_config = {
        'host': 'smtp.gmail.com',
        'port': 587,
        'username': 'your_email@gmail.com',
        'password': 'your_password',
        'from': 'your_email@gmail.com',
        'subject': 'Test Email'
    }
    email_template = """
    Dear {name},

    This is a test email.

    Best regards,
    Your Name
    """
    csv_file = 'recipients.csv'
    bot = EmailAutomationBot(smtp_config, email_template, csv_file)
    bot.run()