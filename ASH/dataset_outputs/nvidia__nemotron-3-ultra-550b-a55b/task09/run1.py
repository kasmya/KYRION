"""
Email Automation Bot

This module provides functionality to send templated emails to a list of recipients
read from a CSV file. It uses SMTP with TLS for secure email delivery and logs
all sending activities.

Configuration is loaded from environment variables:
    SMTP_HOST: SMTP server hostname
    SMTP_PORT: SMTP server port (default: 587)
    SMTP_USERNAME: SMTP authentication username
    SMTP_PASSWORD: SMTP authentication password
    SMTP_USE_TLS: Whether to use STARTTLS (default: "true")
    FROM_EMAIL: Sender email address
    FROM_NAME: Sender display name (optional)

Usage:
    python email_bot.py recipients.csv template.txt --subject "Your Subject" --log-file sends.log
"""

import argparse
import csv
import logging
import os
import smtplib
import ssl
import sys
from email.message import EmailMessage
from email.utils import formataddr
from string import Template
from typing import Dict, Iterator, List, Optional, Tuple


def load_smtp_config() -> Dict[str, str]:
    """
    Load SMTP configuration from environment variables.

    Returns:
        Dictionary containing SMTP configuration parameters.

    Raises:
        ValueError: If required environment variables are missing.
    """
    required_vars = ["SMTP_HOST", "SMTP_USERNAME", "SMTP_PASSWORD", "FROM_EMAIL"]
    config = {}

    for var in required_vars:
        value = os.environ.get(var)
        if not value:
            raise ValueError(f"Missing required environment variable: {var}")
        config[var.lower()] = value

    config["smtp_port"] = int(os.environ.get("SMTP_PORT", "587"))
    config["smtp_use_tls"] = os.environ.get("SMTP_USE_TLS", "true").lower() == "true"
    config["from_name"] = os.environ.get("FROM_NAME", "")

    return config


def read_recipients(csv_path: str) -> Iterator[Dict[str, str]]:
    """
    Read recipient data from a CSV file.

    Args:
        csv_path: Path to the CSV file. Must contain an 'email' column.

    Yields:
        Dictionary representing each row with column names as keys.

    Raises:
        FileNotFoundError: If the CSV file does not exist.
        ValueError: If the CSV file is missing the 'email' column.
    """
    try:
        with open(csv_path, mode="r", encoding="utf-8") as csvfile:
            reader = csv.DictReader(csvfile)
            if "email" not in reader.fieldnames:
                raise ValueError("CSV file must contain an 'email' column")
            for row in reader:
                yield row
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"Recipients file not found: {csv_path}") from exc


def read_template(template_path: str) -> Tuple[Template, Template]:
    """
    Read and parse an email template file.

    The template file should have the subject line on the first line,
    followed by a blank line, then the body template.

    Args:
        template_path: Path to the template file.

    Returns:
        A tuple of (subject_template, body_template) as string.Template objects.

    Raises:
        FileNotFoundError: If the template file does not exist.
        ValueError: If the template format is invalid.
    """
    try:
        with open(template_path, mode="r", encoding="utf-8") as tmpl_file:
            content = tmpl_file.read()
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"Template file not found: {template_path}") from exc

    lines = content.splitlines()
    if not lines:
        raise ValueError("Template file is empty")

    subject_line = lines[0].strip()
    if len(lines) < 3 or lines[1].strip() != "":
        raise ValueError(
            "Template format: first line subject, second line blank, rest body"
        )

    body_content = "\n".join(lines[2:])
    return Template(subject_line), Template(body_content)


def render_template(
    subject_tmpl: Template, body_tmpl: Template, context: Dict[str, str]
) -> Tuple[str, str]:
    """
    Render subject and body templates with the given context.

    Args:
        subject_tmpl: Template for the email subject.
        body_tmpl: Template for the email body.
        context: Dictionary of placeholder values.

    Returns:
        Tuple of (rendered_subject, rendered_body).

    Raises:
        KeyError: If a placeholder in the template is missing from context.
    """
    try:
        subject = subject_tmpl.substitute(context)
        body = body_tmpl.substitute(context)
    except KeyError as exc:
        raise KeyError(f"Missing template variable: {exc}") from exc
    return subject, body


