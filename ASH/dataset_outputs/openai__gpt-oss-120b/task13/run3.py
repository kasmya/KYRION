"""
task_scheduler.py

A lightweight, persistent task scheduler supporting daily, hourly, and minute
frequencies. Jobs can be added, removed, and listed. Executions are logged with
success/failure details. Persistence is achieved via an SQLite job store.

Only the Python standard library and the widely‑used ``APScheduler`` package are
required.
"""

from __future__ import annotations

import importlib
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping, MutableMapping, Sequence

from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED, JobExecutionEvent
from apscheduler.job import Job
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

# --------------------------------------------------------------------------- #
# Logging configuration
# --------------------------------------------------------------------------- #
LOG_FILE = Path(__file__).with_name("task_scheduler.log")
LOGGER = logging.getLogger("task_scheduler")
LOGGER.setLevel(logging.INFO)
_formatter = logging.Formatter(
    "%(asctime)s - %(levelname)s - %(name)s - %(message)s"
)
_handler = logging.handlers.RotatingFileHandler(
    LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
)
_handler.setFormatter(_formatter)
LOGGER.addHandler(_handler)


# --------------------------------------------------------------------------- #
# Exceptions
# --------------------------------------------------------------------------- #
class SchedulerError(Exception):
    """Base exception for scheduler‑related errors."""


class JobNotFoundError(SchedulerError):
    """Raised when a job with the requested identifier does not exist."""


class InvalidFrequencyError(SchedulerError):
    """Raised when an unsupported frequency string is supplied."""


class FunctionImportError(SchedulerError):
    """Raised when a job function cannot be imported safely."""


