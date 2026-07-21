"""
task_scheduler.py

A lightweight, file‑persisted task scheduler supporting daily, hourly and
minute‑based frequencies. Jobs are stored in JSON, executed in a background
thread, and each execution is logged. The implementation uses only the Python
standard library and the widely‑used ``importlib`` package for dynamic imports.

Typical usage::

    from task_scheduler import Scheduler

    scheduler = Scheduler(persist_path="jobs.json")
    scheduler.add_job(
        name="example",
        func_path="my_module:my_function",
        frequency="daily",
        schedule_time="14:30",
    )
    scheduler.start()
"""

from __future__ import annotations

import importlib
import json
import logging
import threading
import traceback
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

# Configure module‑level logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
_handler = logging.StreamHandler()
_formatter = logging.Formatter(
    fmt="%(asctime)s %(levelname)s %(name)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
)
_handler.setFormatter(_formatter)
logger.addHandler(_handler)


class SchedulerError(Exception):
    """Base exception for all scheduler‑related errors."""


class JobNotFoundError(SchedulerError):
    """Raised when attempting to remove or modify a non‑existent job."""


@dataclass
class Job:
    """Representation of a scheduled job."""

    job_id: str
    name: str
    func_path: str  # e.g. "my_module:my_function"
    frequency: str  # "daily", "hourly", "minute"
    schedule_time: Optional[str] = None  # "HH:MM" for daily/hourly
    interval: Optional[int] = None  # minutes for "minute" frequency
    next_run: Optional[str] = None  # ISO format datetime, computed on load

    def to_dict(self) -> Dict[str, Any]:
        """Serialise the job to a dict suitable for JSON storage."""
        data = asdict(self)
        # Remove None values for cleaner JSON
        return {k: v for k, v in data.items() if v is not None}

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "Job":
        """Create a Job instance from a dictionary."""
        return Job(**data)


