"""
email_automation_bot.py

A lightweight email automation utility that reads recipient data from a CSV file,
renders a templated email using placeholder substitution, sends the email via
SMTP with TLS, and logs each send attempt.

Features:
- CSV parsing with explicit error handling.
- Template rendering using :class:`string.Template`.
- Secure SMTP connection (STARTTLS) with optional credential loading from
  environment variables.
- Detailed logging of successes and failures.
- Command‑line interface for straightforward usage.

Only the Python standard library and the widely‑used ``python-dotenv`` package
are required.
"""

from __future__ import annotations

import argparse
import csv
import logging
import os
import smtplib
import sys
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path
from string import Template
from typing import Any, Dict, List, Optional

try:
    from dotenv import load_dotenv  # type: ignore
except ImportError:  # pragma: no cover
    load_dotenv = None  # type: ignore


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


# --------------------------------------------------------------------------- #
# Core functionality
# --------------------------------------------------------------------------- #

def load_recipients(csv_path: Path) -> List[Dict[str, str]]:
    """
    Load recipient records from a CSV file.

    The CSV must contain a header row. Each row is returned as a ``dict``
    mapping column names to string values.

    Args:
        csv_path: Path to the CSV file.

    Returns:
        List of dictionaries representing recipient data.

    Raises:
        FileNotFoundError: If the CSV file does not exist.
        csv.Error: For malformed CSV content.
        ValueError: If the CSV is empty or lacks a header.
    """
    if not csv_path.is_file():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    with csv_path.open(newline="", encoding="utf-8") as fp:
        reader = csv.DictReader(fp)
        if reader.fieldnames is None:
            raise ValueError("CSV file must have a header row.")
        recipients = [row for row in reader]

    if not recipients:
        raise ValueError("CSV file contains no recipient rows.")
    return recipients


def render_template(template_str: str, context: Dict[str, Any]) -> str:
    """
    Render a template string using ``string.Template`` substitution.

    Placeholders in the template should be of the form ``${placeholder}``.

    Args:
        template_str: The raw template string.
        context: Mapping of placeholder names to replacement values.

    Returns:
        Rendered string with all placeholders substituted.

    Raises:
        KeyError: If a placeholder in the template is missing from ``context``.
        ValueError: If the template contains invalid syntax.
    """
    try:
        tmpl = Template(template_str)
        return tmpl.substitute(context)
    except KeyError as exc:
        raise KeyError(f"Missing placeholder for {exc}") from exc
    except ValueError as exc:
        raise ValueError(f"Invalid template syntax: {exc}") from exc


def build_email(
    sender: str,
    recipient: str,
    subject: str,
    body: str,
    html_body: Optional[str] = None,
) -> EmailMessage:
    """
    Construct an :class:`email.message.EmailMessage` instance.

    Args:
        sender: Email address of the sender.
        recipient: Email address of the recipient.
        subject: Email subject line.
        body: Plain‑text body of the email.
        html_body: Optional HTML version of the body.

    Returns:
        Configured ``EmailMessage`` ready for sending.
    """
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = recipient
    msg["Subject"] = subject
    msg.set_content(body)

    if html_body:
        msg.add_alternative(html_body, subtype="html")
    return msg


def send_email(
    smtp_cfg: SMTPConfig,
    message: EmailMessage,
) -> None:
    """
    Send an email message via SMTP.

    The function establishes a connection, optionally upgrades to TLS,
    authenticates, and transmits the message.

    Args:
        smtp_cfg: SMTP configuration.
        message: Fully‑formed ``EmailMessage`` to send.

    Raises:
        smtplib.SMTPException: For any SMTP‑related failure.
        ConnectionError: If TLS negotiation fails.
    """
    try:
        with smtplib.SMTP(smtp_cfg.host, smtp_cfg.port, timeout=10) as server:
            server.ehlo()
            if smtp_cfg.use_tls:
                server.starttls()
                server.ehlo()
            server.login(smtp_cfg.username, smtp_cfg.password)
            server.send_message(message)
    except smtplib.SMTPException as exc:
        raise smtplib.SMTPException(f"SMTP error: {exc}") from exc
    except Exception as exc:
        raise ConnectionError(f"Failed to send email: {exc}") from exc


