import csv
import logging
import os
import smtplib
import ssl
from dataclasses import dataclass, field
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate
from pathlib import Path
from typing import Dict, List, Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("email_bot.log"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


@dataclass
class EmailConfig:
    """SMTP server configuration."""
    host: str
    port: int = 587
    username: str = field(default_factory=lambda: os.getenv("SMTP_USER", ""))
    password: str = field(default_factory=lambda: os.getenv("SMTP_PASS", ""))
    use_tls: bool = True
    use_ssl: bool = False


class EmailAutomationBot:
    """Automated email sender with CSV recipients, template rendering, and logging."""

    def __init__(self, config: Optional[EmailConfig] = None) -> None:
        """Initialize bot with SMTP configuration.

        Args:
            config: EmailConfig object; defaults to environment variables.
        """
        self.config = config or EmailConfig()
        self._validate_config()
        logger.info("EmailAutomationBot initialized with host=%s, port=%d",
                     self.config.host, self.config.port)

    def _validate_config(self) -> None:
        """Ensure required config values are present."""
        if not self.config.host:
            raise ValueError("SMTP host must be provided.")
        if not self.config.username or not self.config.password:
            raise ValueError("SMTP username and password must be set via environment variables or config.")

    def load_recipients(self, csv_path: str) -> List[Dict[str, str]]:
        """Load recipient data from a CSV file.

        Args:
            csv_path: Path to CSV file with columns (e.g., name, email).

        Returns:
            List of dictionaries with column headers as keys.

        Raises:
            FileNotFoundError: If file does not exist.
            ValueError: If CSV is empty or missing required 'email' column.
        """
        path = Path(csv_path)
        if not path.is_file():
            raise FileNotFoundError(f"CSV file not found: {csv_path}")

        recipients = []
        with path.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            if "email" not in reader.fieldnames:
                raise ValueError("CSV must contain an 'email' column.")
            for row in reader:
                if row.get("email"):  # skip empty email rows
                    recipients.append(row)

        if not recipients:
            raise ValueError("No recipients found in CSV file.")

        logger.info("Loaded %d recipients from %s", len(recipients), csv_path)
        return recipients

    def render_template(self, template: str, placeholders: Dict[str, str]) -> str:
        """Render an email template by replacing placeholders with recipient data.

        Placeholders should be in the format {placeholder_name}.
        Only existing placeholders are replaced; unknown ones remain unchanged.

        Args:
            template: Email body with placeholders.
            placeholders: Dictionary mapping placeholder keys to values.

        Returns:
            Rendered string.
        """
        rendered = template
        for key, value in placeholders.items():
            rendered = rendered.replace(f"{{{key}}}", value)
        logger.debug("Template rendered with %d placeholders.", len(placeholders))
        return rendered

    def _create_message(self, subject: str, body_text: str, body_html: Optional[str],
                        to_email: str, to_name: Optional[str] = None) -> MIMEMultipart:
        """Construct a MIME multipart email message.

        Args:
            subject: Email subject.
            body_text: Plain text body.
            body_html: Optional HTML body.
            to_email: Recipient email address.
            to_name: Optional recipient name for display.

        Returns:
            MIMEMultipart message ready to send.
        """
        msg = MIMEMultipart("alternative")
        msg["From"] = self.config.username
        msg["To"] = f"{to_name or ''} <{to_email}>" if to_name else to_email
        msg["Subject"] = subject
        msg["Date"] = formatdate(localtime=True)

        msg.attach(MIMEText(body_text, "plain", "utf-8"))
        if body_html:
            msg.attach(MIMEText(body_html, "html", "utf-8"))

        return msg

    def send_email(self, to_email: str, subject: str, body_text: str,
                   body_html: Optional[str] = None,
                   to_name: Optional[str] = None) -> bool:
        """Send a single email to one recipient.

        Args:
            to_email: Recipient email address.
            subject: Email subject (can include placeholders).
            body_text: Plain text body.
            body_html: Optional HTML body.
            to_name: Optional recipient name.

        Returns:
            True on success, False on failure.
        """
        msg = self._create_message(subject, body_text, body_html, to_email, to_name)

        try:
            context = ssl.create_default_context() if self.config.use_ssl else None
            with smtplib.SMTP(self.config.host, self.config.port, timeout=30) as server:
                if self.config.use_tls:
                    server.starttls(context=context)
                elif self.config.use_ssl:
                    server = smtplib.SMTP_SSL(self.config.host, self.config.port, context=context)
                server.login(self.config.username, self.config.password)
                server.send_message(msg)
            logger.info("Email sent successfully to %s <%s>", to_name or "", to_email)
            return True
        except (smtplib.SMTPException, OSError) as e:
            logger.error("Failed to send email to %s: %s", to_email, str(e))
            return False

    def send_bulk(self, recipients: List[Dict[str, str]],
                  subject_template: str,
                  body_text_template: str,
                  body_html_template: Optional[str] = None,
                  from_name: Optional[str] = None,
                  fail_fast: bool = False) -> Dict[str, bool]:
        """Send personalised emails to a list of recipients.

        Each recipient dict must contain at least an 'email' key.
        Additional keys are used as placeholders in templates.

        Args:
            recipients: List of recipient data dicts.
            subject_template: Subject with placeholders.
            body_text_template: Plain text body with placeholders.
            body_html_template: Optional HTML body with placeholders.
            from_name: Optional display name for sender.
            fail_fast: If True, stop on first failure.

        Returns:
            Dict mapping email address -> success status.
        """
        results: Dict[str, bool] = {}
        for idx, recipient in enumerate(recipients, 1):
            email = recipient.get("email")
            if not email:
                logger.warning("Skipping recipient %d: no email field.", idx)
                continue

            # Prepare placeholders (including a 'from_name' if provided)
            placeholders = recipient.copy()
            if from_name:
                placeholders["from_name"] = from_name

            subject = self.render_template(subject_template, placeholders)
            body_text = self.render_template(body_text_template, placeholders)
            body_html = None
            if body_html_template:
                body_html = self.render_template(body_html_template, placeholders)

            success = self.send_email(
                to_email=email,
                subject=subject,
                body_text=body_text,
                body_html=body_html,
                to_name=recipient.get("name"),
            )
            results[email] = success
            if not success and fail_fast:
                logger.error("Stopping bulk send due to failure on %s", email)
                break

        logger.info("Bulk send completed: %d success, %d failures",
                     sum(1 for v in results.values() if v),
                     sum(1 for v in results.values() if not v))
        return results


if __name__ == "__main__":
    # Example usage (configure SMTP via environment variables)
    bot = EmailAutomationBot()

    # Sample CSV: recipients.csv with columns: name,email,custom_field
    # For demonstration, create a small in-memory list:
    demo_recipients = [
        {"name": "Alice", "email": "alice@example.com", "company": "ACME"},
        {"name": "Bob", "email": "bob@example.com", "company": "BetaCorp"},
    ]

    subject = "Hello {name}, special offer for {company}"
    body_txt = "Dear {name},\n\nWe have an exclusive deal for {company}.\nBest, {from_name}"
    body_html = None  # optional

    try:
        results = bot.send_bulk(demo_recipients, subject, body_txt, body_html, from_name="SenderBot")
        for email, success in results.items():
            status = "OK" if success else "FAILED"
            print(f"{email}: {status}")
    except Exception as e:
        logger.exception("Bulk email sending failed: %s", e)