# --------------------------------------------------------------------------- #
# Scheduler implementation
# --------------------------------------------------------------------------- #
class TaskScheduler:
    """
    Persistent task scheduler using APScheduler.

    Jobs are stored in an SQLite database (default ``tasks.sqlite``) and survive
    process restarts. Supported frequencies are ``daily``, ``hourly`` and
    ``minute``.
    """

    _SUPPORTED_FREQUENCIES = {"daily", "hourly", "minute"}

    def __init__(self, db_url: str = "sqlite:///tasks.sqlite") -> None:
        """
        Initialise the scheduler with a persistent job store.

        Args:
            db_url: SQLAlchemy URL for the job store (defaults to a local SQLite file).

        Raises:
            SchedulerError: If the APScheduler cannot be instantiated.
        """
        try:
            jobstores = {"default": SQLAlchemyJobStore(url=db_url)}
            self._scheduler = BackgroundScheduler(jobstores=jobstores)
            self._scheduler.add_listener(self._job_listener, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)
            self._scheduler.start()
            LOGGER.info("TaskScheduler started with DB %s", db_url)
        except Exception as exc:
            LOGGER.exception("Failed to start scheduler")
            raise SchedulerError("Failed to initialise the scheduler") from exc

    # ------------------------------------------------------------------- #
    # Public API
    # ------------------------------------------------------------------- #
    def add_job(
        self,
        name: str,
        func_path: str,
        frequency: str,
        start_time: datetime | None = None,
        args: Sequence[Any] | None = None,
        kwargs: Mapping[str, Any] | None = None,
    ) -> None:
        """
        Register a new job.

        The target function is identified by ``func_path`` (e.g.
        ``"my_module.my_function"``). The function must be importable and callable.

        Args:
            name: Unique identifier for the job.
            func_path: Dotted path to the callable to execute.
            frequency: One of ``"daily"``, ``"hourly"``, or ``"minute"``.
            start_time: Optional earliest run time; defaults to now.
            args: Positional arguments for the job function.
            kwargs: Keyword arguments for the job function.

        Raises:
            InvalidFrequencyError: If ``frequency`` is not supported.
            FunctionImportError: If the target function cannot be imported.
            SchedulerError: For any APScheduler‑related failure.
        """
        if frequency not in self._SUPPORTED_FREQUENCIES:
            raise InvalidFrequencyError(f"Unsupported frequency: {frequency}")

        func = self._load_callable(func_path)

        trigger = self._build_trigger(frequency, start_time)

        try:
            self._scheduler.add_job(
                func,
                trigger,
                id=name,
                name=name,
                args=args or [],
                kwargs=dict(kwargs) if kwargs else {},
                replace_existing=False,
                misfire_grace_time=60,
                coalesce=True,
            )
            LOGGER.info("Added job %s with frequency %s", name, frequency)
        except Exception as exc:
            LOGGER.exception("Failed to add job %s", name)
            raise SchedulerError(f"Could not add job '{name}'") from exc

    def remove_job(self, name: str) -> None:
        """
        Remove a scheduled job.

        Args:
            name: Identifier of the job to delete.

        Raises:
            JobNotFoundError: If the job does not exist.
            SchedulerError: For any APScheduler‑related failure.
        """
        try:
            self._scheduler.remove_job(job_id=name)
            LOGGER.info("Removed job %s", name)
        except Exception as exc:
            if "JobLookupError" in str(exc):
                raise JobNotFoundError(f"Job '{name}' not found") from exc
            LOGGER.exception("Failed to remove job %s", name)
            raise SchedulerError(f"Could not remove job '{name}'") from exc

    def list_jobs(self) -> list[dict[str, Any]]:
        """
        Return a list of all scheduled jobs with basic metadata.

        Returns:
            A list of dictionaries, each containing ``id``, ``name``,
            ``next_run_time`` and ``trigger`` description.
        """
        jobs_info: list[dict[str, Any]] = []
        for job in self._scheduler.get_jobs():
            jobs_info.append(
                {
                    "id": job.id,
                    "name": job.name,
                    "next_run_time": job.next_run_time,
                    "trigger": str(job.trigger),
                }
            )
        return jobs_info

    def shutdown(self, wait: bool = True) -> None:
        """
        Gracefully shut down the scheduler.

        Args:
            wait: If ``True``, block until all running jobs finish.
        """
        self._scheduler.shutdown(wait=wait)
        LOGGER.info("TaskScheduler shutdown (wait=%s)", wait)

    # ------------------------------------------------------------------- #
    # Internal helpers
    # ------------------------------------------------------------------- #
    @staticmethod
    def _load_callable(func_path: str) -> Callable[..., Any]:
        """
        Safely import a callable given its dotted path.

        Args:
            func_path: Dotted module path to the callable.

        Returns:
            The imported callable.

        Raises:
            FunctionImportError: If the import fails or the object is not callable.
        """
        try:
            module_path, attr_name = func_path.rsplit(".", 1)
            module = importlib.import_module(module_path)
            func = getattr(module, attr_name)
            if not callable(func):
                raise TypeError(f"Object '{func_path}' is not callable")
            return func
        except Exception as exc:
            LOGGER.exception("Failed to import function %s", func_path)
            raise FunctionImportError(f"Cannot import callable '{func_path}'") from exc

    @staticmethod
    def _build_trigger(
        frequency: str, start_time: datetime | None
    ) -> CronTrigger:
        """
        Build an APScheduler ``CronTrigger`` based on the requested frequency.

        Args:
            frequency: ``"daily"``, ``"hourly"``, or ``"minute"``.
            start_time: Optional earliest run time.

        Returns:
            Configured ``CronTrigger`` instance.
        """
        if frequency == "daily":
            return CronTrigger(hour=0, minute=0, start_date=start_time)
        if frequency == "hourly":
            return CronTrigger(minute=0, start_date=start_time)
        # frequency == "minute"
        return CronTrigger(second=0, start_date=start_time)

    @staticmethod
    def _job_listener(event: JobExecutionEvent) -> None:
        """
        Listener that logs job execution outcomes.

        Args:
            event: APScheduler job execution event.
        """
        if event.exception:
            LOGGER.error(
                "Job %s failed with exception: %s",
                event.job_id,
                event.exception,
                exc_info=event.exception,
            )
        else:
            LOGGER.info("Job %s executed successfully", event.job_id)


# --------------------------------------------------------------------------- #
# Example usage (executed only when run as a script)
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    # Simple demonstration functions
    def hello(name: str = "world") -> None:
        print(f"Hello, {name}! Current time: {datetime.now()}")

    # Register demo function in the current module for import by dotted path
    current_module = sys.modules[__name__]
    setattr(current_module, "hello", hello)

    scheduler = TaskScheduler()
    try:
        scheduler.add_job(
            name="greeting",
            func_path=f"{__name__}.hello",
            frequency="minute",
            args=["APScheduler"],
        )
        print("Scheduler is running. Press Ctrl+C to exit.")
        while True:
            pass  # Keep the main thread alive
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        scheduler.shutdown()