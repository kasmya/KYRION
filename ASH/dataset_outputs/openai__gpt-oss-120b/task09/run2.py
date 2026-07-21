"""email_automation_bot.py

A lightweight email automation utility that reads recipient data from a CSV file,
renders a templated email using placeholders, sends the email via SMTP with TLS,
and logs each successful send. Designed with type hints, comprehensive docstrings,
and robust error handling while adhering to security best practices.

Dependencies:
- Python 3.8+
- Standard library only (no external packages required)

Usage example:
    from email_automation_bot import SMTPConfig, send_bulk_emails

    config = SMTPConfig(
        host="smtp.example.com",
        port=587,
        username="user@example.com",
        password=os.getenv("SMTP_PASSWORD"),
        use_tls=True,
    )
    send_bulk_emails(
        csv_path="recipients.csv",
        template_path="email_template.txt",
        smtp_config=config,
        sender="user@example.com",
        subject="Welcome, {{ name }}!",
    )
"""

from __future__ import annotations

import csv
import logging
import os
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path
from string import Template
from typing import Any, Dict, List

# --------------------------------------------------------------------------- #
# Logging configuration
# --------------------------------------------------------------------------- #
LOGGER = logging.getLogger(__name__)
if not LOGGER.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        fmt="%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    LOGGER.addHandler(handler)
    LOGGER.setLevel(logging.INFO)


# --------------------------------------------------------------------------- #
# Data structures
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class SMTPConfig:
    """Configuration required to connect to an SMTP server.

    Attributes:
        host: SMTP server hostname or IP address.
        port: Port number (usually 587 for STARTTLS or 465 for SSL).
        username: Account username (often the email address).
        password: Account password. Should be provided via environment variable
                  or a secure secret manager; never hard‑coded.
        use_tls: If True, initiate a STARTTLS session after connecting.
    """

    host: str
    port: int
    username: str
    password: str
    use_tls: bool = True


# --------------------------------------------------------------------------- #
# Core functionality
# --------------------------------------------------------------------------- #
def load_recipients(csv_path: str | Path) -> List[Dict[str, str]]:
    """Load recipient data from a CSV file.

    The CSV must contain a header row. Each row becomes a dictionary mapping
    column names to values.

    Args:
        csv_path: Path to the CSV file containing recipient information.

    Returns:
        A list of dictionaries, each representing a recipient.

    Raises:
        FileNotFoundError: If the CSV file does not exist.
        PermissionError: If the file cannot be read due to insufficient permissions.
        csv.Error: For malformed CSV content.
    """
    path = Path(csv_path)
    if not path.is_file():
        raise FileNotFoundError(f"CSV file not found: {path}")

    recipients: List[Dict[str, str]] = []
    try:
        with path.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row_number, row in enumerate(reader, start=2):  # start=2 accounts for header line
                if not row:
                    LOGGER.warning("Empty row encountered at line %d; skipping.", row_number)
                    continue
                recipients.append({k: v.strip() for k, v in row.items() if k})
    except PermissionError as exc:
        raise PermissionError(f"Cannot read CSV file {path}: {exc}") from exc
    except csv.Error as exc:
        raise csv.Error(f"Error parsing CSV file {path}: {exc}") from exc

    LOGGER.info("Loaded %d recipient(s) from %s.", len(recipients), path)
    return recipients


def render_template(template_str: str, context: Dict[str, Any]) -> str:
    """Render a template string with the provided context.

    Uses :class:`string.Template` for placeholder substitution. Placeholders
    are denoted by ``${variable}``. Missing placeholders raise a ``KeyError``.

    Args:
        template_str: Raw template text.
        context: Mapping of placeholder names to replacement values.

    Returns:
        Rendered string with all placeholders replaced.

    Raises:
        KeyError: If the template contains placeholders not present in ``context``.
        ValueError: If the template string is malformed.
    """
    try:
        tmpl = Template(template_str)
        return tmpl.substitute(context)
    except KeyError as exc:
        missing = exc.args[0]
        raise KeyError(f"Missing placeholder '{missing}' in context for template.") from exc
    except ValueError as exc:
        raise ValueError(f"Invalid template syntax: {exc}") from exc


def send_email(
    smtp_config: SMTPConfig,
    sender: str,
    recipient: str,
    subject: str,
    body: str,
) -> None:
    """Send a single email via SMTP with TLS (if configured).

    Args:
        smtp_config: SMTP connection parameters.
        sender: Email address of the sender (must match SMTP authentication).
        recipient: Destination email address.
        subject: Email subject line.
        body: Plain‑text email body.

    Raises:
        smtplib.SMTPException: For any SMTP‑related errors.
        ssl.SSLError: For TLS/SSL negotiation failures.
    """
    message = EmailMessage()
    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)

    context = ssl.create_default_context()
    try:
        with smtplib.SMTP(smtp_config.host, smtp_config.port, timeout=30) as server:
            server.ehlo()
            if smtp_config.use_tls:
                server.starttls(context=context)
                server.ehlo()
            if smtp_config.username and smtp_config.password:
                server.login(smtp_config.username, smtp_config.password)
            server.send_message(message)
        LOGGER.info("Email sent to %s", recipient)
    except (smtplib.SMTPException, ssl.SSLError) as exc:
        LOGGER.error("Failed to send email to %s: %s", recipient, exc)
        raise


