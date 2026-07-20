#!/usr/bin/env python3
"""
Email Automation Bot

Features:
- Load recipient list from a CSV file.
- Render a plain‑text email template with placeholders (e.g. {{name}}).
- Send personalised emails via SMTP with TLS.
- Log each sent email (including failures) to a rotating file logger.

Only the Python standard library is used.
"""

import csv
import logging
import os
import smtplib
import ssl
import sys
from argparse import ArgumentParser
from dataclasses import dataclass
from email.message import EmailMessage
from string import Template
from typing import Dict, List, Mapping, NamedTuple, Optional

# --------------------------------------------------------------------------- #
# Logging configuration
# --------------------------------------------------------------------------- #
LOG_FORMAT = "%(asctime)s %(levelname)-8s %(name)s %(message)s"
logging.basicConfig(
    level=logging.INFO,
    format=LOG_FORMAT,
    handlers=[
        logging.FileHandler("email_bot.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("email_bot")


# --------------------------------------------------------------------------- #
# Data structures
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class SMTPConfig:
    """Configuration required to connect to an SMTP server."""

    host: str
    port: int
    username: str
    password: str
    use_tls: bool = True
    timeout: Optional[int] = 30


class Recipient(NamedTuple):
    """Immutable representation of a CSV row containing at least an email."""

    email: str
    name: str
    # Additional fields can be accessed via the underlying mapping
    extra: Mapping[str, str] = {}


# --------------------------------------------------------------------------- #
# Core functionality
# --------------------------------------------------------------------------- #
def load_recipients(csv_path: str) -> List[Recipient]:
    """
    Load recipients from a CSV file.

    The CSV must contain a column named ``email``.  Any other columns are
    considered placeholders for the template (e.g. ``name``).

    Args:
        csv_path: Path to the CSV file.

    Returns:
        List of :class:`Recipient` objects.

    Raises:
        FileNotFoundError: If the CSV file does not exist.
        ValueError: If the required ``email`` column is missing.
    """
    recipients: List[Recipient] = []
    with open(csv_path, newline="", encoding="utf-8") as fp:
        reader = csv.DictReader(fp)
        if "email" not in reader.fieldnames:
            raise ValueError("CSV must contain an 'email' column.")
        for row in reader:
            email = row.pop("email").strip()
            name = row.pop("name", "").strip()
            recipients.append(Recipient(email=email, name=name, extra=row))
    logger.info("Loaded %d recipient(s) from %s", len(recipients), csv_path)
    return recipients


def render_template(template_str: str, context: Mapping[str, str]) -> str:
    """
    Render a template string using :class:`string.Template`.

    Placeholders are written as ``${placeholder}`` according to the
    ``Template`` syntax.

    Args:
        template_str: The raw template text.
        context: Mapping of placeholder names to their replacement values.

    Returns:
        Rendered string.

    Raises:
        KeyError: If a placeholder is missing in ``context``.
    """
    try:
        template = Template(template_str)
        return template.substitute(context)
    except KeyError as exc:
        missing = exc.args[0]
        raise KeyError(f"Missing placeholder '{missing}' for template rendering.") from exc


def send_email(
    smtp_cfg: SMTPConfig,
    sender: str,
    recipient: Recipient,
    subject: str,
    body: str,
) -> None:
    """
    Send a single email via SMTP.

    Args:
        smtp_cfg: SMTP configuration.
        sender: Email address appearing in the ``From`` header.
        recipient: Recipient data.
        subject: Email subject.
        body: Email body (plain text).

    Raises:
        smtplib.SMTPException: For any SMTP‑related errors.
    """
    message = EmailMessage()
    message["From"] = sender
    message["To"] = recipient.email
    message["Subject"] = subject
    message.set_content(body)

    context = ssl.create_default_context()
    try:
        with smtplib.SMTP(smtp_cfg.host, smtp_cfg.port, timeout=smtp_cfg.timeout) as server:
            if smtp_cfg.use_tls:
                server.starttls(context=context)
                logger.debug("Started TLS with %s:%s", smtp_cfg.host, smtp_cfg.port)
            server.login(smtp_cfg.username, smtp_cfg.password)
            server.send_message(message)
        logger.info("Email sent to %s <%s>", recipient.name, recipient.email)
    except smtplib.SMTPException as exc:
        logger.error(
            "Failed to send email to %s <%s>: %s", recipient.name, recipient.email, exc
        )
        raise


def build_smtp_config_from_env() -> SMTPConfig:
    """
    Construct :class:`SMTPConfig` from environment variables.

    Expected variables:
        - SMTP_HOST
        - SMTP_PORT
        - SMTP_USER
        - SMTP_PASS
        - SMTP_TLS (optional, defaults to ``1``)

    Returns:
        Filled :class:`SMTPConfig` instance.

    Raises:
        EnvironmentError: If any required variable is missing or malformed.
    """
    try:
        host = os.environ["SMTP_HOST"]
        port = int(os.environ.get("SMTP_PORT", "587"))
        username = os.environ["SMTP_USER"]
        password = os.environ["SMTP_PASS"]
        use_tls = os.environ.get("SMTP_TLS", "1") not in {"0", "false", "False"}
        return SMTPConfig(host=host, port=port, username=username, password=password, use_tls=use_tls)
    except KeyError as exc:
        raise EnvironmentError(f"Missing required SMTP environment variable: {exc}") from exc
    except ValueError as exc:
        raise EnvironmentError("SMTP_PORT must be an integer.") from exc


def main() -> None:
    """Entry point for the CLI."""
    parser = ArgumentParser(description="Send personalised emails from a CSV list.")
    parser.add_argument(
        "csv_path", help="Path to CSV file containing at least an 'email' column."
    )
    parser.add_argument(
        "template_path", help="Path to a plain‑text email template file."
    )
    parser.add_argument(
        "--subject", required=True, help="Subject line for the email."
    )
    parser.add_argument(
        "--sender", required=True, help="Sender email address (From header)."
    )
    args = parser.parse_args()

    # Load configuration, template and recipients
    smtp_cfg = build_smtp_config_from_env()
    try:
        with open(args.template_path, "r", encoding="utf-8") as f:
            template_str = f.read()
    except OSError as exc:
        logger.critical("Unable to read template file: %s", exc)
        sys.exit(1)

    try:
        recipients = load_recipients(args.csv_path)
    except Exception as exc:
        logger.critical("Failed to load recipients: %s", exc)
        sys.exit(1)

    # Process each recipient
    for recipient in recipients:
        # Merge built‑in fields with any extra columns from the CSV
        context: Dict[str, str] = {
            "email": recipient.email,
            "name": recipient.name,
            **recipient.extra,
        }
        try:
            body = render_template(template_str, context)
        except KeyError as exc:
            logger.error("Skipping %s <%s>: %s", recipient.name, recipient.email, exc)
            continue

        try:
            send_email(
                smtp_cfg=smtp_cfg,
                sender=args.sender,
                recipient=recipient,
                subject=args.subject,
                body=body,
            )
        except smtplib.SMTPException:
            # Error already logged inside ``send_email``; continue with next.
            continue


if __name__ == "__main__":
    main()