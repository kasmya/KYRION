"""
task_scheduler.py

A lightweight, persistent, and extensible task scheduler built on APScheduler.
Features:
- Add / remove / list scheduled jobs
- Persistent storage via SQLite (SQLAlchemyJobStore)
- Execution logging to file and console
- Supports daily, hourly, minute-level schedules
- Type hints, extensive docstrings, and robust error handling
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED, JobExecutionEvent
from apscheduler.job import Job
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

# --------------------------------------------------------------------------- #
# Logging configuration
# --------------------------------------------------------------------------- #
LOG_DIR = Path(os.getenv("TASK_SCHEDULER_LOG_DIR", ".")) / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

LOGGER = logging.getLogger("TaskScheduler")
LOGGER.setLevel(logging.INFO)
formatter = logging.Formatter(
    "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s", "%Y-%m-%d %H:%M:%S"
)

# file handler
file_handler = logging.FileHandler(LOG_DIR / "scheduler.log")
file_handler.setFormatter(formatter)
LOGGER.addHandler(file_handler)

# console handler
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(formatter)
LOGGER.addHandler(console_handler)


# --------------------------------------------------------------------------- #
# Custom Exceptions
# --------------------------------------------------------------------------- #
class SchedulerError(Exception):
    """Base exception for scheduler related errors."""


class JobAlreadyExistsError(SchedulerError):
    """Raised when trying to add a job with a duplicate identifier."""


class JobNotFoundError(SchedulerError):
    """Raised when trying to manipulate a non‑existent job."""


# --------------------------------------------------------------------------- #
# Helper Types
# --------------------------------------------------------------------------- #
TriggerArgs = Dict[str, Union[int, str, datetime]]


# --------------------------------------------------------------------------- #
# Core Scheduler Implementation
# --------------------------------------------------------------------------- #
class TaskScheduler:
    """
    Wrapper around APScheduler providing a simple API for adding, removing,
    and persisting scheduled tasks.

    Parameters
    ----------
    db_path : str, optional
        Filesystem path to the SQLite database used for job persistence.
        If omitted, a file named ``tasks.sqlite`` is created in the current
        working directory.
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        sqlite_path = db_path or str(Path.cwd() / "tasks.sqlite")
        self._jobstore = {"default": SQLAlchemyJobStore(url=f"sqlite:///{sqlite_path}")}

        self._scheduler = BackgroundScheduler(jobstores=self._jobstore)
        self._scheduler.add_listener(self._job_listener, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)
        self._scheduler.start()
        LOGGER.info("TaskScheduler initialized with jobstore at %s", sqlite_path)

    # ------------------------------------------------------------------- #
    # Public API
    # ------------------------------------------------------------------- #
    def add_task(
        self,
        job_id: str,
        func: Callable[..., Any],
        trigger: str,
        trigger_args: Optional[TriggerArgs] = None,
        args: Optional[List[Any]] = None,
        kwargs: Optional[Dict[str, Any]] = None,
        replace_existing: bool = False,
    ) -> Job:
        """
        Schedule a new job.

        Parameters
        ----------
        job_id : str
            Unique identifier for the job.
        func : Callable[..., Any]
            Callable to be executed. Must be importable (no lambdas/closures).
        trigger : str
            One of ``'cron'`` or ``'interval'``.
        trigger_args : dict, optional
            Arguments passed to the underlying APScheduler trigger.
            For ``cron`` you may provide ``hour``, ``minute``, ``day`` etc.
            For ``interval`` you may provide ``seconds``, ``minutes``, ``hours``.
        args : list, optional
            Positional arguments for ``func``.
        kwargs : dict, optional
            Keyword arguments for ``func``.
        replace_existing : bool, default False
            If ``True`` and a job with ``job_id`` exists, it will be replaced.

        Returns
        -------
        apscheduler.job.Job
            The created APScheduler job instance.

        Raises
        ------
        JobAlreadyExistsError
            If a job with the given ``job_id`` already exists and
            ``replace_existing`` is ``False``.
        SchedulerError
            For any other scheduling failure.
        """
        if not callable(func):
            raise SchedulerError("Provided func must be callable.")

        if job_id in self._scheduler.get_jobs():
            if not replace_existing:
                raise JobAlreadyExistsError(f"Job with id '{job_id}' already exists.")
            self.remove_task(job_id)

        trigger_args = trigger_args or {}
        logger = LOGGER

        try:
            if trigger == "cron":
                trigger_obj = CronTrigger(**trigger_args)  # type: ignore[arg-type]
            elif trigger == "interval":
                trigger_obj = IntervalTrigger(**trigger_args)  # type: ignore[arg-type]
            else:
                raise SchedulerError("Unsupported trigger type. Use 'cron' or 'interval'.")

            job = self._scheduler.add_job(
                func,
                trigger=trigger_obj,
                id=job_id,
                args=args or [],
                kwargs=kwargs or {},
                replace_existing=replace_existing,
                misfire_grace_time=60,
                coalesce=True,
                max_instances=1,
                name=func.__name__,
            )
            logger.info("Added job '%s' with trigger %s", job_id, trigger)
            return job
        except Exception as exc:
            logger.exception("Failed to add job '%s': %s", job_id, exc)
            raise SchedulerError(f"Failed to add job '{job_id}': {exc}") from exc

    def remove_task(self, job_id: str) -> None:
        """
        Remove a scheduled job.

        Parameters
        ----------
        job_id : str
            Identifier of the job to remove.

        Raises
        ------
        JobNotFoundError
            If the job does not exist.
        """
        try:
            self._scheduler.remove_job(job_id)
            LOGGER.info("Removed job '%s'", job_id)
        except Exception as exc:
            LOGGER.exception("Error removing job '%s': %s", job_id, exc)
            raise JobNotFoundError(f"Job '{job_id}' not found.") from exc

    def list_tasks(self) -> List[Dict[str, Any]]:
        """
        Retrieve a summary of all scheduled jobs.

        Returns
        -------
        list of dict
            Each dict contains ``id``, ``name``, ``next_run_time`` and ``trigger``.
        """
        jobs_info = []
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
        Gracefully shutdown the scheduler.

        Parameters
        ----------
        wait : bool, default True
            Wait for all running jobs to finish before shutting down.
        """
        LOGGER.info("Shutting down TaskScheduler...")
        self._scheduler.shutdown(wait=wait)
        LOGGER.info("TaskScheduler stopped.")

    # ------------------------------------------------------------------- #
    # Private helpers
    # ------------------------------------------------------------------- #
    @staticmethod
    def _job_listener(event: JobExecutionEvent) -> None:
        """
        APScheduler listener that logs job execution results.
        """
        job_id = event.job_id
        if event.exception:
            LOGGER.error(
                "Job '%s' failed with exception: %s", job_id, event.exception, exc_info=event.exception
            )
        else:
            LOGGER.info("Job '%s' executed successfully.", job_id)


# --------------------------------------------------------------------------- #
# Example usage (executed only when run as a script)
# --------------------------------------------------------------------------- #
if __name__ == "__main__":

    def sample_task(message: str, *, repeat: int = 1) -> None:
        """A simple demonstration task."""
        for i in range(repeat):
            LOGGER.info("Task says: %s (iteration %d)", message, i + 1)

    scheduler = TaskScheduler()

    # Add a minute‑level interval job (runs every 2 minutes