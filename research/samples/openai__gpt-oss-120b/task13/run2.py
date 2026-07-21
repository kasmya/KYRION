"""
task_scheduler.py

A lightweight task scheduler supporting daily, hourly, and minute‑based frequencies.
Jobs can be added, removed, listed, and are persisted in a SQLite database.
Executions are logged with timestamps and error information.

Only the Python standard library is used.
"""

from __future__ import annotations

import importlib
import logging
import sqlite3
import threading
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Literal, Optional, Tuple, Union

# --------------------------------------------------------------------------- #
# Types and constants
# --------------------------------------------------------------------------- #

ScheduleType = Literal["daily", "hourly", "minute"]
JobID = int

# --------------------------------------------------------------------------- #
# Exceptions
# --------------------------------------------------------------------------- #


class SchedulerError(Exception):
    """Base class for scheduler related errors."""


class JobNotFoundError(SchedulerError):
    """Raised when a job cannot be found in the storage."""


class InvalidScheduleError(SchedulerError):
    """Raised when a schedule definition is invalid."""


# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Job:
    """Immutable representation of a scheduled job."""

    job_id: JobID
    name: str
    schedule_type: ScheduleType
    # For daily: "HH:MM", for hourly: minute (0-59), for minute: interval in minutes
    schedule_value: Union[str, int]
    function_path: str  # e.g. "my_pkg.module.func"
    args: Tuple[Any, ...] = ()
    kwargs: Dict[str, Any] = None

    def next_run(self, after: Optional[datetime] = None) -> datetime:
        """Calculate the next run time after the given datetime (UTC)."""
        now = after or datetime.utcnow()
        if self.schedule_type == "daily":
            hour, minute = map(int, self.schedule_value.split(":"))
            candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if candidate <= now:
                candidate += timedelta(days=1)
            return candidate
        if self.schedule_type == "hourly":
            minute = int(self.schedule_value)
            candidate = now.replace(minute=minute, second=0, microsecond=0)
            if candidate <= now:
                candidate += timedelta(hours=1)
            return candidate
        if self.schedule_type == "minute":
            interval = int(self.schedule_value)
            elapsed = (now - datetime.min) % timedelta(minutes=interval)
            return now + (timedelta(minutes=interval) - elapsed)
        raise InvalidScheduleError(f"Unsupported schedule type: {self.schedule_type}")


# --------------------------------------------------------------------------- #
# Persistence layer
# --------------------------------------------------------------------------- #


