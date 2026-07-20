#!/usr/bin/env python3
"""
Email Automation Bot
--------------------

Features:
- Reads recipients from a CSV file.
- Renders an email template with placeholders (e.g., $name).
- Sends emails via SMTP with TLS/SSL.
- Logs sent emails and errors.

Usage (as a script):
    python email_bot.py \
        --csv recipients.csv \
        --template email_template.txt \
        --subject "Your Subject Here" \
        --smtp-server smtp.example.com \
        --smtp-port 465 \
        --smtp-user your_user@example.com \
        [--smtp-password YOUR_PASSWORD] \
        [--log-file email_bot.log]

The SMTP password can also be supplied via the environment variable
SMTP_PASSWORD or will be prompted securely if omitted.
"""

import argparse
import csv
import logging
import os
import sys
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from string import Template
from typing import List, Mapping, Optional
from getpass import getpass
from datetime import datetime


# --------------------------------------------------------------------------- #
# Data models
# --------------------------------------------------------------------------- #
@dataclass
class SMTPConfig:
    """Configuration needed to connect to an SMTP server."""
    server: str
    port: int
    user: str
    password: str
    use_ssl: bool = True  # force SSL; can be overridden if needed


@dataclass
class Recipient:
    """A single email recipient with optional extra fields for templating."""
    email: str
    fields: Mapping[str, str]


# --------------------------------------------------------------------------- #
# CSV handling
# --------------------------------------------------------------------------- #
def load_recipients(csv_path: str) -> List[Recipient]:
    """
    Load recipients from a CSV file.

    The CSV must contain a column named 'email'. Other columns are treated as
    placeholder fields for the template.

    Args:
        csv_path: Path to the CSV file.

    Returns:
        List of Recipient objects.

    Raises:
        FileNotFoundError: If the CSV file does not exist.
        ValueError: If required columns are missing.
    """
    if not os.path.isfile(csv_path):
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    recipients: List[Recipient] = []
    with open(csv_path, newline='', encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if "email" not in reader.fieldnames:
            raise ValueError("CSV must contain an 'email' column.")
        for row in reader:
            email = row.pop("email").strip()
            if not email:
                continue  # skip empty rows
            recipients.append(Recipient(email=email, fields=row))
    return recipients


# --------------------------------------------------------------------------- #
# Template handling
# --------------------------------------------------------------------------- #
def load_template(template_path: str) -> Template:
    """
    Load an email template from a text file.

    Placeholders should follow the `${placeholder}` syntax compatible with
    ``string.Template``.

    Args:
        template_path: Path to the template file.

    Returns:
        A Template object.

    Raises:
        FileNotFoundError: If the template file does not exist.
    """
    if not os.path.isfile(template_path):
        raise FileNotFoundError(f"Template file not found: {template_path}")

    with open(template_path, "r", encoding="utf-8") as f:
        content = f.read()
    return Template(content)


def render_template(template: Template, mapping: Mapping[str, str]) -> str:
    """
    Render the template with the given mapping.

    Args:
        template: The Template object.
        mapping: Mapping of placeholder names to values.

    Returns:
        Rendered string.

    Raises:
        KeyError: If a placeholder is missing in the mapping.
    """
    try:
        return template.substitute(mapping)
    except KeyError as exc:
        missing = exc.args[0]
        raise KeyError(f"Missing placeholder '{missing}' for template rendering.") from exc


# --------------------------------------------------------------------------- #
# Email sending
# --------------------------------------------------------------------------- #
def create_email_message(
    from_addr: str,
    to_addr: str,
    subject: str,
    body: str,
    reply_to: Optional[str] = None,
) -> EmailMessage:
    """
    Build an EmailMessage object.

    Args:
        from_addr: Sender email address.
        to_addr: Recipient email address.
        subject: Email subject.
        body: Email body (plain text).
        reply_to: Optional Reply-To address.

    Returns:
        Configured EmailMessage instance.
    """
    msg = EmailMessage()
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg["Subject"] = subject
    if reply_to:
        msg["Reply-To"] = reply_to
    msg.set_content(body)
    return msg


def send_email(
    smtp_cfg: SMTPConfig,
    message: EmailMessage,
) -> None:
    """
    Send an email using the provided SMTP configuration.

    Args:
        smtp_cfg: SMTP configuration.
        message: EmailMessage ready to be sent.

    Raises:
        smtplib.SMTPException: For any SMTP-related errors.
    """
    context = ssl.create_default_context()
    try:
        if smtp_cfg.use_ssl:
            with smtplib.SMTP_SSL(
                smtp_cfg.server, smtp_cfg.port, context=context, timeout=30
            ) as server:
                server.login(smtp_cfg.user, smtp_cfg.password)
                server.send_message(message)
        else:
            with smtplib.SMTP(smtp_cfg.server, smtp_cfg.port, timeout=30) as server:
                server.starttls(context=context)
                server.login(smtp_cfg.user, smtp_cfg.password)
                server.send_message(message)
    except smtplib.SMTPException as e:
        raise e


# --------------------------------------------------------------------------- #
# Logging setup
# --------------------------------------------------------------------------- #
def configure_logging(log_file: Optional[str] = None) -> None:
    """
    Configure the root logger.

    Args:
        log_file: Optional path to a file where logs will be written.
    """
    handlers = [logging.StreamHandler(sys.stdout)]
    if log_file:
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=handlers,
    )


