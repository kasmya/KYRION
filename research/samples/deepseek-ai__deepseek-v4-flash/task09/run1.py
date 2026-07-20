import csv
import logging
import os
import smtplib
from dataclasses import dataclass, field
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List, Dict, Optional, Tuple
from string import Template


@dataclass
class SMTPConfig:
    """SMTP server configuration."""
    host: str
    port: int
    user: str
    password: str
    use_tls: bool = True
    use_ssl: bool = False


@dataclass
class EmailConfig:
    """General email configuration."""
    from_addr: str
    subject_template: str = ""
    body_template: str = ""
    encoding: str = "utf-8"


@dataclass
class Recipient:
    """Represents a single email recipient with custom fields."""
    email: str
    name: str = ""
    fields: Dict[str, str] = field(default_factory=dict)


class EmailAutomationBot:
    """
    An email automation bot that reads recipients from a CSV file,
    renders email templates with placeholders, sends emails via SMTP,
    and logs all sent messages.
    """

    def __init__(
        self,
        smtp_config: SMTPConfig,
        email_config: EmailConfig,
        log_level: int = logging.INFO
    ) -> None:
        """
        Initialize the bot with SMTP and email settings.

        Args:
            smtp_config: SMTP server configuration.
            email_config: Email content and sender settings.
            log_level: Logging level (default: logging.INFO).
        """
        self.smtp_config = smtp_config
        self.email_config = email_config
        self._setup_logging(log_level)
        self.recipients: List[Recipient] = []

    def _setup_logging(self, log_level: int) -> None:
        """Configure logging for the bot."""
        logging.basicConfig(
            level=log_level,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler("email_bot.log"),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(self.__class__.__name__)

    def load_recipients_from_csv(self, csv_path: str) -> None:
        """
        Load recipients from a CSV file. Expects at least 'email' column.
        First row must be headers. Additional columns become custom fields.
        A 'name' column is optional but recommended.

        Args:
            csv_path: Path to the CSV file.

        Raises:
            FileNotFoundError: If the CSV file does not exist.
            ValueError: If CSV has no 'email' column.
        """
        if not os.path.isfile(csv_path):
            raise FileNotFoundError(f"CSV file not found: {csv_path}")

        self.recipients.clear()
        with open(csv_path, mode='r', newline='', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            if 'email' not in reader.fieldnames:
                raise ValueError("CSV must contain an 'email' column.")

            for row in reader:
                email = row.pop('email').strip()
                name = row.pop('name', '').strip()
                # remaining columns become custom fields
                fields = {k.strip(): v.strip() for k, v in row.items() if v}
                recipient = Recipient(email=email, name=name, fields=fields)
                self.recipients.append(recipient)

        self.logger.info(f"Loaded {len(self.recipients)} recipients from {csv_path}")

    def render_subject(self, recipient: Recipient) -> str:
        """
        Render the subject template with recipient data.

        Args:
            recipient: Recipient object with name and fields.

        Returns:
            Rendered subject string.
        """
        if not self.email_config.subject_template:
            return ""

        template = Template(self.email_config.subject_template)
        return template.safe_substitute(
            name=recipient.name,
            email=recipient.email,
            **recipient.fields
        )

    def render_body(self, recipient: Recipient) -> str:
        """
        Render the body template with recipient data.

        Args:
            recipient: Recipient object with name and fields.

        Returns:
            Rendered body string.
        """
        if not self.email_config.body_template:
            return ""

        template = Template(self.email_config.body_template)
        return template.safe_substitute(
            name=recipient.name,
            email=recipient.email,
            **recipient.fields
        )

    def _create_message(self, recipient: Recipient) -> MIMEMultipart:
        """
        Create a MIME multipart email message for the recipient.

        Args:
            recipient: The recipient.

        Returns:
            MIMEMultipart message ready to send.
        """
        msg = MIMEMultipart('alternative')
        msg['From'] = self.email_config.from_addr
        msg['To'] = recipient.email
        msg['Subject'] = self.render_subject(recipient)

        body_text = self.render_body(recipient)
        # Attach plain text version
        msg.attach(MIMEText(body_text, 'plain', self.email_config.encoding))
        # Optionally attach HTML version if template contains HTML
        # For simplicity, we only send plain text; HTML can be added similarly.
        return msg

    def send_email(self, recipient: Recipient) -> Tuple[bool, str]:
        """
        Send an email to a single recipient. Connects and disconnects per email
        to ensure individual error handling.

        Args:
            recipient: The recipient to send to.

        Returns:
            Tuple of (success: bool, details: str).
        """
        try:
            msg = self._create_message(recipient)
            server_kwargs = {}
            if self.smtp_config.use_ssl:
                server_kwargs['context'] = ssl.create_default_context()
                server = smtplib.SMTP_SSL(
                    self.smtp_config.host,
                    self.smtp_config.port,
                    **server_kwargs
                )
            else:
                server = smtplib.SMTP(
                    self.smtp_config.host,
                    self.smtp_config.port
                )
                if self.smtp_config.use_tls:
                    server.starttls(context=ssl.create_default_context())

            with server:
                server.login(self.smtp_config.user, self.smtp_config.password)
                server.send_message(msg)

            self.logger.info(f"Email sent to {recipient.email}")
            return True, "Sent successfully"

        except (smtplib.SMTPException, ConnectionError, OSError) as e:
            self.logger.error(f"Failed to send email to {recipient.email}: {e}")
            return False, str(e)

    def run(self) -> int:
        """
        Execute the bot: sends personalised emails to all loaded recipients.
        Logs each attempt.

        Returns:
            Number of successful sends.
        """
        if not self.recipients:
            self.logger.warning("No recipients loaded. Use load_recipients_from_csv() first.")
            return 0

        success_count = 0
        for recipient in self.recipients:
            ok, detail = self.send_email(recipient)
            if ok:
                success_count += 1

        self.logger.info(f"Finished: {success_count}/{len(self.recipients)} emails sent successfully.")
        return success_count


# Example usage (guarded to avoid execution on import)
if __name__ == "__main__":
    # Configuration via environment variables (security best practice)
    smtp_cfg = SMTPConfig(
        host=os.environ.get("SMTP_HOST", "smtp.example.com"),
        port=int(os.environ.get("SMTP_PORT", "587")),
        user=os.environ.get("SMTP_USER", ""),
        password=os.environ.get("SMTP_PASS", ""),
        use_tls=True,
        use_ssl=False
    )

    email_cfg = EmailConfig(
        from_addr=os.environ.get("EMAIL_FROM", "noreply@example.com"),
        subject_template=os.environ.get("EMAIL_SUBJECT", "Hello ${name}!"),
        body_template=os.environ.get("EMAIL_BODY", "Dear ${name},\n\nThis is a test email.")
    )

    bot = EmailAutomationBot(smtp_cfg, email_cfg)

    # Load recipients (expects a CSV file path as argument or default)
    import sys
    if len(sys.argv) > 1:
        csv_file = sys.argv[1]
    else:
        csv_file = "recipients.csv"
    try:
        bot.load_recipients_from_csv(csv_file)
    except (FileNotFoundError, ValueError) as e:
        bot.logger.error(f"Failed to load recipients: {e}")
        sys.exit(1)

    bot.run()