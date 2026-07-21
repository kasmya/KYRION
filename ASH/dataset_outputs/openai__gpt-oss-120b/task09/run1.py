"""
email_automation_bot.py

A simple email automation utility that reads recipient data from a CSV file,
renders a Jinja2‑based email template with per‑recipient placeholders, sends
the emails via a secure SMTP connection, and logs the results.

Only the Python standard library and the widely‑used ``jinja2`` package are
required.

Typical usage::

    from pathlib import Path
    from email_automation_bot import send_bulk_emails

    send_bulk_emails(
        smtp_server="smtp.example.com",
        smtp_port=465,
        smtp_user="user@example.com",
        smtp_password="super‑secret",
        sender="user@example.com",
        csv_path=Path("recipients.csv"),
        template_path=Path("email_template.txt"),
        log_path=Path("email_sends.log"),
    )
"""

from __future__ import annotations

import csv
import logging
import ssl
import smtplib
from pathlib import Path
from typing import List, Dict, Any

from email.message import EmailMessage

from jinja2 import Environment, FileSystemLoader, Template, TemplateError

__all__ = [
    "load_recipients",
    "load_template",
    "render_email",
    "send_email",
    "configure_logger",
    "send_bulk_emails",
]


def configure_logger(log_path: Path) -> logging.Logger:
    """
    Configure a file logger for the module.

    Args:
        log_path: Destination path for the log file.

    Returns:
        A configured ``logging.Logger`` instance.
    """
    logger = logging.getLogger("email_automation_bot")
    logger.setLevel(logging.INFO)

    # Avoid adding multiple handlers if configure_logger is called repeatedly.
    if not logger.handlers:
        handler = logging.FileHandler(log_path, encoding="utf-8")
        formatter = logging.Formatter(
            fmt="%(asctime)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger


def load_recipients(csv_path: Path) -> List[Dict[str, str]]:
    """
    Load recipient data from a CSV file.

    The CSV must contain a header row. Each row is converted to a ``dict``
    mapping column names to string values.

    Args:
        csv_path: Path to the CSV file.

    Returns:
        A list of dictionaries, one per recipient.

    Raises:
        FileNotFoundError: If ``csv_path`` does not exist.
        csv.Error: If the CSV cannot be parsed.
    """
    if not csv_path.is_file():
        raise FileNotFoundError(f"Recipient CSV not found: {csv_path}")

    recipients: List[Dict[str, str]] = []
    try:
        with csv_path.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Normalise all values to strings (CSV may return None)
                cleaned = {k: (v if v is not None else "") for k, v in row.items()}
                recipients.append(cleaned)
    except csv.Error as exc:
        raise csv.Error(f"Error parsing CSV {csv_path}: {exc}") from exc

    return recipients


def load_template(template_path: Path) -> Template:
    """
    Load a Jinja2 template from a file.

    Args:
        template_path: Path to the template file.

    Returns:
        A compiled Jinja2 ``Template`` object.

    Raises:
        FileNotFoundError: If the template file does not exist.
        TemplateError: If Jinja2 fails to compile the template.
    """
    if not template_path.is_file():
        raise FileNotFoundError(f"Template file not found: {template_path}")

    env = Environment(
        loader=FileSystemLoader(searchpath=str(template_path.parent)),
        autoescape=False,  # Email bodies are plain text or already escaped HTML
    )
    try:
        template = env.get_template(template_path.name)
    except TemplateError as exc:
        raise TemplateError(f"Failed to load template {template_path}: {exc}") from exc

    return template


def render_email(template: Template, context: Dict[str, Any]) -> str:
    """
    Render the email body using the supplied template and context.

    Args:
        template: A pre‑compiled Jinja2 template.
        context: Mapping of placeholder names to values for this recipient.

    Returns:
        Rendered email body as a string.

    Raises:
        TemplateError: If rendering fails.
    """
    try:
        return template.render(**context)
    except TemplateError as exc:
        raise TemplateError(f"Template rendering failed for context {context}: {exc}") from exc


def send_email(
    smtp: smtplib.SMTP_SSL,
    sender: str,
    recipient: str,
    subject: str,
    body: str,
) -> None:
    """
    Send a single email using an existing SMTP connection.

    Args:
        smtp: An active ``smtplib.SMTP_SSL`` connection.
        sender: The email address of the sender.
        recipient: The recipient's email address.
        subject: Subject line for the email.
        body: Email body (plain text).

    Raises:
        smtplib.SMTPException: If sending fails.
    """
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = recipient
    msg["Subject"] = subject
    msg.set_content(body)

    try:
        smtp.send_message(msg)
    except smtplib.SMTPException as exc:
        raise smtplib.SMTPException(f"Failed to send email to {recipient}: {exc}") from exc


def send_bulk_emails(
    *,
    smtp_server: str,
    smtp_port: int,
    smtp_user: str,
    smtp_password: str,
    sender: str,
    csv_path: Path,
    template_path: Path,
    log_path: Path,
    subject: str = "Your Subject Here",
) -> None:
    """
    Orchestrate the bulk email sending process.

    The function reads recipient data, renders the template for each recipient,
    sends the email through a secure SMTP connection, and logs successes and
    failures.

    Args:
        smtp_server: Hostname of the SMTP server.
        smtp_port: Port number (usually 465 for SSL).
        smtp_user: Username for SMTP authentication.
        smtp_password: Password for SMTP authentication.
        sender: Email address shown in the ``From`` header.
        csv_path: Path to the CSV file containing recipient data.
        template_path: Path to the Jinja2 template file.
        log_path: Path where send logs are written.
        subject: Subject line to use for all emails.

    Raises:
        RuntimeError: If a fatal error occurs that prevents further processing.
    """
    logger = configure_logger(log_path)

    try:
        recipients = load_recipients(csv_path)
        template = load_template(template_path)
    except (FileNotFoundError, csv.Error, TemplateError) as exc:
        logger.error("Initialisation failed: %s", exc)
        raise RuntimeError("Failed to initialise email automation") from exc

    context_ssl = ssl.create_default_context()
    try:
        with smtplib.SMTP_SSL(smtp_server, smtp_port, context=context_ssl) as smtp:
            try:
                smtp.login(smtp_user, smtp_password)
            except smtplib.SMTPException as exc:
                logger.error("SMTP authentication failed: %s", exc)
                raise RuntimeError("SMTP login failed") from exc

            for recipient_data in recipients:
                recipient_email = recipient_data.get("email")
                if not recipient_email:
                    logger.warning("Skipping row without 'email' field: %s", recipient_data)
                    continue

                try:
                    body = render_email(template, recipient_data)
                    send_email(smtp, sender, recipient_email, subject, body)
                    logger.info("Email sent to %s", recipient_email)
                except (TemplateError, smtplib.SMTPException) as exc:
                    logger.error("Failed to send email to %s: %s", recipient_email, exc)

    except smtplib.SMTPException as exc:
        logger.error("SMTP connection error: %s", exc)
        raise RuntimeError("SMTP connection failed") from exc