class Scheduler:
    """
    Scheduler that manages jobs, persists them to disk, and executes them in a
    background thread.
    """

    def __init__(self, persist_path: str | Path = "scheduler_jobs.json") -> None:
        """
        Initialise the scheduler.

        Args:
            persist_path: Path to the JSON file used for persisting jobs.
        """
        self._persist_path = Path(persist_path).expanduser().resolve()
        self._jobs: Dict[str, Job] = {}
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.RLock()
        self._load_jobs()

    def _load_jobs(self) -> None:
        """Load jobs from the persistence file, handling I/O errors gracefully."""
        if not self._persist_path.is_file():
            logger.info("No persisted job file found at %s", self._persist_path)
            return
        try:
            with self._persist_path.open("r", encoding="utf-8") as f:
                raw_jobs: List[Dict[str, Any]] = json.load(f)
            with self._lock:
                self._jobs = {
                    job_data["job_id"]: Job.from_dict(job_data) for job_data in raw_jobs
                }
            logger.info("Loaded %d job(s) from %s", len(self._jobs), self._persist_path)
        except (OSError, json.JSONDecodeError) as exc:
            logger.error("Failed to load jobs: %s", exc)
            raise SchedulerError(f"Could not load jobs from {self._persist_path}") from exc

    def _save_jobs(self) -> None:
        """Persist current jobs to the JSON file, handling I/O errors."""
        try:
            with self._persist_path.open("w", encoding="utf-8") as f:
                json.dump([job.to_dict() for job in self._jobs.values()], f, indent=2)
            logger.info("Persisted %d job(s) to %s", len(self._jobs), self._persist_path)
        except OSError as exc:
            logger.error("Failed to persist jobs: %s", exc)
            raise SchedulerError(f"Could not save jobs to {self._persist_path}") from exc

    def add_job(
        self,
        name: str,
        func_path: str,
        frequency: str,
        schedule_time: Optional[str] = None,
        interval: Optional[int] = None,
    ) -> str:
        """
        Add a new job to the scheduler.

        Args:
            name: Human‑readable name of the job.
            func_path: Fully qualified function path in the form ``module:function``.
            frequency: One of ``"daily"``, ``"hourly"``, ``"minute"``.
            schedule_time: ``"HH:MM"`` string required for ``daily`` and ``hourly``.
            interval: Number of minutes between executions for ``minute`` frequency.

        Returns:
            The unique identifier of the created job.

        Raises:
            SchedulerError: If validation fails.
        """
        if frequency not in {"daily", "hourly", "minute"}:
            raise SchedulerError("Invalid frequency; must be 'daily', 'hourly', or 'minute'.")

        if frequency in {"daily", "hourly"}:
            if not schedule_time:
                raise SchedulerError(f"`schedule_time` required for frequency '{frequency}'.")
            try:
                datetime.strptime(schedule_time, "%H:%M")
            except ValueError as exc:
                raise SchedulerError("schedule_time must be in HH:MM 24‑hour format.") from exc
        elif frequency == "minute":
            if not isinstance(interval, int) or interval <= 0:
                raise SchedulerError("`interval` must be a positive integer for minute frequency.")

        # Verify that the function can be imported safely
        module_name, _, func_name = func_path.partition(":")
        if not module_name or not func_name:
            raise SchedulerError("func_path must be in 'module:function' format.")
        try:
            module = importlib.import_module(module_name)
            getattr(module, func_name)
        except (ImportError, AttributeError) as exc:
            raise SchedulerError(f"Unable to locate function '{func_path}'.") from exc

        job_id = str(uuid.uuid4())
        job = Job(
            job_id=job_id,
            name=name,
            func_path=func_path,
            frequency=frequency,
            schedule_time=schedule_time,
            interval=interval,
        )
        job.next_run = self._compute_next_run(job).isoformat()
        with self._lock:
            self._jobs[job_id] = job
            self._save_jobs()
        logger.info("Added job %s (%s)", job_id, name)
        return job_id

    def remove_job(self, job_id: str) -> None:
        """
        Remove a job from the scheduler.

        Args:
            job_id: Identifier of the job to remove.

        Raises:
            JobNotFoundError: If the job does not exist.
            SchedulerError: If persistence fails.
        """
        with self._lock:
            if job_id not in self._jobs:
                raise JobNotFoundError(f"Job with id {job_id} not found.")
            removed = self._jobs.pop(job_id)
            self._save_jobs()
        logger.info("Removed job %s (%s)", job_id, removed.name)

    def _import_callable(self, func_path: str) -> Callable[..., Any]:
        """
        Import a callable from a ``module:function`` string.

        Args:
            func_path: Path to the function.

        Returns:
            Callable object.

        Raises:
            SchedulerError: If import fails.
        """
        module_name, _, func_name = func_path.partition(":")
        try:
            module = importlib.import_module(module_name)
            func = getattr(module, func_name)
            if not callable(func):
                raise TypeError(f"'{func_path}' is not callable.")
            return func
        except Exception as exc:
            raise SchedulerError(f"Failed to import function '{func_path}'.") from exc

    def _compute_next_run(self, job: Job) -> datetime:
        """
        Compute the next execution time for a job based on its frequency.

        Args:
            job: Job instance.

        Returns:
            A timezone‑naïve ``datetime`` representing the next run.

        Raises:
            SchedulerError: If the job configuration is invalid.
        """
        now = datetime.now()
        if job.frequency == "daily":
            hour, minute = map(int, job.schedule_time.split(":"))
            candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if candidate <= now:
                candidate += timedelta(days=1)
            return candidate
        if job.frequency == "hourly":
            minute = int(job.schedule_time.split(":")[1])
            candidate = now.replace(minute=minute, second=0, microsecond=0)
            if candidate <= now:
                candidate += timedelta(hours=1)
            return candidate
        if job.frequency == "minute":
            interval = job.interval or 1
            # Round up to the next interval boundary
            minutes = (now.minute // interval + 1) * interval
            candidate = now.replace(minute=0, second=0, microsecond=0) + timedelta(
                minutes=minutes
            )
            if candidate <= now:
                candidate += timedelta(minutes=interval)
            return candidate
        raise SchedulerError(f"Unsupported frequency '{job.frequency}' for job {job.job_id}")

    def _run_job(self, job: Job) -> None:
        """
        Execute a job's target function, handling exceptions and logging.

        Args:
            job: Job to execute.
        """
        logger.info("Executing job %s (%s)", job.job_id, job.name)
        try:
            func = self._import_callable(job.func_path)
            func()
            logger.info("Job %s completed successfully.", job.job_id)
        except Exception as exc:
            logger.error(
                "Job %s raised an exception: %s\n%s",
                job.job_id,
                exc,
                traceback.format_exc(),
            )

    def _scheduler_loop(self) -> None:
        """Background loop that checks for due jobs and runs them."""
        logger.info("Scheduler thread started.")
        while not self._stop_event.is_set():
            now = datetime.now()
            due_jobs: List[Job] = []
            with self._lock:
                for job in self._jobs.values():
                    next_run = datetime.fromisoformat(job.next_run)
                    if next_run <= now:
                        due_jobs.append(job)

            for job in due_jobs:
                self._run_job(job)
                # Reschedule next run
                with self._lock:
                    job.next_run = self._compute_next_run(job).isoformat()
                    self._save_jobs()

            # Sleep a short period; using Event.wait allows immediate wake‑up on stop.
            self._stop_event.wait(30)

        logger.info("Scheduler thread stopped.")

    def start(self) -> None:
        """
        Start the scheduler's background thread.

        Raises:
            SchedulerError: If the scheduler is already running.
        """
        if self._thread and self._thread.is_alive():
            raise SchedulerError("Scheduler is already running.")
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._scheduler_loop, daemon=True)
        self._thread.start()
        logger.info("Scheduler started.")

    def stop(self) -> None:
        """
        Stop the scheduler's background thread and wait for it to finish.
        """
        self._stop_event.set()
        if self._thread:
            self._thread.join()
            logger.info("Scheduler stopped.")

    def list_jobs(self) -> List[Dict[str, Any]]:
        """
        Return a list of all scheduled jobs with their metadata.

        Returns:
            List of dictionaries representing jobs.
        """
        with self._lock:
            return [job.to_dict() for job in self._jobs.values()]