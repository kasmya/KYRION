"""
Email Automation Bot

Reads recipients from a CSV file, renders templated email messages with
placeholders, sends emails over SMTP, and logs the sending operations.

Usage:
    python email_bot.py recipients.csv template.txt config.json

Dependencies:
    - jinja2 (for template rendering)
    - Python 3.8+ standard library
"""

import csv
import json
import logging
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any, Dict, List, Optional

from jinja2 import Environment, BaseLoader, TemplateSyntaxError

# Configure module-level logger
logger = logging.getLogger(__name__)


def setup_logging(log_file: str = "email_bot.log") -> None:
    """
    Configure logging to both console and a file.

    Args:
        log_file: Path to the log file. Defaults to 'email_bot.log'.
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(),
        ],
    )


def load_config(config_path: str) -> Dict[str, Any]:
    """
    Load SMTP configuration and email template from a JSON file.

    Args:
        config_path: Path to the JSON configuration file.

    Returns:
        A dictionary containing SMTP settings and template details.

    Raises:
        FileNotFoundError: If the config file does not exist.
        json.JSONDecodeError: If the config file is not valid JSON.
        KeyError: If required keys are missing from the configuration.
    """
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config: Dict[str, Any] = json.load(f)
    except FileNotFoundError:
        logger.error("Configuration file not found: %s", config_path)
        raise
    except json.JSONDecodeError as e:
        logger.error("Invalid JSON in configuration file: %s", e)
        raise

    required_keys = ["smtp_server", "smtp_port", "username", "password",
                     "from_address", "subject_template", "body_template"]
    for key in required_keys:
        if key not in config:
            logger.error("Missing required configuration key: %s", key)
            raise KeyError(f"Missing required configuration key: {key}")

    return config


def read_recipients(csv_path: str) -> List[Dict[str, str]]:
    """
    Read recipient data from a CSV file.

    The first row is expected to contain headers. Each subsequent row
    represents a recipient. The column 'email' is mandatory.

    Args:
        csv_path: Path to the CSV file.

    Returns:
        A list of dictionaries, each representing a recipient.

    Raises:
        FileNotFoundError: If the CSV file does not exist.
        csv.Error: If the CSV file is malformed.
        ValueError: If the 'email' column is missing.
    """
    recipients: List[Dict[str, str]] = []
    try:
        with open(csv_path, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            if "email" not in (reader.fieldnames or []):
                raise ValueError("CSV must contain an 'email' column")
            for row in reader:
                recipients.append(row)
    except FileNotFoundError:
        logger.error("Recipients CSV file not found: %s", csv_path)
        raise
    except csv.Error as e:
        logger.error("Error reading CSV file: %s", e)
        raise

    if not recipients:
        logger.warning("No recipients found in CSV file: %s", csv_path)

    return recipients


def create_message(
    recipient: Dict[str, str],
    subject_template: str,
    body_template: str,
    from_address: str,
) -> MIMEMultipart:
    """
    Create a MIME email message by rendering subject and body templates.

    Args:
        recipient: Dictionary containing recipient data (must include 'email').
        subject_template: Jinja2 template string for the subject.
        body_template: Jinja2 template string for the HTML body.
        from_address: Sender email address.

    Returns:
        A MIMEMultipart message object ready for sending.

    Raises:
        jinja2.TemplateSyntaxError: If the templates have syntax errors.
        KeyError: If the recipient dictionary lacks keys used in the template.
    """
    env = Environment(loader=BaseLoader())

    try:
        subject_tmpl = env.from_string(subject_template)
        body_tmpl = env.from_string(body_template)
    except TemplateSyntaxError as e:
        logger.error("Template syntax error: %s", e)
        raise

    try:
        subject = subject_tmpl.render(**recipient)
        body_html = body_tmpl.render(**recipient)
    except KeyError as e:
        logger.error("Missing placeholder in template: %s", e)
        raise
    except Exception as e:
        logger.error("Unexpected error rendering template: %s", e)
        raise

    msg = MIMEMultipart("alternative")
    msg["From"] = from_address
    msg["To"] = recipient["email"]
    msg["Subject"] = subject

    part = MIMEText(body_html, "html")
    msg.attach(part)

    return msg


def send_email(
    smtp_server: str,
    smtp_port: int,
    username: str,
    password: str,
    msg: MIMEMultipart,
    use_tls: bool = True,
) -> bool:
    """
    Send an email message over SMTP with TLS encryption.

    Args:
        smtp_server: SMTP server hostname.
        smtp_port: SMTP server port.
        username: SMTP authentication username.
        password: SMTP authentication password.
        msg: MIMEMultipart message to send.
        use_tls: Whether to use STARTTLS. Defaults to True.

    Returns:
        True if the email was sent successfully, False otherwise.

    Raises:
        smtplib.SMTPException: On SMTP-related errors.
    """
    context = ssl.create_default_context()

    try:
        with smtplib.SMTP(smtp_server, smtp_port, timeout=30) as server:
            server.ehlo()
            if use_tls:
                server.starttls(context=context)
                server.ehlo()
            server.login(username, password)
            server.send_message(msg)
        logger.info("Email sent successfully to %s", msg["To"])
        return True
    except smtplib.SMTPAuthenticationError as e:
        logger.error("SMTP authentication failed: %s", e)
        raise
    except smtplib.SMTPException as e:
        logger.error("SMTP error sending to %s: %s", msg["To"], e)
        raise
    except (OSError, TimeoutError) as e:
        logger.error("Network error sending to %s: %s", msg["To"], e)
        raise


def main() -> None:
    """
    Main entry point: orchestrate reading, rendering, sending, and logging.

    Expects three command-line arguments: recipients CSV, config JSON, and
    optionally a log file path.
    """
    import sys

    if len(sys.argv) < 3:
        print("Usage: python email_bot.py <recipients.csv> <config.json> [log_file]")
        sys.exit(1)

    recipients_csv = sys.argv[1]
    config_json = sys.argv[2]
    log_file = sys.argv[3] if len(sys.argv) > 3 else "email_bot.log"

    setup_logging(log_file)

    try:
        config = load_config(config_json)
    except (FileNotFoundError, json.JSONDecodeError, KeyError) as e:
        logger.critical("Failed to load configuration: %s", e)
        sys.exit(1)

    try:
        recipients = read_recipients(recipients_csv)
    except (FileNotFoundError, csv.Error, ValueError) as e:
        logger.critical("Failed to read recipients: %s", e)
        sys.exit(1)

    if not recipients:
        logger.warning("No recipients to process. Exiting.")
        sys.exit(0)

    smtp_config = {
        "smtp_server": config["smtp_server"],
        "smtp_port": int(config["smtp_port"]),
        "username": config["username"],
        "password": config["password"],
        "use_tls": config.get("use_tls", True),
    }
    from_address = config["from_address"]
    subject_template = config["subject_template"]
    body_template = config["body_template"]

    success_count = 0
    fail_count = 0

    for recipient in recipients:
        try:
            msg = create_message(
                recipient, subject_template, body_template, from_address
            )
            send_email(**smtp_config, msg=msg)
            success_count += 1
        except (KeyError, TemplateSyntaxError, smtplib.SMTPException,
                ValueError, OSError) as e:
            logger.error(
                "Failed to send to %s: %s",
                recipient.get("email", "unknown"),
                e,
            )
            fail_count += 1

    logger.info(
        "Batch completed: %d sent, %d failed",
        success_count,
        fail_count,
    )


if __name__ == "__main__":
    main()