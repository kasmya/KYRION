"""
Email Automation Bot

Reads recipient data from a CSV file, renders templated emails with placeholders,
sends them via SMTP, and logs the sending activity.

Security:
    - SMTP credentials are read from environment variables, never hardcoded.
    - SMTP connection uses TLS (STARTTLS) by default.
    - Input CSV is validated for expected columns.
    - Template placeholders are escaped to prevent injection in plain-text context.
"""

import csv
import logging
import os
import smtplib
import sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from string import Template
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Logging configuration
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler("email_bot.log"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
REQUIRED_CSV_COLUMNS: List[str] = ["email", "first_name"]
SMTP_HOST: str = os.getenv("SMTP_HOST", "smtp.example.com")
SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER: str = os.getenv("SMTP_USER", "")
SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
SENDER_EMAIL: str = os.getenv("SENDER_EMAIL", "noreply@example.com")
SENDER_NAME: str = os.getenv("SENDER_NAME", "Automation Bot")
DEFAULT_SUBJECT: str = "Hello, ${first_name}!"


def load_recipients(csv_path: str) -> List[Dict[str, str]]:
    """
    Load recipient data from a CSV file.

    Args:
        csv_path: Path to the CSV file. Must contain at least 'email' and
                  'first_name' columns.

    Returns:
        A list of dictionaries, each representing a recipient row.

    Raises:
        FileNotFoundError: If the CSV file does not exist.
        ValueError: If the CSV does not contain the required columns.
    """
    if not os.path.isfile(csv_path):
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    recipients: List[Dict[str, str]] = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or not all(
            col in reader.fieldnames for col in REQUIRED_COLUMNS
        ):
            missing = [col for col in REQUIRED_COLUMNS if col not in (reader.fieldnames or [])]
            raise ValueError(
                f"CSV is missing required columns: {missing}. "
                f"Required: {REQUIRED_COLUMNS}"
            )
        for row in reader:
            recipients.append(dict(row))
    logger.info("Loaded %d recipients from %s", len(recipients), csv_path)
    return recipients


def render_template(template_str: str, context: Dict[str, str]) -> str:
    """
    Render a string template using Python's string.Template.

    Placeholders are expected in the form $placeholder or ${placeholder}.
    Missing keys will raise a KeyError.

    Args:
        template_str: The template with placeholders.
        context: Dictionary mapping placeholder names to values.

    Returns:
        The rendered string.
    """
    tmpl = Template(template_str)
    try:
        return tmpl.substitute(context)
    except KeyError as exc:
        logger.error("Missing placeholder in template: %s", exc)
        raise


def build_message(
    recipient_email: str,
    recipient_data: Dict[str, str],
    subject_template: str = DEFAULT_SUBJECT,
    html_template: Optional[str] = None,
    text_template: Optional[str] = None,
) -> MIMEMultipart:
    """
    Construct a MIME multipart/alternative email message.

    Args:
        recipient_email: Recipient's email address.
        recipient_data: Dictionary of placeholder values for the recipient.
        subject_template: A string.Template for the email subject.
        html_template: Optional HTML template string. If provided, an HTML
                       part is added.
        text_template: Optional plain-text template string. If provided, a
                       plain-text part is added.

    Returns:
        A MIMEMultipart email message ready to be sent.
    """
    msg = MIMEMultipart("alternative")
    msg["From"] = f"{SENDER_NAME} <{SENDER_EMAIL}>"
    msg["To"] = recipient_email
    msg["Subject"] = Template(subject_template).safe_substitute(recipient_data)

    if text_template:
        text_body = render_template(text_template, recipient_data)
        msg.attach(MIMEText(text_body, "plain", "utf-8"))

    if html_template:
        html_body = render_template(html_template, recipient_data)
        msg.attach(MIMEText(html_body, "html", "utf-8"))

    if not text_template and not html_template:
        logger.warning("No text or HTML template provided; sending empty body.")

    return msg


def send_email(
    msg: MIMEMultipart,
    smtp_host: str = SMTP_HOST,
    smtp_port: int = SMTP_PORT,
    smtp_user: str = SMTP_USER,
    smtp_password: str = SMTP_PASSWORD,
    use_tls: bool = True,
) -> Tuple[bool, str]:
    """
    Send an email via SMTP.

    Args:
        msg: The MIMEMultipart message to send.
        smtp_host: SMTP server hostname.
        smtp_port: SMTP server port.
        smtp_user: SMTP username.
        smtp_password: SMTP password.
        use_tls: Whether to use STARTTLS. Defaults to True.

    Returns:
        A tuple of (success: bool, message: str). The message contains
        a success confirmation or error description.
    """
    if not smtp_host:
        raise ValueError("SMTP_HOST is not configured.")

    try:
        server = smtplib.SMTP(smtp_host, smtp_port, timeout=30)
        server.ehlo()
        if use_tls:
            server.starttls()
            server.ehlo()
        if smtp_user and smtp_password:
            server.login(smtp_user, smtp_password)
        server.send_message(msg)
        server.quit()
        logger.info("Email sent successfully to %s", msg["To"])
        return True, "OK"
    except smtplib.SMTPAuthenticationError as exc:
        logger.error("SMTP authentication failed: %s", exc)
        return False, f"Authentication error: {exc}"
    except smtplib.SMTPConnectError as exc:
        logger.error("SMTP connection failed: %s", exc)
        return False, f"Connection error: {exc}"
    except smtplib.SMTPRecipientsRefused as exc:
        logger.error("Recipient refused: %s", exc)
        return False, f"Recipient refused: {exc}"
    except smtplib.SMTPSenderRefused as exc:
        logger.error("Sender refused: %s", exc)
        return False, f"Sender refused: {exc}"
    except smtplib.SMTPDataError as exc:
        logger.error("SMTP data error: %s", exc)
        return False, f"Data error: {exc}"
    except smtplib.SMTPException as exc:
        logger.error("General SMTP error: %s", exc)
        return False, f"SMTP error: {exc}"
    except OSError as exc:
        logger.error("Network error: %s", exc)
        return False, f"Network error: {exc}"


def log_send_result(
    recipient_email: str,
    success: bool,
    message: str,
    log_file: str = "send_log.csv",
) -> None:
    """
    Append a send result to a CSV log file.

    Args:
        recipient_email: The recipient's email address.
        success: Whether the send was successful.
        message: A status or error message.
        log_file: Path to the log CSV file.
    """
    file_exists = os.path.isfile(log_file)
    with open(log_file, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["email", "success", "message"])
        writer.writerow([recipient_email, success, message])
    logger.debug("Logged result for %s to %s", recipient_email, log_file)


def run_email_bot(
    csv_path: str,
    subject_template: str = DEFAULT_SUBJECT,
    html_template: Optional[str] = None,
    text_template: Optional[str] = None,
    log_file: str = "send_log.csv",
) -> None:
    """
    Main entry point: load recipients, render emails, send them, and log results.

    Args:
        csv_path: Path to the CSV file with recipient data.
        subject_template: Subject line template string.
        html_template: Optional HTML body template string.
        text_template: Optional plain-text body template string.
        log_file: Path to the CSV log file.
    """
    logger.info("Starting email automation bot.")
    try:
        recipients = load_recipients(csv_path)
    except (FileNotFoundError, ValueError) as exc:
        logger.critical("Failed to load recipients: %s", exc)
        return

    total = len(recipients)
    success_count = 0
    for idx, recipient in enumerate(recipients, start=1):
        email = recipient.get("email", "").strip()
        if not email:
            logger.warning("Row %d has empty email; skipping.", idx)
            continue

        try:
            msg = build_message(email, recipient, subject_template, html_template, text_template)
        except KeyError as exc:
            logger.error("Template rendering failed for %s: %s", email, exc)
            log_send_result(email, False, f"Template error: {exc}", log_file)
            continue

        success, status_msg = send_email(msg)
        if success:
            success_count += 1
        log_send(email, success, status_msg, log_file)
        logger.info(
            "Processed %d/%d: %s -> %s", idx, total, email, "SUCCESS" if success else "FAILED"
        )

    logger.info(
        "Email bot finished. %d/%d emails sent successfully.", success_count, total
    )


if __name__ == "__main__":
    # Example usage (requires SMTP_* env vars and a recipients.csv file)
    import argparse

    parser = argparse.ArgumentParser(description="Send templated emails to a CSV list of recipients.")
    parser.add_argument("csv", help="Path to the recipients CSV file")
    parser.add_argument("--subject", default=DEFAULT_SUBJECT, help="Subject template")
    parser.add_argument("--html-template", help="Path to HTML template file")
    parser.add_argument("--text-template", help="Path to plain-text template file")
    parser.add_argument("--log-file", default="send_log.csv", help="Path to send log CSV")
    args = parser.parse_args()

    html_tmpl = None
    text_tmpl = None

    if args.html_template:
        with open(args.html_template, encoding="utf-8") as f:
            html_tmpl = f.read()
    if args.text_template:
        with open(args.text_template, encoding="utf-8") as f:
            text_tmpl = f.read()

    run_email_bot(
        csv_path=args.csv,
        subject_template=args.subject,
        html_template=html_tmpl,
        text_template=text_tmpl,
        log_file=args.log_file,
    )