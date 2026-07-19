"""
### Task 13: Task Scheduler (APScheduler + SQLite)

Schedules jobs (interval, cron, or one-off date), persists schedule metadata
and execution history to SQLite, and optionally emails a notification when
a job completes.

Requirements:
    pip install apscheduler sqlalchemy

Run:
    python 13_task_scheduler.py
"""

from __future__ import annotations

import logging
import smtplib
from datetime import datetime
from email.message import EmailMessage
from typing import Any, Callable, Dict, Optional

from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import Column, DateTime, Integer, String, Text, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("task_scheduler")

Base = declarative_base()


class ExecutionHistory(Base):
    """SQLAlchemy model recording each job execution attempt."""

    __tablename__ = "execution_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String(128), nullable=False)
    status = Column(String(16), nullable=False)  # "success" or "error"
    detail = Column(Text, nullable=True)
    executed_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class EmailNotifier:
    """Sends email notifications via SMTP. Falls back to logging if unconfigured."""

    def __init__(
        self,
        smtp_host: Optional[str] = None,
        smtp_port: int = 587,
        username: Optional[str] = None,
        password: Optional[str] = None,
        sender: Optional[str] = None,
    ) -> None:
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.username = username
        self.password = password
        self.sender = sender or username

    def send(self, to_address: str, subject: str, body: str) -> None:
        """Sends an email, or logs it if SMTP is not configured (e.g. in dev/test)."""
        if not self.smtp_host:
            logger.info("[EMAIL STUB] To: %s | Subject: %s | Body: %s", to_address, subject, body)
            return

        message = EmailMessage()
        message["From"] = self.sender
        message["To"] = to_address
        message["Subject"] = subject
        message.set_content(body)

        try:
            with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=10) as server:
                server.starttls()
                if self.username and self.password:
                    server.login(self.username, self.password)
                server.send_message(message)
            logger.info("Notification email sent to %s", to_address)
        except (smtplib.SMTPException, OSError) as exc:
            logger.error("Failed to send notification email to %s: %s", to_address, exc)


class TaskSchedulerService:
    """Wraps APScheduler with SQLite persistence and execution history logging."""

    def __init__(
        self,
        db_url: str = "sqlite:///scheduler.db",
        notifier: Optional[EmailNotifier] = None,
        notify_address: Optional[str] = None,
    ) -> None:
        self.engine = create_engine(db_url)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

        jobstores = {"default": SQLAlchemyJobStore(engine=self.engine)}
        self.scheduler = BackgroundScheduler(jobstores=jobstores)
        self.scheduler.add_listener(
            self._on_job_event, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR
        )

        self.notifier = notifier or EmailNotifier()
        self.notify_address = notify_address

    def _on_job_event(self, event: Any) -> None:
        """APScheduler event listener that records execution history and notifies."""
        status = "error" if event.exception else "success"
        detail = str(event.exception) if event.exception else "completed successfully"

        session = self.Session()
        try:
            record = ExecutionHistory(job_id=event.job_id, status=status, detail=detail)
            session.add(record)
            session.commit()
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to record execution history: %s", exc)
            session.rollback()
        finally:
            session.close()

        if self.notify_address:
            self.notifier.send(
                self.notify_address,
                subject=f"Job '{event.job_id}' {status}",
                body=f"Job '{event.job_id}' finished with status '{status}': {detail}",
            )

    def add_interval_job(
        self, func: Callable[..., Any], job_id: str, seconds: int, kwargs: Optional[Dict] = None
    ) -> None:
        """Schedules a job that runs at a fixed interval, in seconds."""
        self.scheduler.add_job(
            func, "interval", seconds=seconds, id=job_id, kwargs=kwargs or {}, replace_existing=True
        )
        logger.info("Scheduled interval job '%s' every %ss", job_id, seconds)

    def add_cron_job(self, func: Callable[..., Any], job_id: str, cron_expression: str) -> None:
        """Schedules a job using a standard 5-field cron expression."""
        from apscheduler.triggers.cron import CronTrigger

        trigger = CronTrigger.from_crontab(cron_expression)
        self.scheduler.add_job(func, trigger, id=job_id, replace_existing=True)
        logger.info("Scheduled cron job '%s' with expression '%s'", job_id, cron_expression)

    def add_one_off_job(self, func: Callable[..., Any], job_id: str, run_date: datetime) -> None:
        """Schedules a job to run exactly once at the given datetime."""
        self.scheduler.add_job(func, "date", run_date=run_date, id=job_id, replace_existing=True)
        logger.info("Scheduled one-off job '%s' at %s", job_id, run_date.isoformat())

    def remove_job(self, job_id: str) -> None:
        """Removes a scheduled job by id."""
        try:
            self.scheduler.remove_job(job_id)
            logger.info("Removed job '%s'", job_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not remove job '%s': %s", job_id, exc)

    def get_history(self, job_id: Optional[str] = None, limit: int = 50):
        """Returns recent execution history, optionally filtered by job_id."""
        session = self.Session()
        try:
            query = session.query(ExecutionHistory).order_by(ExecutionHistory.executed_at.desc())
            if job_id:
                query = query.filter_by(job_id=job_id)
            return query.limit(limit).all()
        finally:
            session.close()

    def start(self) -> None:
        """Starts the background scheduler."""
        self.scheduler.start()
        logger.info("Scheduler started")

    def shutdown(self) -> None:
        """Gracefully stops the scheduler."""
        self.scheduler.shutdown()
        logger.info("Scheduler shut down")


def sample_job(message: str = "Hello from scheduled job") -> None:
    """Example job function to demonstrate scheduling."""
    logger.info("Running sample_job: %s", message)


if __name__ == "__main__":
    service = TaskSchedulerService(notify_address=None)
    service.start()

    service.add_interval_job(sample_job, job_id="heartbeat", seconds=30, kwargs={"message": "tick"})

    try:
        import time

        logger.info("Scheduler running. Press Ctrl+C to exit.")
        while True:
            time.sleep(2)
    except (KeyboardInterrupt, SystemExit):
        service.shutdown()