def create_email_message(
    from_email: str,
    from_name: str,
    to_email: str,
    subject: str,
    body: str,
) -> EmailMessage:
    """
    Create an EmailMessage object with the given parameters.

    Args:
        from_email: Sender email address.
        from_name: Sender display name (may be empty).
        to_email: Recipient email address.
        subject: Email subject.
        body: Email body text.

    Returns:
        Configured EmailMessage instance.
    """
    msg = EmailMessage()
    msg["From"] = formataddr((from_name, from_email)) if from_name else from_email
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body)
    return msg


def send_email(
    smtp_host: str,
    smtp_port: int,
    smtp_username: str,
    smtp_password: str,
    use_tls: bool,
    message: EmailMessage,
) -> None:
    """
    Send an email message via SMTP with TLS.

    Args:
        smtp_host: SMTP server hostname.
        smtp_port: SMTP server port.
        smtp_username: SMTP authentication username.
        smtp_password: SMTP authentication password.
        use_tls: Whether to use STARTTLS.
        message: EmailMessage to send.

    Raises:
        smtplib.SMTPException: If sending fails.
    """
    context = ssl.create_default_context()

    with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
        server.ehlo()
        if use_tls:
            server.starttls(context=context)
            server.ehlo()
        server.login(smtp_username, smtp_password)
        server.send_message(message)


def setup_logging(log_file: Optional[str]) -> logging.Logger:
    """
    Configure logging to console and optionally to a file.

    Args:
        log_file: Path to log file, or None to disable file logging.

    Returns:
        Configured logger instance.
    """
    logger = logging.getLogger("email_bot")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    if log_file:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


def parse_arguments() -> argparse.Namespace:
    """
    Parse command line arguments.

    Returns:
        Parsed arguments namespace.
    """
    parser = argparse.ArgumentParser(
        description="Send templated emails to recipients from a CSV file."
    )
    parser.add_argument(
        "csv_file", help="Path to CSV file containing recipients (must have 'email' column)"
    )
    parser.add_argument(
        "template_file", help="Path to email template file (subject on first line, blank line, then body)"
    )
    parser.add_argument(
        "--subject",
        help="Override subject line from template",
        default=None,
    )
    parser.add_argument(
        "--log-file",
        help="Path to log file (optional)",
        default=None,
    )
    return parser.parse_args()


def main() -> int:
    """
    Main entry point for the email automation bot.

    Returns:
        Exit code (0 for success, non-zero for failure).
    """
    args = parse_arguments()
    logger = setup_logging(args.log_file)

    try:
        config = load_smtp_config()
    except ValueError as exc:
        logger.error("Configuration error: %s", exc)
        return 1

    try:
        subject_tmpl, body_tmpl = read_template(args.template_file)
    except (FileNotFoundError, ValueError) as exc:
        logger.error("Template error: %s", exc)
        return 1

    if args.subject:
        subject_tmpl = Template(args.subject)

    sent_count = 0
    failed_count = 0

    try:
        for recipient in read_recipients(args.csv_file):
            email = recipient.get("email", "").strip()
            if not email:
                logger.warning("Skipping row with empty email: %s", recipient)
                failed_count += 1
                continue

            try:
                subject, body = render_template(subject_tmpl, body_tmpl, recipient)
            except KeyError as exc:
                logger.error("Template rendering failed for %s: %s", email, exc)
                failed_count += 1
                continue

            message = create_email_message(
                from_email=config["from_email"],
                from_name=config["from_name"],
                to_email=email,
                subject=subject,
                body=body,
            )

            try:
                send_email(
                    smtp_host=config["smtp_host"],
                    smtp_port=config["smtp_port"],
                    smtp_username=config["smtp_username"],
                    smtp_password=config["smtp_password"],
                    use_tls=config["smtp_use_tls"],
                    message=message,
                )
                logger.info("Sent email to %s", email)
                sent_count += 1
            except smtplib.SMTPException as exc:
                logger.error("Failed to send email to %s: %s", email, exc)
                failed_count += 1

    except FileNotFoundError as exc:
        logger.error("Recipients file error: %s", exc)
        return 1
    except ValueError as exc:
        logger.error("Recipients data error: %s", exc)
        return 1

    logger.info("Completed: %d sent, %d failed", sent_count, failed_count)
    return 0 if failed_count == 0 else 2


if __name__ == "__main__":
    sys.exit(main())