"""
Email Automation Bot

This module provides functionality to send templated emails to a list of recipients
read from a CSV file. It supports SMTP with TLS/SSL, placeholder rendering, and
comprehensive logging.

Security Best Practices:
- Credentials are read from environment variables, never hardcoded.
- Uses TLS (STARTTLS) or SSL for encrypted connections.
- Validates email format and sanitizes inputs.
- Logs successes and failures without exposing sensitive data.

Usage:
    Set environment variables:
        SMTP_PASSWORD: Password for the SMTP account.
    Run the script with required arguments:
        python email_bot.py --csv recipients.csv --template template.txt \
            --smtp-host smtp.example.com --smtp-port 587 \
            --username sender@example.com --from-addr sender@example.com
"""

import argparse
import csv
import logging
import os
import re
import smtplib
import ssl
import sys
from email.message import EmailMessage
from pathlib import Path
from string import Template
from typing import Dict, List, Optional, Tuple


def parse_args() -> argparse.Namespace:
    """
    Parse command-line arguments for the email bot.

    Returns:
        argparse.Namespace: Parsed arguments.
    """
    parser = argparse.ArgumentParser(
        description="Send templated emails to recipients from a CSV file."
    )
    parser.add_argument(
        "--csv",
        type=Path,
        required=True,
        help="Path to CSV file containing recipients. Must have an 'email' column.",
    )
    parser.add_argument(
        "--template",
        type=Path,
        required=True,
        help="Path to email template file. First line: subject, rest: body.",
    )
    parser.add_argument(
        "--smtp-host",
        type=str,
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
        "--username",
        type=str,
        required=True,
        help="SMTP username (usually the sender email).",
    )
    parser.add_argument(
        "--from-addr",
        type=str,
        required=True,
        help="Sender email address.",
    )
    parser.add_argument(
        "--use-tls",
        action="store_true",
        default=True,
        help="Use STARTTLS (default: True).",
    )
    parser.add_argument(
        "--use-ssl",
        action="store_true",
        default=False,
        help="Use SMTP_SSL (implicit TLS on port 465). Overrides --use-tls.",
    )
    parser.add_argument(
        "--log-file",
        type=Path,
        default=Path("email_bot.log"),
        help="Path to log file (default: email_bot.log).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Simulate sending without connecting to SMTP.",
    )
    return parser.parse_args()


def setup_logging(log_file: Path) -> logging.Logger:
    """
    Configure logging to file and console.

    Args:
        log_file: Path to the log file.

    Returns:
        logging.Logger: Configured logger instance.
    """
    logger = logging.getLogger("email_bot")
    logger.setLevel(logging.INFO)

    # Avoid duplicate handlers if called multiple times
    if not logger.handlers:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
        )
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
    return logger


def read_recipients(csv_path: Path) -> List[Dict[str, str]]:
    """
    Read recipients from a CSV file.

    Args:
        csv_path: Path to the CSV file.

    Returns:
        List of dictionaries, each representing a recipient row.

    Raises:
        FileNotFoundError: If the CSV file does not exist.
        ValueError: If the CSV lacks an 'email' column.
    """
    if not csv_path.is_file():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    recipients: List[Dict[str, str]] = []
    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if "email" not in reader.fieldnames:
            raise ValueError("CSV must contain an 'email' column.")
        for row in reader:
            # Strip whitespace from all fields
            cleaned = {k: v.strip() for k, v in row.items()}
            recipients.append(cleaned)
    return recipients


def load_template(template_path: Path) -> Tuple[str, str]:
    """
    Load email template from a file.

    The first line is treated as the subject template.
    The remaining lines constitute the body template.

    Args:
        template_path: Path to the template file.

    Returns:
        Tuple of (subject_template, body_template).

    Raises:
        FileNotFoundError: If the template file does not exist.
    """
    if not template_path.is_file():
        raise FileNotFoundError(f"Template file not found: {template_path}")

    with template_path.open("r", encoding="utf-8") as f:
        lines = f.readlines()

    if not lines:
        raise ValueError("Template file is empty.")

    subject_template = lines[0].rstrip("\n")
    body_template = "".join(lines[1:]).lstrip("\n")
    return subject_template, body_template