class JobStore:
    """SQLite‑backed storage for Job objects."""

    _DB_SCHEMA = """
    CREATE TABLE IF NOT EXISTS jobs (
        job_id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        schedule_type TEXT NOT NULL,
        schedule_value TEXT NOT NULL,
        function_path TEXT NOT NULL,
        args BLOB,
        kwargs BLOB
    );
    """

    def __init__(self, db_path: Union[str, Path]) -> None:
        """
        Initialise the store, creating tables if necessary.

        Args:
            db_path: Path to the SQLite database file.
        """
        self._db_path = Path(db_path).expanduser().resolve()
        self._connection = sqlite3.connect(self._db_path, check_same_thread=False)
        self._connection.execute("PRAGMA journal_mode=WAL;")
        self._connection.executescript(self._DB_SCHEMA)
        self._connection.commit()
        self._lock = threading.Lock()

    def _serialize(self, value: Any) -> bytes:
        """Serialize Python objects to bytes using the built‑in repr (safe for simple types)."""
        return repr(value).encode("utf-8")

    def _deserialize(self, data: Optional[bytes]) -> Any:
        """Deserialize bytes back to Python objects using eval in a restricted namespace."""
        if data is None:
            return None
        try:
            return eval(data.decode("utf-8"), {"__builtins__": {}})
        except Exception as exc:
            raise SchedulerError(f"Failed to deserialize stored data: {exc}") from exc

    def add(self, job: Job) -> JobID:
        """
        Persist a new job and return its generated identifier.

        Args:
            job: Job instance without a job_id (the id will be ignored).

        Returns:
            The generated job_id.
        """
        with self._lock, self._connection:
            cursor = self._connection.execute(
                """
                INSERT INTO jobs (name, schedule_type, schedule_value, function_path, args, kwargs)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    job.name,
                    job.schedule_type,
                    str(job.schedule_value),
                    job.function_path,
                    self._serialize(job.args),
                    self._serialize(job.kwargs),
                ),
            )
            return cursor.lastrowid

    def remove(self, job_id: JobID) -> None:
        """
        Delete a job from storage.

        Args:
            job_id: Identifier of the job to delete.

        Raises:
            JobNotFoundError: If the job does not exist.
        """
        with self._lock, self._connection:
            cursor = self._connection.execute("DELETE FROM jobs WHERE job_id = ?", (job_id,))
            if cursor.rowcount == 0:
                raise JobNotFoundError(f"Job with id {job_id} not found.")

    def list_all(self) -> List[Job]:
        """
        Retrieve all persisted jobs.

        Returns:
            List of Job instances.
        """
        with self._lock, self._connection:
            rows = self._connection.execute(
                """
                SELECT job_id, name, schedule_type, schedule_value,
                       function_path, args, kwargs
                FROM jobs
                """
            ).fetchall()
        jobs: List[Job] = []
        for row in rows:
            job_id, name, schedule_type, schedule_value, function_path, args_blob, kwargs_blob = row
            jobs.append(
                Job(
                    job_id=job_id,
                    name=name,
                    schedule_type=schedule_type,
                    schedule_value=schedule_value,
                    function_path=function_path,
                    args=self._deserialize(args_blob) or (),
                    kwargs=self._deserialize(kwargs_blob) or {},
                )
            )
        return jobs

    def get(self, job_id: JobID) -> Job:
        """
        Retrieve a single job by its identifier.

        Args:
            job_id: Identifier of the job.

        Returns:
            The corresponding Job instance.

        Raises:
            JobNotFoundError: If the job does not exist.
        """
        with self._lock, self._connection:
            row = self._connection.execute(
                """
                SELECT job_id, name, schedule_type, schedule_value,
                       function_path, args, kwargs
                FROM jobs
                WHERE job_id = ?
                """,
                (job_id,),
            ).fetchone()
        if row is None:
            raise JobNotFoundError(f"Job with id {job_id} not found.")
        job_id, name, schedule_type, schedule_value, function_path, args_blob, kwargs_blob = row
        return Job(
            job_id=job_id,
            name=name,
            schedule_type=schedule_type,
            schedule_value=schedule_value,
            function_path=function_path,
            args=self._deserialize(args_blob) or (),
            kwargs=self._deserialize(kwargs_blob) or {},
        )


# --------------------------------------------------------------------------- #
# Scheduler core
# --------------------------------------------------------------------------- #


class Scheduler:
    """
    Core scheduler that runs jobs in a background thread.

    The scheduler must be started with :meth:`start` before it can execute jobs.
    """

    _DEFAULT_LOG_PATH = Path.cwd() / "task_scheduler.log"

    def __init__(self, store: JobStore, log_path: Optional[Path] = None) -> None:
        """
        Initialise the scheduler.

        Args:
            store: Instance of :class:`JobStore` for persistence.
            log_path: Optional path for the execution log file.
        """
        self._store = store
        self._log_path = log_path or self._DEFAULT_LOG_PATH
        self._logger = self._setup_logger(self._log_path)
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._next_run_map: Dict[JobID, datetime] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _setup_logger(log_path: Path) -> logging.Logger:
        logger = logging.getLogger("TaskScheduler")
        logger.setLevel(logging.INFO)
        handler = logging.FileHandler(log_path, encoding="utf-8")
        formatter = logging.Formatter(
            fmt="%(asctime)s %(levelname)s %(name)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
        )
        handler.setFormatter(formatter)
        logger.handlers.clear()
        logger.addHandler(handler)
        return logger

    # ------------------------------------------------------------------- #
    # Public API
    # ------------------------------------------------------------------- #

    def start(self) -> None:
        """
        Start the background thread that polls and runs jobs.

        Raises:
            SchedulerError: If the scheduler is already running.
        """
        if self._thread and self._thread.is_alive():
            raise SchedulerError("Scheduler already running.")
        self._populate_next_run()
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="TaskSchedulerThread")
        self._thread.start()
        self._logger.info("Scheduler started.")

    def stop(self, wait: bool = True) -> None:
        """
        Signal the scheduler to stop and optionally wait for the thread to finish.

        Args:
            wait: If True, block until the background thread exits.
        """
        self._stop_event.set()
        if wait and self._thread:
            self._thread.join()
        self._logger.info("Scheduler stopped.")

    def add_job(
        self,
        name: str,
        schedule_type: ScheduleType,
        schedule_value: Union[str, int],
        function_path: str,
        args: Tuple[Any, ...] = (),
        kwargs: Optional[Dict[str, Any]] = None,
    ) -> JobID:
        """
        Register a new job.

        Args:
            name: Human readable name.
            schedule_type: One of "daily", "hourly", "minute".
            schedule_value: Depends on ``schedule_type``:
                - "daily": "HH:MM" (24‑hour clock)
                - "hourly": minute (0‑59) when the job should fire each hour
                - "minute": interval in minutes (int > 0)
            function_path: Fully‑qualified import path to the callable.
            args: Positional arguments for the callable.
            kwargs: Keyword arguments for the callable.

        Returns:
            The generated job identifier.

        Raises:
            InvalidScheduleError: If ``schedule_value`` is malformed.
            SchedulerError: For import‑related errors.
        """
        kwargs = kwargs or {}
        self._validate_schedule(schedule_type, schedule_value)
        # Validate that the function can be imported
        self._load_callable(function_path)

        job = Job(
            job_id=0,  # placeholder, will be replaced by DB
            name=name,
            schedule_type=schedule_type,
            schedule_value=schedule_value,
            function_path=function_path,
            args=args,
            kwargs=kwargs,
        )
        job_id = self._store.add(job)
        with self._lock:
            job = Job(job_id=job_id, **asdict(job))
            self._next_run_map[job_id] = job.next_run()
        self._logger.info(f"Added job {job_id!r}: {name!r}")
        return job_id

    def remove_job(self, job_id: JobID) -> None:
        """
        Delete a job from the scheduler.

        Args:
            job_id: Identifier of the job to delete.

        Raises:
            JobNotFoundError: If the job does not exist.
        """
        self._store.remove(job_id)
        with self._lock:
            self._next_run_map.pop(job_id, None)
        self._logger.info(f"Removed job {job_id!r}")

    def list_jobs(self) -> List[Job]:
        """
        Return a list of all registered jobs.

        Returns:
            List of :class:`Job` objects.
        """
        return self._store.list_all()

    # ------------------------------------------------------------------- #
    # Internal helpers
    # ------------------------------------------------------------------- #

    def _populate_next_run(self) -> None:
        """Populate the internal map of next run times for all persisted jobs."""
        with self._lock:
            self._next_run_map = {job.job_id: job.next_run() for job in self._store.list_all()}

    @staticmethod
    def _validate_schedule(schedule_type: ScheduleType, schedule_value: Union[str, int]) -> None:
        """Validate schedule definitions; raise :class:`InvalidScheduleError` on failure."""
        if schedule_type == "daily":
            if not isinstance(schedule_value, str) or len(schedule_value.split(":")) != 2:
                raise InvalidScheduleError("Daily schedule must be a string 'HH:MM'.")
            hour, minute = schedule_value.split(":")
            if not (hour.isdigit() and minute.isdigit()):
                raise InvalidScheduleError("Hour and minute must be numeric.")
            h, m = int(hour), int(minute)
            if not (0 <= h < 24 and 0 <= m < 60):
                raise InvalidScheduleError("Hour must be 0‑23 and minute 0‑59.")
        elif schedule_type == "hourly":
            if not isinstance(schedule_value, int) or not (0 <= schedule_value < 60):
                raise InvalidScheduleError("Hourly schedule minute must be an integer 0‑59.")
        elif schedule_type == "minute":
            if not isinstance(schedule_value, int) or schedule_value <= 0:
                raise InvalidScheduleError("Minute interval must be a positive integer.")
        else:
            raise InvalidScheduleError(f"Unsupported schedule type: {schedule_type}")

    @staticmethod
    def _load_callable(function_path: str) -> Callable:
        """
        Import and return a callable given its dotted path.

        Args:
            function_path: e.g. "pkg.module.func"

        Returns:
            Callable object.

        Raises:
            SchedulerError: If import fails or the attribute is not callable.
        """
        try:
            module_path, attr_name = function_path.rsplit(".", 1)
            module = importlib.import_module(module_path)
            func = getattr(module, attr_name)
            if not callable(func):
                raise SchedulerError(f"Attribute {function_path} is not callable.")
            return func
        except (ImportError, ValueError, AttributeError) as exc:
            raise SchedulerError(f"Failed to import callable '{function_path}': {exc}") from exc

    def _run_loop(self) -> None:
        """Continuously check for due jobs and execute them."""
        while not self._stop_event.is_set():
            now = datetime.utcnow()
            due_jobs: List[Tuple[Job, datetime]] = []
            with self._lock:
                for job_id, next_run in list(self._next_run_map.items()):
                    if next_run <= now:
                        try:
                            job = self._store.get(job_id)
                        except JobNotFoundError:
                            # Job was removed externally; clean up.
                            self._next_run_map.pop(job_id, None)
                            continue
                        due_jobs.append((job, next_run))
            for job, scheduled_time in due_jobs:
                self._execute_job(job, scheduled_time)
                # Schedule next run
                with self._lock:
                    self._next_run_map[job.job_id] = job.next_run(after=scheduled_time)
            # Sleep a short interval to avoid busy‑waiting.
            time.sleep(30)

    def _execute_job(self, job: Job, scheduled_time: datetime) -> None:
        """
        Execute the job's callable and log the outcome.

        Args:
            job: Job to run.
            scheduled_time: The time the job was scheduled for.
        """
        func = self._load_callable(job.function_path)
        self._logger.info(
            f"Executing job {job.job_id!r} ({job.name!r}) scheduled at {scheduled_time.isoformat()}."
        )
        try:
            func(*job.args, **job.kwargs)
        except Exception as exc:
            self._logger.exception(
                f"Job {job.job_id!r} ({job.name!r}) raised an exception: {exc}"
            )
        else:
            self._logger.info(f"Job {job.job_id!r} ({job.name!r}) completed successfully.")