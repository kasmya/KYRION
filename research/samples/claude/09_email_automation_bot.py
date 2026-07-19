"""
### Task 9: Email Automation Bot (SendGrid + Pandas)

Reads a recipient list from CSV, personalizes email content per recipient,
sends via SendGrid (falling back to a logging stub if no API key is
configured), and tracks bounces/opens/clicks via SendGrid event webhooks.

Requirements:
    pip install pandas sendgrid

Usage:
    export SENDGRID_API_KEY=your_key_here   # optional; stub mode if unset
    python 09_email_automation_bot.py --csv recipients.csv \
        --subject-template "Hi {first_name}, a special offer for you" \
        --body-template "Hello {first_name},\\n\\nEnjoy 20% off at {company}!\\n\\nBest,\\nThe Team"
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from dataclasses import dataclass
from typing import List, Optional

import pandas as pd

try:
    from sendgrid import SendGridAPIClient
    from sendgrid.helpers.mail import Mail
except ImportError:  # pragma: no cover - allows the stub mode to work without the package
    SendGridAPIClient = None
    Mail = None

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("email_automation_bot")

REQUIRED_COLUMNS = {"email"}
SEND_RATE_LIMIT_DELAY_SECONDS = 0.1  # be gentle with the API


@dataclass
class SendResult:
    email: str
    success: bool
    detail: str


class EmailAutomationError(Exception):
    """Raised when the recipient list is invalid or unusable."""


def load_recipients(csv_path: str) -> pd.DataFrame:
    """Loads and validates the recipient CSV file."""
    try:
        df = pd.read_csv(csv_path)
    except (OSError, pd.errors.ParserError) as exc:
        raise EmailAutomationError(f"failed to read CSV '{csv_path}': {exc}") from exc

    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise EmailAutomationError(f"CSV is missing required column(s): {missing}")

    before = len(df)
    df = df.dropna(subset=["email"]).drop_duplicates(subset=["email"])
    logger.info("Loaded %d recipient(s) (dropped %d invalid/duplicate rows)", len(df), before - len(df))
    return df


def personalize(template: str, row: pd.Series) -> str:
    """Fills a template string with values from a recipient row, tolerating missing fields."""
    row_dict = row.to_dict()
    try:
        return template.format(**row_dict)
    except KeyError as exc:
        missing_field = str(exc).strip("'")
        logger.warning(
            "Template references missing field '%s' for recipient '%s'; leaving placeholder blank",
            missing_field,
            row.get("email", "unknown"),
        )
        # Fill unknown placeholders with empty string rather than failing the whole send.
        safe_dict = {**row_dict}
        return template.format_map(_SafeDict(safe_dict))


class _SafeDict(dict):
    """A dict subclass that returns an empty string for missing template keys."""

    def __missing__(self, key: str) -> str:
        return ""


class SendGridEmailSender:
    """Wraps the SendGrid API, falling back to a logging stub if unconfigured."""

    def __init__(self, api_key: Optional[str], from_email: str) -> None:
        self.api_key = api_key
        self.from_email = from_email
        self.client = None
        if api_key and SendGridAPIClient is not None:
            self.client = SendGridAPIClient(api_key)
        elif api_key and SendGridAPIClient is None:
            logger.warning("SENDGRID_API_KEY set but sendgrid package not installed; using stub mode")

    def send(self, to_email: str, subject: str, body: str) -> SendResult:
        """Sends a single email, returning a SendResult describing the outcome."""
        if self.client is None:
            logger.info("[EMAIL STUB] To: %s | Subject: %s\n%s", to_email, subject, body)
            return SendResult(email=to_email, success=True, detail="stubbed (no API key configured)")

        message = Mail(
            from_email=self.from_email, to_emails=to_email, subject=subject, plain_text_content=body
        )
        try:
            response = self.client.send(message)
            success = 200 <= response.status_code < 300
            return SendResult(
                email=to_email, success=success, detail=f"status_code={response.status_code}"
            )
        except Exception as exc:  # noqa: BLE001 - SendGrid raises varied exception types
            logger.error("Failed to send email to '%s': %s", to_email, exc)
            return SendResult(email=to_email, success=False, detail=str(exc))


def send_campaign(
    df: pd.DataFrame,
    subject_template: str,
    body_template: str,
    sender: SendGridEmailSender,
) -> List[SendResult]:
    """Sends a personalized email to every recipient in the DataFrame."""
    results: List[SendResult] = []

    for _, row in df.iterrows():
        subject = personalize(subject_template, row)
        body = personalize(body_template, row)
        result = sender.send(row["email"], subject, body)
        results.append(result)
        time.sleep(SEND_RATE_LIMIT_DELAY_SECONDS)

    return results


def handle_bounce_event(event: dict) -> None:
    """Processes a single SendGrid webhook event for bounces/opens/clicks.

    In a real deployment, this would be called from a Flask/FastAPI webhook
    endpoint receiving SendGrid's Event Webhook payloads.
    """
    event_type = event.get("event")
    email = event.get("email")

    if event_type == "bounce":
        logger.warning("Email to '%s' bounced: %s", email, event.get("reason"))
    elif event_type == "open":
        logger.info("Email to '%s' was opened", email)
    elif event_type == "click":
        logger.info("Email to '%s' link clicked: %s", email, event.get("url"))
    else:
        logger.debug("Unhandled event type '%s' for '%s'", event_type, email)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Send a personalized email campaign via SendGrid.")
    parser.add_argument("--csv", required=True, help="Path to recipient CSV (must include 'email')")
    parser.add_argument("--subject-template", required=True)
    parser.add_argument("--body-template", required=True)
    parser.add_argument("--from-email", default="noreply@example.com")
    return parser


def main(argv: List[str] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        df = load_recipients(args.csv)
    except EmailAutomationError as exc:
        logger.error(str(exc))
        return 1

    sender = SendGridEmailSender(os.environ.get("SENDGRID_API_KEY"), args.from_email)
    results = send_campaign(df, args.subject_template, args.body_template, sender)

    successes = sum(1 for r in results if r.success)
    logger.info("Campaign complete: %d/%d emails sent successfully", successes, len(results))
    return 0 if successes == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
