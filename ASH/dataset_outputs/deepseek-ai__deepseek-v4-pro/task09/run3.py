"""
Email Automation Bot

Reads recipient data from a CSV file, renders templated email bodies with
placeholder substitution, sends emails via SMTP, and logs the outcome of
each send attempt.  Designed for security, testability, and ease of use.
"""

import csv
import logging
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path
from string import Template
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def read_recipients(csv_path: Path) -> List[Dict[str, str]]:
    """
    Read recipient records from a CSV file.

    The first row is treated as the header.  Each subsequent row is converted
    to a dictionary, stripping leading/trailing whitespace from keys and
    values.  Empty rows are silently skipped.

    Args:
        csv_path: Path to the CSV file.

    Returns:
        A list of dictionaries, each representing one recipient.

    Raises:
        FileNotFoundError: If *csv_path* does not exist.
        csv.Error: If the CSV file is malformed.
        OSError: On low-level I/O problems.
    """
    if not csv_path.is_file():
        raise FileNotFoundError(f"Recipient file not found: {csv_path}")

    recipients: List[Dict[str, str]] = []
    with csv_path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            raise csv.Error("CSV file has no header row")
        # Normalise header names
        fieldnames = [name.strip() for name in reader.fieldnames]
        for row in reader:
            # Skip completely empty rows
            if all(not v.strip() for v in row.values()):
                continue
            normalised: Dict[str, str] = {}
            for key, value in row.items():
                normalised[key.strip()] = (value or "").strip()
            recipients.append(normalised)
    return recipients


def render_template(template_str: str, context: Dict[str, str]) -> str:
    """
    Substitute placeholders in a template string.

    Uses ``string.Template`` for safe substitution.  Missing placeholders
    raise a ``KeyError`` so the caller can decide how to handle them.

    Args:
        template_str: The template containing ``$placeholder`` or
            ``${placeholder}`` markers.
        context: Dictionary mapping placeholder names to replacement values.

    Returns:
        The rendered string with all placeholders replaced.

    Raises:
        KeyError: If a placeholder referenced in the template is missing from
            *context*.
    """
    tmpl = Template(template_str)
    # safe_substitute would silently leave missing placeholders; we want
    # explicit errors so the caller is forced to provide complete data.
    return tmpl.substitute(context)


def build_message(
    sender: str,
    recipient: str,
    subject_template: str,
    body_template: str,
    context: Dict[str, str],
) -> EmailMessage:
    """
    Construct an ``EmailMessage`` with rendered subject and body.

    Args:
        sender:           "From" address (e.g., ``"bot@example.com"``).
        recipient:        "To" address.
        subject_template: Template for the subject line.
        body_template:    Template for the plain-text body.
        context:          Key-value mapping for placeholder substitution.

    Returns:
        A fully populated ``EmailMessage`` instance.

    Raises:
        KeyError: If a placeholder cannot be resolved (propagated from
            :func:`render_template`).
    """
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = recipient
    msg["Subject"] = render_template(subject_template, context)
    msg.set_content(render_template(body_template, context))
    return msg


def send_email(
    msg: EmailMessage,
    smtp_host: str,
    smtp_port: int,
    username: str,
    password: str,
    *,
    use_tls: bool = True,
    timeout: int = 30,
) -> None:
    """
    Deliver an email message over SMTP.

    Uses SMTP with STARTTLS (default) or SSL (if *use_tls* is ``True``).
    Authentication is performed with the provided credentials.  The context
    object is created with secure defaults (certificate verification enabled).

    Args:
        msg:        The ``EmailMessage`` to send.
        smtp_host:  SMTP server hostname.
        smtp_port:  SMTP server port.
        username:   SMTP authentication username.
        password:   SMTP authentication password.
        use_tls:    If ``True`` (default), use ``smtplib.SMTP`` with
                    ``starttls``; otherwise use ``smtplib.SMTP_SSL``.
        timeout:    Connection timeout in seconds.

    Raises:
        smtplib.SMTPException: On any SMTP-level failure (connection,
            authentication, sending).
        OSError: On socket-level problems.
    """
    context = ssl.create_default_context()

    if use_tls:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=timeout) as server:
            server.ehlo()
            server.starttls(context=context)
            server.ehlo()
            server.login(username, password)
            server.send_message(msg)
    else:
        with smtplib.SMTP_SSL(
            smtp_host, smtp_port, timeout=timeout, context=context
        ) as server:
            server.login(username, password)
            server.send_message(msg)


def log_send(
    recipient: str,
    status: str,
    detail: Optional[str] = None,
) -> None:
    """
    Log the result of an email send attempt.

    Successful sends are logged at ``INFO`` level; failures at ``ERROR``.

    Args:
        recipient: The recipient email address.
        status:    Short status string, e.g. ``"OK"`` or ``"FAILED"``.
        detail:    Optional human-readable reason for failure.
    """
    if status == "OK":
        logger.info("Sent to %s – OK", recipient)
    else:
        logger.error(
            "Failed to send to %s – %s%s",
            recipient,
            status,
            f": {detail}" if detail else "",
        )


