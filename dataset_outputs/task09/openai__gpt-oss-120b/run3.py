"""Email automation bot.

Features:
- Load recipients from a CSV file.
- Render an email template with placeholders.
- Send messages via SMTP with TLS.
- Log successful deliveries and errors.
"""

import csv
import logging
import os
import ssl
import sys
from dataclasses import dataclass
from pathlib import Path
from string import Template
from typing import Dict, List, Mapping, Optional

import smtplib
from email.message import EmailMessage

# --------------------------------------------------------------------------- #
# Configuration & Logging
# --------------------------------------------------------------------------- #

LOGGER = logging.getLogger("email_bot")
LOGGER.setLevel(logging.INFO)
handler = logging.StreamHandler(sys.stdout)
formatter = logging.Formatter(
    "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
handler.setFormatter(formatter)
LOGGER.addHandler(handler)


# --------------------------------------------------------------------------- #
# Data structures
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class SMTPConfig:
    """Configuration required to connect to an SMTP server."""

    host: str
    port: int = 465  # default to SMTPS
    username: str = ""
    password: str = ""
    use_tls: bool = True  # TLS (STARTTLS) for port 587, SSL for port 465

    @classmethod
    def from_env(cls) -> "SMTPConfig":
        """Create a configuration from environment variables.

        Expected variables:
            EMAIL_SMTP_HOST, EMAIL_SMTP_PORT, EMAIL_SMTP_USER,
            EMAIL_SMTP_PASS, EMAIL_SMTP_TLS (truthy/falsey)
        """
        env = os.getenv
        host = env("EMAIL_SMTP_HOST")
        if not host:
            raise ValueError("EMAIL_SMTP_HOST environment variable not set")

        port = int(env("EMAIL_SMTP_PORT", "465"))
        username = env("EMAIL_SMTP_USER", "")
        password = env("EMAIL_SMTP_PASS", "")
        use_tls = env("EMAIL_SMTP_TLS", "true").lower() in {"1", "true", "yes"}

        return cls(host=host, port=port, username=username, password=password, use_tls=use_tls)


# --------------------------------------------------------------------------- #
# Core functionality
# --------------------------------------------------------------------------- #


class EmailBot:
    """Bot that sends personalised emails to a list of recipients."""

    def __init__(
        self,
        smtp_cfg: SMTPConfig,
        subject_template: str,
        body_template: str,
        sender_email: str,
        dry_run: bool = False,
    ) -> None:
        """
        Parameters
        ----------
        smtp_cfg: SMTPConfig
            SMTP connection settings.
        subject_template: str
            Template for the email subject (uses :class:`string.Template` syntax).
        body_template: str
            Template for the email body (plain‑text, Template syntax).
        sender_email: str
            The email address that will appear in the ``From`` header.
        dry_run: bool
            If true, no email will actually be sent; actions are only logged.
        """
        self.smtp_cfg = smtp_cfg
        self.subject_template = Template(subject_template)
        self.body_template = Template(body_template)
        self.sender_email = sender_email
        self.dry_run = dry_run

    @staticmethod
    def load_recipients(csv_path: Path) -> List[Mapping[str, str]]:
        """
        Load recipients from a CSV file.

        The CSV must contain a header row. Each row is turned into a dictionary
        where the keys are the column names.

        Parameters
        ----------
        csv_path: Path
            Path to the CSV file.

        Returns
        -------
        List[Mapping[str, str]]
            List of recipient dictionaries.
        """
        if not csv_path.is_file():
            raise FileNotFoundError(f"Recipients file not found: {csv_path}")

        recipients: List[Mapping[str, str]] = []
        with csv_path.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for line_no, row in enumerate(reader, start=2):
                if not row:
                    LOGGER.warning("Empty row at line %d ignored", line_no)
                    continue
                recipients.append(row)
        LOGGER.info("Loaded %d recipient(s) from %s", len(recipients), csv_path)
        return recipients

    def _render(self, template: Template, context: Mapping[str, str]) -> str:
        """Render a Template with the supplied context, raising if key missing."""
        try:
            return template.substitute(context)
        except KeyError as exc:
            missing = exc.args[0]
            raise ValueError(
                f"Missing placeholder '{missing}' in context for recipient {context}"
            ) from exc

    def _build_message(
        self, recipient: Mapping[str, str]
    ) -> EmailMessage:
        """Create an EmailMessage ready for sending."""
        subject = self._render(self.subject_template, recipient)
        body = self._render(self.body_template, recipient)

        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = self.sender_email
        msg["To"] = recipient["email"]
        msg.set_content(body)
        return msg

    def send_all(
        self,
        recipients: List[Mapping[str, str]],
        batch_size: Optional[int] = None,
    ) -> None:
        """
        Send emails to all recipients.

        Parameters
        ----------
        recipients: List[Mapping[str, str]]
            Recipient dictionaries; each must contain at least an ``email`` key.
        batch_size: Optional[int]
            If provided, emails are sent in batches of this size (useful for
            throttling). ``None`` means send them all at once.
        """
        if not recipients:
            LOGGER.warning("No recipients to send to.")
            return

        # Validate recipient format early
        for rec in recipients:
            if "email" not in rec or not rec["email"]:
                raise ValueError(f"Recipient missing 'email' field: {rec}")

        total = len(recipients)
        batches = (
            [recipients[i : i + batch_size] for i in range(0, total, batch_size)]
            if batch_size
            else [recipients]
        )
        LOGGER.info(
            "Starting to send %d email(s) in %d batch(es).", total, len(batches)
        )

        for batch_no, batch in enumerate(batches, start=1):
            LOGGER.info("Processing batch %d with %d email(s).", batch_no, len(batch))
            if self.dry_run:
                for rec in batch:
                    LOGGER.info("[DRY RUN] Would send to %s", rec["email"])
                continue

            try:
                self._send_batch(batch)
                LOGGER.info("Batch %d sent successfully.", batch_no)
            except Exception as exc:
                LOGGER.exception("Failed to send batch %d: %s", batch_no, exc)

    def _send_batch(self, batch: List[Mapping[str, str]]) -> None:
        """Send a batch of messages using a single SMTP connection."""
        context = ssl.create_default_context()
        if self.smtp_cfg.use_tls and self.smtp_cfg.port == 587:
            smtp_class = smtplib.SMTP
        else:
            smtp_class = smtplib.SMTP_SSL

        with smtp_class(
            host=self.smtp_cfg.host,
            port=self.smtp_cfg.port,
            context=context,
        ) as server:
            if self.smtp_cfg.use_tls and self.smtp_cfg.port != 465:
                server.starttls(context=context)

            if self.smtp_cfg.username:
                server.login(self.smtp_cfg.username, self.smtp_cfg.password)

            for rec in batch:
                msg = self._build_message(rec)
                server.send_message(msg)
                LOGGER.info("Sent email to %s", rec["email"])


# --------------------------------------------------------------------------- #
# Example usage (can be used as script entry point)
# --------------------------------------------------------------------------- #

def _main() -> None:
    import argparse
    from getpass import getpass

    parser = argparse.ArgumentParser(description="Send personalised emails.")
    parser.add_argument(
        "recipients_csv",
        type=Path,
        help="Path to CSV file containing recipient data (must include 'email' column).",
    )
    parser.add_argument(
        "subject_template",
        type=Path,
        help="Path to a text file containing the subject template.",
    )
    parser.add_argument(
        "body_template",
        type=Path,
        help="Path to a text file containing the email body template.",
    )
    parser.add_argument(
        "--sender",
        required=True,
        help="Email address that will appear in the From header.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and render messages but do not send them.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=None,
        help="Optional batch size for sending emails.",
    )
    args = parser.parse_args()

    # Load SMTP configuration from environment; ask for password if missing.
    smtp_cfg = SMTPConfig.from_env()
    if smtp_cfg.username and not smtp_cfg.password:
        smtp_cfg = SMTPConfig(
            host=smtp_cfg.host,
            port=smtp_cfg.port,
            username=smtp_cfg.username,
            password=getpass(prompt="SMTP password: "),
            use_tls=smtp_cfg.use_tls,
        )

    # Read templates
    subject_tpl = args.subject_template.read_text(encoding="utf-8")
    body_tpl = args.body_template.read_text(encoding="utf-8")

    bot = EmailBot(
        smtp_cfg=smtp_cfg,
        subject_template=subject_tpl,
        body_template=body_tpl,
        sender_email=args.sender,
        dry_run=args.dry_run,
    )

    recipients = bot.load_recipients(args.recipients_csv)
    bot.send_all(recipients, batch_size=args.batch_size)


if __name__ == "__main__":
    _main()