def configure_logging(log_path: Path) -> None:
    """
    Configure the root logger to output to a file and to the console.

    Args:
        log_path: Destination for the log file.
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def load_smtp_config(
    env_path: Optional[Path] = None,
) -> SMTPConfig:
    """
    Load SMTP credentials from environment variables.

    Expected variables:
        SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, SMTP_TLS (optional, defaults to "true").

    If ``python-dotenv`` is available, a ``.env`` file can be used.

    Args:
        env_path: Optional path to a ``.env`` file.

    Returns:
        An :class:`SMTPConfig` instance.

    Raises:
        EnvironmentError: If required variables are missing or malformed.
    """
    if load_dotenv and env_path and env_path.is_file():
        load_dotenv(dotenv_path=env_path)

    try:
        host = os.environ["SMTP_HOST"]
        port = int(os.environ.get("SMTP_PORT", "587"))
        username = os.environ["SMTP_USER"]
        password = os.environ["SMTP_PASS"]
        tls_str = os.environ.get("SMTP_TLS", "true").lower()
        use_tls = tls_str in {"1", "true", "yes", "on"}
    except KeyError as exc:
        raise EnvironmentError(f"Missing required SMTP environment variable: {exc}") from exc
    except ValueError as exc:
        raise EnvironmentError(f"Invalid SMTP configuration: {exc}") from exc

    return SMTPConfig(host=host, port=port, username=username, password=password, use_tls=use_tls)


def process_batch(
    csv_file: Path,
    template_file: Path,
    subject_template: str,
    sender: str,
    log_file: Path,
    smtp_cfg: SMTPConfig,
    html_template_file: Optional[Path] = None,
) -> None:
    """
    Orchestrate the full email sending workflow.

    For each recipient row:
        1. Render the subject and body templates.
        2. Build the email message.
        3. Send via SMTP.
        4. Log the outcome.

    Args:
        csv_file: Path to the CSV containing recipient data.
        template_file: Path to the plain‑text email body template.
        subject_template: Template string for the email subject.
        sender: Sender email address.
        log_file: Destination for the log file.
        smtp_cfg: SMTP configuration.
        html_template_file: Optional path to an HTML body template.

    Raises:
        Exception: Propagates any unexpected errors after logging.
    """
    configure_logging(log_file)
    logger = logging.getLogger(__name__)

    try:
        recipients = load_recipients(csv_file)
        with template_file.open(encoding="utf-8") as f:
            body_template = f.read()
        html_template = None
        if html_template_file:
            with html_template_file.open(encoding="utf-8") as f:
                html_template = f.read()
    except Exception as exc:
        logger.exception("Failed to initialise processing: %s", exc)
        raise

    for idx, data in enumerate(recipients, start=1):
        recipient_email = data.get("email")
        if not recipient_email:
            logger.warning("Row %d missing 'email' column; skipping.", idx)
            continue

        try:
            subject = render_template(subject_template, data)
            body = render_template(body_template, data)
            html_body = render_template(html_template, data) if html_template else None
            msg = build_email(sender, recipient_email, subject, body, html_body)
            send_email(smtp_cfg, msg)
            logger.info("Successfully sent to %s", recipient_email)
        except Exception as exc:
            logger.error("Failed to send to %s: %s", recipient_email, exc)


# --------------------------------------------------------------------------- #
# Command‑line interface
# --------------------------------------------------------------------------- #

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Send templated emails to a list of recipients from CSV."
    )
    parser.add_argument("csv", type=Path, help="Path to recipients CSV file.")
    parser.add_argument(
        "template", type=Path, help="Path to plain‑text email body template."
    )
    parser.add_argument(
        "--html-template",
        type=Path,
        help="Optional path to HTML email body template.",
    )
    parser.add_argument(
        "--subject",
        required=True,
        help="Subject line template (use ${placeholder} syntax).",
    )
    parser.add_argument(
        "--sender",
        required=True,
        help="Email address of the sender.",
    )
    parser.add_argument(
        "--log",
        type=Path,
        default=Path("email_automation.log"),
        help="Path to log file (default: email_automation.log).",
    )
    parser.add_argument(
        "--env",
        type=Path,
        help="Path to a .env file containing SMTP credentials.",
    )
    return parser.parse_args()


def main() -> None:
    """
    Entry point for the command‑line tool.
    """
    args = _parse_args()
    try:
        smtp_cfg = load_smtp_config(args.env)
    except EnvironmentError as exc:
        logging.error("SMTP configuration error: %s", exc)
        sys.exit(1)

    try:
        process_batch(
            csv_file=args.csv,
            template_file=args.template,
            subject_template=args.subject,
            sender=args.sender,
            log_file=args.log,
            smtp_cfg=smtp_cfg,
            html_template_file=args.html_template,
        )
    except KeyboardInterrupt:
        logging.info("Interrupted by user.")
        sys.exit(0)
    except Exception as exc:
        logging.exception("Unhandled exception: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()