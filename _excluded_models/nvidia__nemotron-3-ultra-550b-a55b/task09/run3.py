"""
Email Automation Bot

A self-contained module for sending templated emails to recipients listed in a CSV file.
Uses SMTP with TLS, reads credentials from environment variables, and logs all operations.

Configuration is expected via environment variables:
- SMTP_HOST: SMTP server hostname
- SMTP_PORT: SMTP server port (default 587)
- SMTP_USERNAME: SMTP authentication username
- SMTP_PASSWORD: SMTP authentication password
- SMTP_USE_TLS: Whether to use STARTTLS (default True)

Example usage:
    python email_bot.py recipients.csv template.txt

CSV format: must contain at least an 'email' column. Other columns are used as template variables.
Template format: first line is subject, remaining lines are body. Placeholders use {variable} syntax.
"""

import csv
import logging
import os
import smtplib
import sys
from email.message import EmailMessage
from pathlib import Path
from string import Template
from typing import Any, Dict, List, Optional, Tuple

# Configure module logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
logger.addHandler(handler)


def read_recipients(csv_path: str) -> List[Dict[str, str]]:
    """
    Read recipient data from a CSV file.

    Args:
        csv_path: Path to the CSV file containing recipient data.

    Returns:
        List of dictionaries, each representing a recipient with column headers as keys.

    Raises:
        FileNotFoundError: If the CSV file does not exist.
        ValueError: If the CSV file is missing the required 'email' column.
        csv.Error: If there is an error parsing the CSV file.
    """
    path = Path(csv_path)
    if not path.is_file():
        logger.error("Recipient CSV file not found: %s", csv_path)
        raise FileNotFoundError(f"Recipient CSV file not found: {csv_path}")

    recipients: List[Dict[str, str]] = []
    try:
        with path.open(newline="", encoding="utf-8") as csvfile:
            reader = csv.DictReader(csvfile)
            if "email" not in reader.fieldnames:
                logger.error("CSV missing required 'email' column")
                raise ValueError("CSV must contain an 'email' column")
            for row in reader:
                # Strip whitespace from all values
                cleaned_row = {k: v.strip() for k, v in row.items()}
                recipients.append(cleaned_row)
        logger.info("Loaded %d recipients from %s", len(recipients), csv_path)
        return recipients
    except csv.Error as exc:
        logger.error("CSV parsing error: %s", exc)
        raise


def render_template(template_path: str, context: Dict[str, str]) -> Tuple[str, str]:
    """
    Render an email template with the given context.

    The template file must have the subject on the first line and the body on subsequent lines.
    Placeholders use Python's `string.Template` syntax (e.g., ${name} or $name).

    Args:
        template_path: Path to the template file.
        context: Dictionary mapping placeholder names to values.

    Returns:
        A tuple (subject, body) with placeholders substituted.

    Raises:
        FileNotFoundError: If the template file does not exist.
        ValueError: If the template file is empty or missing a subject line.
        KeyError: If a placeholder in the template is not provided in the context.
    """
    path = Path(template_path)
    if not path.is_file():
        logger.error("Template file not found: %s", template_path)
        raise FileNotFoundError(f"Template file not found: {template_path}")

    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.error("Error reading template file: %s", exc)
        raise

    lines = content.splitlines()
    if not lines:
        logger.error("Template file is empty")
        raise ValueError("Template file is empty")

    subject = lines[0].strip()
    body = "\n".join(lines[1:]).strip()

    if not subject:
        logger.error("Template missing subject line")
        raise ValueError("Template must have a subject on the first line")

    template_subject = Template(subject)
    template_body = Template(body)

    try:
        rendered_subject = template_subject.substitute(context)
        rendered_body = template_body.substitute(context)
    except KeyError as exc:
        logger.error("Missing template variable: %s", exc)
        raise

    logger.debug("Rendered subject: %s", rendered_subject)
    return rendered_subject, rendered_body