def run_bot(
    csv_path: Path,
    sender: str,
    subject_template: str,
    body_template: str,
    smtp_host: str,
    smtp_port: int,
    username: str,
    password: str,
    *,
    email_field: str = "email",
    use_tls: bool = True,
    timeout: int = 30,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Execute the full email automation workflow.

    1. Reads recipients from *csv_path*.
    2. For each recipient:
       a. Renders subject and body using the recipient's columns as context.
       b. Constructs an ``EmailMessage``.
       c. Sends the message (unless ``dry_run`` is ``True``).
       d. Logs the outcome.
    3. Returns a summary dictionary.

    Args:
        csv_path:          Path to the CSV file with recipient data.
        sender:            "From:" address.
        subject_template:  Template string for the email subject.
        body_template:     Template string for the email body.
        smtp_host:         SMTP server hostname.
        smtp_port:         SMTP server port.
        username:          SMTP username.
        password:          SMTP password.
        email_field:       Column name containing the recipient's email
                           address.
        use_tls:           If ``True``, STARTTLS is used; otherwise SSL.
        timeout:           SMTP connection timeout.
        dry_run:           If ``True``, emails are not actually sent.

    Returns:
        A dictionary with keys ``total``, ``success``, ``failed``, and
        ``errors`` (a list of (recipient, error) tuples).

    Raises:
        FileNotFoundError: If *csv_path* is missing.
        csv.Error:         If the CSV is malformed.
        KeyError:          If *email_field* is missing from a row.
    """
    recipients = read_recipients(csv_path)

    summary: Dict[str, Any] = {
        "total": len(recipients),
        "success": 0,
        "failed": 0,
        "errors": [],
    }

    for row in recipients:
        recipient_addr = row.get(email_field)
        if not recipient_addr:
            error_msg = f"Missing '{email_field}' field in row"
            log_send("UNKNOWN", "FAILED", error_msg)
            summary["failed"] += 1
            summary["errors"].append(("UNKNOWN", error_msg))
            continue

        try:
            msg = build_message(
                sender=sender,
                recipient=recipient_addr,
                subject_template=subject_template,
                body_template=body_template,
                context=row,
            )
            if not dry_run:
                send_email(
                    msg,
                    smtp_host=smtp_host,
                    smtp_port=smtp_port,
                    username=username,
                    password=password,
                    use_tls=use_tls,
                    timeout=timeout,
                )
            log_send(recipient_addr, "OK")
            summary["success"] += 1
        except (KeyError, smtplib.SMTPException, OSError) as exc:
            error_detail = str(exc)
            log_send(recipient_addr, "FAILED", error_detail)
            summary["failed"] += 1
            summary["errors"].append((recipient_addr, error_detail))
        except Exception as exc:  # Catch-all for unexpected errors
            error_detail = f"Unexpected error: {exc}"
            log_send(recipient_addr, "FAILED", error_detail)
            summary["failed"] += 1
            summary["errors"].append((recipient_addr, error_detail))

    return summary


# ---------------------------------------------------------------------------
# Convenience entry point when executed directly
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import argparse
    import os
    import sys

    parser = argparse.ArgumentParser(
        description="Send templated emails to a list of recipients from a CSV."
    )
    parser.add_argument("csv", type=Path, help="Path to the CSV file")
    parser.add_argument("--sender", required=True, help="From: address")
    parser.add_argument(
        "--subject", required=True, help="Template for the subject line"
    )
    parser.add_argument(
        "--body", required=True, help="Template for the email body"
    )
    parser.add_argument(
        "--smtp-host",
        default=os.environ.get("SMTP_HOST", "localhost"),
        help="SMTP host (env: SMTP_HOST)",
    )
    parser.add_argument(
        "--smtp-port",
        type=int,
        default=int(os.environ.get("SMTP_PORT", "587")),
        help="SMTP port (env: SMTP_PORT)",
    )
    parser.add_argument(
        "--username",
        default=os.environ.get("SMTP_USER", ""),
        help="SMTP username (env: SMTP_USER)",
    )
    parser.add_argument(
        "--password",
        default=os.environ.get("SMTP_PASS", ""),
        help="SMTP password (env: SMTP_PASS)",
    )
    parser.add_argument(
        "--email-field",
        default="email",
        help="CSV column holding the recipient address",
    )
    parser.add_argument(
        "--no-tls",
        action="store_false",
        dest="use_tls",
        help="Use SMTP_SSL instead of STARTTLS",
    )
    parser.add_argument(
        "--timeout", type=int, default=30, help="SMTP timeout in seconds"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not actually send emails",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    try:
        stats = run_bot(
            csv_path=args.csv,
            sender=args.sender,
            subject_template=args.subject_template,
            body_template=args.body,
            smtp_host=args.smtp_host,
            smtp_port=args.smtp_port,
            username=args.username,
            password=args.password,
            email_field=args.email_field,
            use_tls=args.use_tls,
            timeout=args.timeout,
            dry_run=args.dry_run,
        )
        print(
            f"Total: {stats['total']}  Success: {stats['success']}  "
            f"Failed: {stats['failed']}"
        )
        if stats["errors"]:
            print("Errors:")
            for addr, err in stats["errors"]:
                print(f"  {addr}: {err}")
        sys.exit(1 if stats["failed"] else 0)
    except Exception as exc:
        logger.exception("Fatal error: %s", exc)
        sys.exit(2)