def render_email(
    subject_template: str, body_template: str, recipient: Dict[str, str]
) -> Tuple[str, str]:
    """
    Render email subject and body by substituting placeholders.

    Placeholders use Python's `string.Template` syntax (e.g., $name or ${name}).

    Args:
        subject_template: Subject line with placeholders.
        body_template: Body text with placeholders.
        recipient: Dictionary of placeholder values.

    Returns:
        Tuple of (rendered_subject, rendered_body).
    """
    subject_tmpl = Template(subject_template)
    body_tmpl = Template(body_template)
    # safe_substitute leaves missing placeholders unchanged
    rendered_subject = subject_tmpl.safe_substitute(recipient)
    rendered_body = body_tmpl.safe_substitute(recipient)
    return rendered_subject, rendered_body


def validate_email(email: str) -> bool:
    """
    Basic email format validation.

    Args:
        email: Email address string.

    Returns:
        True if the email matches a simple RFC 5322 pattern, False otherwise.
    """
    pattern = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
    return re.match(pattern, email) is not None


def send_email(
    smtp_host: str,
    smtp_port: int,
    username: str,
    password: str,
    from_addr: str,
    to_addr: str,
    subject: str,
    body: str,
    use_tls: bool = True,
    use_ssl: bool = False,
) -> bool:
    """
    Send an email via SMTP.

    Args:
        smtp_host: SMTP server hostname.
        smtp_port: SMTP server port.
        username: SMTP username.
        password: SMTP password.
        from_addr: Sender email address.
        to_addr: Recipient email address.
        subject: Email subject.
        body: Email body (plain text).
        use_tls: Whether to use STARTTLS (explicit TLS).
        use_ssl: Whether to use SMTP_SSL (implicit TLS).

    Returns:
        True if sent successfully, False otherwise.
    """
    msg = EmailMessage()
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg.set_content(body)

    try:
        if use_ssl:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(smtp_host, smtp_port, context=context) as server:
                server.login(username, password)
                server.send_message(msg)
        else:
            with smtplib.SMTP(smtp_host, smtp_port) as server:
                if use_tls:
                    context = ssl.create_default_context()
                    server.starttls(context=context)
                server.login(username, password)
                server.send_message(msg)
        return True
    except (smtplib.SMTPException, ConnectionError, TimeoutError, ssl.SSLError) as e:
        # Log the exception type and message without sensitive data
        logging.getLogger("email_bot").debug("SMTP error: %s", e)
        return False


def main() -> None:
    """
    Main entry point for the email automation bot.
    """
    args = parse_args()
    logger = setup_logging(args.log_file)

    # Retrieve password from environment variable
    password = os.environ.get("SMTP_PASSWORD")
    if not password:
        logger.error("Environment variable SMTP_PASSWORD not set.")
        sys.exit(1)

    try:
        recipients = read_recipients(args.csv)
    except (FileNotFoundError, ValueError) as e:
        logger.error("Failed to read recipients: %s", e)
        sys.exit(1)

    try:
        subject_template, body_template = load_template(args.template)
    except (FileNotFoundError, ValueError) as e:
        logger.error("Failed to load template: %s", e)
        sys.exit(1)

    logger.info("Starting email job. Recipients: %d", len(recipients))
    sent_count = 0
    failed_count = 0

    for idx, recipient in enumerate(recipients, start=1):
        email = recipient.get("email", "")
        if not validate_email(email):
            logger.warning("Row %d: Invalid email address '%s'. Skipping.", idx, email)
            failed_count += 1
            continue

        rendered_subject, rendered_body = render_email(
            subject_template, body_template, recipient
        )

        if args.dry_run:
            logger.info(
                "DRY RUN - To: %s | Subject: %s", email, rendered_subject
            )
            sent_count += 1
            continue

        success = send_email(
            smtp_host=args.smtp_host,
            smtp_port=args.smtp_port,
            username=args.username,
            password=password,
            from_addr=args.from_addr,
            to_addr=email,
            subject=rendered_subject,
            body=rendered_body,
            use_tls=args.use_tls,
            use_ssl=args.use_ssl,
        )

        if success:
            logger.info("Sent to %s", email)
            sent_count += 1
        else:
            logger.error("Failed to send to %s", email)
            failed_count += 1

    logger.info("Job completed. Sent: %d, Failed: %d", sent_count, failed_count)


if __name__ == "__main__":
    main()