def build_smtp_config() -> Dict[str, Any]:
    """
    Build SMTP configuration from environment variables.

    Returns:
        Dictionary with keys: host, port, username, password, use_tls.

    Raises:
        ValueError: If required environment variables are missing.
    """
    host = os.getenv("SMTP_HOST")
    port_str = os.getenv("SMTP_PORT", "587")
    username = os.getenv("SMTP_USERNAME")
    password = os.getenv("SMTP_PASSWORD")
    use_tls_str = os.getenv("SMTP_USE_TLS", "true").lower()

    if not host:
        raise ValueError("SMTP_HOST environment variable is required")
    if not username:
        raise ValueError("SMTP_USERNAME environment variable is required")
    if not password:
        raise ValueError("SMTP_PASSWORD environment variable is required")

    try:
        port = int(port_str)
    except ValueError as exc:
        logger.error("Invalid SMTP_PORT: %s", port_str)
        raise ValueError(f"SMTP_PORT must be an integer: {port_str}") from exc

    use_tls = use_tls_str in ("1", "true", "yes", "on")

    return {
        "host": host,
        "port": port,
        "username": username,
        "password": password,
        "use_tls": use_tls,
    }


def send_email(
    smtp_config: Dict[str, Any],
    from_addr: str,
    to_addr: str,
    subject: str,
    body: str,
) -> None:
    """
    Send a single email via SMTP with TLS.

    Args:
        smtp_config: Dictionary with SMTP connection parameters.
        from_addr: Sender email address.
        to_addr: Recipient email address.
        subject: Email subject line.
        body: Email body text (plain text).

    Raises:
        smtplib.SMTPException: If the email cannot be sent.
        ConnectionError: If the SMTP server cannot be reached.
    """
    msg = EmailMessage()
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg.set_content(body)

    try:
        with smtplib.SMTP(smtp_config["host"], smtp_config["port"], timeout=30) as server:
            server.ehlo()
            if smtp_config["use_tls"]:
                server.starttls()
                server.ehlo()
            server.login(smtp_config["username"], smtp_config["password"])
            server.send_message(msg)
        logger.info("Email sent successfully to %s", to_addr)
    except smtplib.SMTPException as exc:
        logger.error("SMTP error sending to %s: %s", to_addr, exc)
        raise
    except OSError as exc:
        logger.error("Connection error sending to %s: %s", to_addr, exc)
        raise ConnectionError(f"Failed to connect to SMTP server: {exc}") from exc


def main(
    csv_path: str,
    template_path: str,
    from_addr: str,
    smtp_config: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Main entry point for the email automation bot.

    Reads recipients, renders the template for each, and sends the emails.

    Args:
        csv_path: Path to the CSV file with recipient data.
        template_path: Path to the email template file.
        from_addr: Sender email address.
        smtp_config: Optional SMTP configuration. If not provided, reads from environment.

    Raises:
        Exception: Any exception from underlying operations will be logged and re-raised.
    """
    if smtp_config is None:
        smtp_config = build_smtp_config()

    logger.info("Starting email automation bot")
    logger.info("SMTP server: %s:%d (TLS: %s)", smtp_config["host"], smtp_config["port"], smtp_config["use_tls"])

    try:
        recipients = read_recipients(csv_path)
    except Exception as exc:
        logger.critical("Failed to read recipients: %s", exc)
        raise

    success_count = 0
    failure_count = 0

    for recipient in recipients:
        email = recipient.get("email")
        if not email:
            logger.warning("Skipping recipient with missing email: %s", recipient)
            failure_count += 1
            continue

        try:
            subject, body = render_template(template_path, recipient)
            send_email(smtp_config, from_addr, email, subject, body)
            success_count += 1
        except Exception as exc:
            logger.error("Failed to send email to %s: %s", email, exc)
            failure_count += 1

    logger.info("Email automation completed. Success: %d, Failures: %d", success_count, failure_count)


if __name__ == "__main__":
    # Simple command-line interface for direct execution
    if len(sys.argv) != 3:
        print("Usage: python email_bot.py <recipients.csv> <template.txt>")
        print("Environment variables required: SMTP_HOST, SMTP_USERNAME, SMTP_PASSWORD")
        print("Optional: SMTP_PORT (default 587), SMTP_USE_TLS (default true)")
        sys.exit(1)

    csv_file = sys.argv[1]
    template_file = sys.argv[2]
    sender = os.getenv("SENDER_EMAIL")
    if not sender:
        logger.error("SENDER_EMAIL environment variable is required")
        sys.exit(1)

    try:
        main(csv_file, template_file, sender)
    except Exception as exc:
        logger.critical("Email automation failed: %s", exc)
        sys.exit(1)