def load_template(template_path: str | Path) -> str:
    """Read the raw template text from a file.

    Args:
        template_path: Path to the file containing the email template.

    Returns:
        The template as a string.

    Raises:
        FileNotFoundError: If the template file does not exist.
        PermissionError: If the file cannot be read.
        OSError: For other I/O related issues.
    """
    path = Path(template_path)
    if not path.is_file():
        raise FileNotFoundError(f"Template file not found: {path}")

    try:
        content = path.read_text(encoding="utf-8")
        LOGGER.debug("Loaded template from %s (size: %d bytes).", path, len(content))
        return content
    except PermissionError as exc:
        raise PermissionError(f"Cannot read template file {path}: {exc}") from exc
    except OSError as exc:
        raise OSError(f"Error reading template file {path}: {exc}") from exc


def send_bulk_emails(
    csv_path: str | Path,
    template_path: str | Path,
    smtp_config: SMTPConfig,
    sender: str,
    subject: str,
) -> None:
    """Orchestrate loading recipients, rendering templates, and sending emails.

    Args:
        csv_path: Path to CSV file with recipient data.
        template_path: Path to the email body template.
        smtp_config: SMTP connection configuration.
        sender: Email address used as the "From" field.
        subject: Subject line template (supports ``${placeholder}`` syntax).

    Raises:
        Exception: Propagates any exception raised during processing.
    """
    recipients = load_recipients(csv_path)
    raw_template = load_template(template_path)

    for recipient_data in recipients:
        # Ensure required fields exist
        if "email" not in recipient_data:
            LOGGER.warning("Recipient entry missing 'email' field; skipping: %s", recipient_data)
            continue

        # Render subject and body
        try:
            rendered_subject = render_template(subject, recipient_data)
            rendered_body = render_template(raw_template, recipient_data)
        except (KeyError, ValueError) as exc:
            LOGGER.error("Template rendering failed for %s: %s", recipient_data.get("email"), exc)
            continue

        try:
            send_email(
                smtp_config=smtp_config,
                sender=sender,
                recipient=recipient_data["email"],
                subject=rendered_subject,
                body=rendered_body,
            )
        except Exception:
            # Already logged inside send_email; continue with next recipient
            continue


# --------------------------------------------------------------------------- #
# Example entry‑point (executed when run as a script)
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        description="Send bulk templated emails from a CSV list."
    )
    parser.add_argument("csv", help="Path to CSV file with recipient data.")
    parser.add_argument("template", help="Path to email body template file.")
    parser.add_argument(
        "--subject",
        required=True,
        help="Subject line template (use ${placeholder} for variables).",
    )
    parser.add_argument(
        "--sender",
        required=True,
        help="Sender email address (must match SMTP credentials).",
    )
    parser.add_argument(
        "--smtp-host",
        required=True,
        help="SMTP server hostname.",
    )
    parser.add_argument(
        "--smtp-port",
        type=int,
        default=587,
        help="SMTP server port (default: 587).",
    )
    parser.add_argument(
        "--smtp-user",
        required=True,
        help="SMTP username.",
    )
    parser.add_argument(
        "--smtp-pass-env",
        default="SMTP_PASSWORD",
        help=(
            "Name of environment variable that holds the SMTP password. "
            "Do NOT pass passwords on the command line."
        ),
    )
    parser.add_argument(
        "--no-tls",
        action="store_true",
        help="Disable STARTTLS. Use only if the server requires plain connection.",
    )

    args = parser.parse_args()

    smtp_password = os.getenv(args.smtp_pass_env)
    if not smtp_password:
        LOGGER.error("SMTP password not found in environment variable '%s'.", args.smtp_pass_env)
        sys.exit(1)

    config = SMTPConfig(
        host=args.smtp_host,
        port=args.smtp_port,
        username=args.smtp_user,
        password=smtp_password,
        use_tls=not args.no_tls,
    )

    try:
        send_bulk_emails(
            csv_path=args.csv,
            template_path=args.template,
            smtp_config=config,
            sender=args.sender,
            subject=args.subject,
        )
    except Exception as exc:
        LOGGER.exception("Unhandled exception during bulk send: %s", exc)
        sys.exit(1)