# --------------------------------------------------------------------------- #
# Main workflow
# --------------------------------------------------------------------------- #
def main() -> None:
    parser = argparse.ArgumentParser(description="Email automation bot")
    parser.add_argument("--csv", required=True, help="Path to CSV with recipients")
    parser.add_argument(
        "--template", required=True, help="Path to email template (text file)"
    )
    parser.add_argument(
        "--subject", required=True, help="Subject line for the email"
    )
    parser.add_argument(
        "--smtp-server", required=True, help="SMTP server hostname"
    )
    parser.add_argument(
        "--smtp-port",
        type=int,
        required=False,
        default=465,
        help="SMTP server port (default 465 for SSL)",
    )
    parser.add_argument(
        "--smtp-user", required=True, help="SMTP username (usually email address)"
    )
    parser.add_argument(
        "--smtp-password",
        help="SMTP password; if omitted, read from env SMTP_PASSWORD or prompt",
    )
    parser.add_argument(
        "--log-file",
        help="Optional path to a log file (default: console only)",
    )
    parser.add_argument(
        "--reply-to",
        help="Optional Reply-To email address",
    )
    args = parser.parse_args()

    configure_logging(args.log_file)

    # Resolve SMTP password
    smtp_password = args.smtp_password or os.getenv("SMTP_PASSWORD")
    if not smtp_password:
        smtp_password = getpass(prompt="Enter SMTP password: ")

    smtp_cfg = SMTPConfig(
        server=args.smtp_server,
        port=args.smtp_port,
        user=args.smtp_user,
        password=smtp_password,
        use_ssl=args.smtp_port == 465,  # common convention
    )

    try:
        recipients = load_recipients(args.csv)
        logging.info(f"Loaded {len(recipients)} recipients from {args.csv}")
    except Exception as exc:
        logging.error(f"Failed to load recipients: {exc}")
        sys.exit(1)

    try:
        template = load_template(args.template)
    except Exception as exc:
        logging.error(f"Failed to load template: {exc}")
        sys.exit(1)

    sent_count = 0
    for recipient in recipients:
        try:
            # Merge global placeholders (e.g., email) with recipient-specific fields
            placeholder_map = {"email": recipient.email, **recipient.fields}
            body = render_template(template, placeholder_map)

            message = create_email_message(
                from_addr=smtp_cfg.user,
                to_addr=recipient.email,
                subject=args.subject,
                body=body,
                reply_to=args.reply_to,
            )
            send_email(smtp_cfg, message)

            logging.info(
                f"Sent email to {recipient.email} at {datetime.utcnow().isoformat()}Z"
            )
            sent_count += 1
        except Exception as exc:
            logging.error(f"Failed to send email to {recipient.email}: {exc}")

    logging.info(f"Finished. Successfully sent {sent_count}/{len(recipients)} emails.")


if __name__ == "__main__":
    main()