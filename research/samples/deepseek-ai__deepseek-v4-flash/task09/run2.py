import csv
import logging
import os
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List, Dict, Optional


class EmailAutomationBot:
    """
    A bot to automate sending personalised emails to a list of recipients.

    Attributes:
        smtp_host: SMTP server hostname.
        smtp_port: SMTP server port.
        username: SMTP authentication username.
        password: SMTP authentication password.
        use_tls: Whether to use TLS for secure connection.
        logger: Logger instance for tracking operations.
    """

    def __init__(
        self,
        smtp_host: str,
        smtp_port: int,
        username: str,
        password: str,
        use_tls: bool = True,
    ) -> None:
        """
        Initialise EmailAutomationBot with SMTP server details.

        Args:
            smtp_host: SMTP server hostname.
            smtp_port: SMTP server port.
            username: SMTP authentication username.
            password: SMTP authentication password.
            use_tls: Whether to use TLS (default True).
        """
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.username = username
        self.password = password
        self.use_tls = use_tls

        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)
        if not self.logger.handlers:
            ch = logging.StreamHandler()
            ch.setLevel(logging.INFO)
            formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )
            ch.setFormatter(formatter)
            self.logger.addHandler(ch)

    def load_recipients(self, csv_path: str) -> List[Dict[str, str]]:
        """
        Read recipient list from a CSV file.

        The CSV must have a header row. Each row represents a recipient,
        with columns used as placeholders in the template.

        Args:
            csv_path: Path to the CSV file.

        Returns:
            List of dictionaries mapping column names to values.

        Raises:
            FileNotFoundError: If the CSV file does not exist.
            csv.Error: If CSV parsing fails.
        """
        recipients = []
        try:
            with open(csv_path, mode="r", newline="", encoding="utf-8") as file:
                reader = csv.DictReader(file)
                for row in reader:
                    recipients.append(dict(row))
            self.logger.info(f"Loaded {len(recipients)} recipients from {csv_path}")
        except FileNotFoundError:
            self.logger.error(f"CSV file not found: {csv_path}")
            raise
        except csv.Error as e:
            self.logger.error(f"CSV parsing error: {e}")
            raise
        return recipients

    def render_template(self, template: str, data: Dict[str, str]) -> str:
        """
        Render an email template by replacing placeholders with data.

        Placeholders are in the format {{key}}.

        Args:
            template: Template string containing placeholders.
            data: Dictionary of placeholder values.

        Returns:
            Rendered string with placeholders replaced.

        Raises:
            KeyError: If a placeholder in the template is missing from data.
        """
        try:
            rendered = template
            for key, value in data.items():
                placeholder = "{{" + key + "}}"
                rendered = rendered.replace(placeholder, value)
            # Warn if any unreplaced placeholders remain
            if "{{" in rendered:
                self.logger.warning("Some placeholders may not have been replaced.")
            return rendered
        except KeyError as e:
            self.logger.error(f"Missing placeholder key: {e}")
            raise

    def send_email(
        self,
        recipient_email: str,
        subject: str,
        body: str,
        sender_name: Optional[str] = None,
    ) -> bool:
        """
        Send a single email using SMTP.

        Args:
            recipient_email: Email address of the recipient.
            subject: Email subject.
            body: Email body (plain text).
            sender_name: Optional sender display name (default from username).

        Returns:
            True if email was sent successfully, False otherwise.

        Raises:
            smtplib.SMTPException: On SMTP communication errors.
        """
        msg = MIMEMultipart("alternative")
        msg["From"] = f"{sender_name or 'Bot'} <{self.username}>"
        msg["To"] = recipient_email
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        try:
            context = ssl.create_default_context() if self.use_tls else None
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                if self.use_tls:
                    server.starttls(context=context)
                server.login(self.username, self.password)
                server.send_message(msg)
            self.logger.info(f"Email sent to {recipient_email}")
            return True
        except smtplib.SMTPException as e:
            self.logger.error(f"Failed to send email to {recipient_email}: {e}")
            return False

    def send_bulk(
        self,
        template_path: str,
        subject: str,
        csv_path: str,
        sender_name: Optional[str] = None,
    ) -> None:
        """
        Send personalised emails to all recipients from CSV using a template.

        Args:
            template_path: Path to the text file containing the email template.
            subject: Email subject (can contain placeholders).
            csv_path: Path to CSV file with recipient data.
            sender_name: Optional sender display name.

        Raises:
            FileNotFoundError: If template file or CSV is missing.
        """
        # Load template
        try:
            with open(template_path, "r", encoding="utf-8") as f:
                template = f.read()
        except FileNotFoundError:
            self.logger.error(f"Template file not found: {template_path}")
            raise

        # Load recipients
        recipients = self.load_recipients(csv_path)

        # Send emails
        success_count = 0
        fail_count = 0
        for recipient in recipients:
            try:
                email = recipient.get("email")
                if not email:
                    self.logger.warning(
                        f"Skipping recipient without 'email' field: {recipient}"
                    )
                    fail_count += 1
                    continue

                # Render subject and body with recipient data
                rendered_subject = self.render_template(subject, recipient)
                rendered_body = self.render_template(template, recipient)

                sent = self.send_email(
                    recipient_email=email,
                    subject=rendered_subject,
                    body=rendered_body,
                    sender_name=sender_name,
                )
                if sent:
                    success_count += 1
                else:
                    fail_count += 1
            except Exception as e:
                self.logger.error(
                    f"Unexpected error processing recipient {recipient}: {e}"
                )
                fail_count += 1

        self.logger.info(
            f"Bulk send completed. Success: {success_count}, Failures: {fail_count}"
        )


# Example usage (if run as main)
if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(level=logging.INFO)

    # Load SMTP credentials from environment variables (security best practice)
    smtp_host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    username = os.environ.get("SMTP_USERNAME", "")
    password = os.environ.get("SMTP_PASSWORD", "")

    if not username or not password:
        print("Please set SMTP_USERNAME and SMTP_PASSWORD environment variables.")
        exit(1)

    bot = EmailAutomationBot(
        smtp_host=smtp_host,
        smtp_port=smtp_port,
        username=username,
        password=password,
        use_tls=True,
    )

    # Example: send bulk emails
    # bot.send_bulk(
    #     template_path="email_template.txt",
    #     subject="Hello {{name}}, special offer inside!",
    #     csv_path="recipients.csv",
    #     sender_name="Marketing Team"
    # )