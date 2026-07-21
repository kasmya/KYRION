"""
Task Scheduler Module

A thread-safe task scheduler supporting recurring jobs with daily, hourly, and minute frequencies.
Provides persistence via SQLite, structured logging, and secure job management.

Features:
- Add/remove scheduled jobs with unique IDs
- Persistent storage using SQLite with WAL mode
- Structured execution logging with rotation
- Support for daily, hourly, and minute frequencies
- Thread-safe operations with proper locking
- Input validation and sanitization
- Graceful shutdown handling

Example:
    scheduler = TaskScheduler("tasks.db", "scheduler.log")
    scheduler.start()
    job_id = scheduler.add_job("backup", "daily", "02:00", backup_function)
    scheduler.remove_job(job_id)
    scheduler.stop()
"""

import sqlite3
import threading
import logging
import logging.handlers
import json
import uuid
import time
import atexit
import signal
import sys
from datetime import datetime, time as dt_time, timedelta
from dataclasses import dataclass, asdict
from enum import Enum
from typing import Callable, Optional, Dict, List, Any, Union
from pathlib import Path
from contextlib import contextmanager
import functools


class Frequency(Enum):
    """Supported job frequencies."""
    MINUTE = "minute"
    HOURLY = "hourly"
    DAILY = "daily"


@dataclass(frozen=True)
class Job:
    """Represents a scheduled job."""
    id: str
    name: str
    frequency: Frequency
    schedule_time: str  # Format: "HH:MM" for daily/hourly, "MM" for minute
    function_name: str
    function_module: str
    args: tuple
    kwargs: dict
    enabled: bool = True
    created_at: str = ""
    last_run: Optional[str] = None
    next_run: Optional[str] = None
    run_count: int = 0

    def __post_init__(self) -> None:
        if not self.created_at:
            object.__setattr__(self, 'created_at', datetime.utcnow().isoformat())


class SchedulerError(Exception):
    """Base exception for scheduler errors."""
    pass


class JobNotFoundError(SchedulerError):
    """Raised when a job is not found."""
    pass


class InvalidScheduleError(SchedulerError):
    """Raised when schedule parameters are invalid."""
    pass


class PersistenceError(SchedulerError):
    """Raised when persistence operations fail."""
    pass


class TaskScheduler:
    """
    Thread-safe task scheduler with persistence and logging.

    Args:
        db_path: Path to SQLite database file.
        log_path: Path to log file.
        max_log_size: Maximum log file size in bytes (default: 10MB).
        backup_count: Number of log backups to keep (default: 5).
    """

    def __init__(
        self,
        db_path: Union[str, Path],
        log_path: Union[str, Path],
        max_log_size: int = 10 * 1024 * 1024,
        backup_count: int = 5
    ) -> None:
        self._db_path = Path(db_path).resolve()
        self._log_path = Path(log_path).resolve()
        self._max_log_size = max_log_size
        self._backup_count = backup_count

        self._lock = threading.RLock()
        self._running = False
        self._scheduler_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._jobs: Dict[str, Job] = {}
        self._function_registry: Dict[str, Callable[..., Any]] = {}

        self._init_database()
        self._init_logging()
        self._load_jobs()
        atexit.register(self.stop)
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

    def _signal_handler(self, signum: int, frame: Any) -> None:
        """Handle shutdown signals gracefully."""
        self.stop()
        sys.exit(0)

    def _init_database(self) -> None:
        """Initialize SQLite database with WAL mode and required tables."""
        try:
            with self._db_connection() as conn:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA busy_timeout=5000")
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS jobs (
                        id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        frequency TEXT NOT NULL,
                        schedule_time TEXT NOT NULL,
                        function_name TEXT NOT NULL,
                        function_module TEXT NOT NULL,
                        args TEXT NOT NULL,
                        kwargs TEXT NOT NULL,
                        enabled INTEGER NOT NULL DEFAULT 1,
                        created_at TEXT NOT NULL,
                        last_run TEXT,
                        next_run TEXT,
                        run_count INTEGER NOT NULL DEFAULT 0
                    )
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_jobs_next_run
                    ON jobs(next_run) WHERE enabled = 1
                """)
                conn.commit()
        except sqlite3.Error as e:
            raise PersistenceError(f"Database initialization failed: {e}") from e

    def _init_logging(self) -> None:
        """Configure rotating file logger with structured format."""
        self._logger = logging.getLogger(f"scheduler.{self._db_path.stem}")
        self._logger.setLevel(logging.INFO)
        self._logger.propagate = False

        if not self._logger.handlers:
            handler = logging.handlers.RotatingFileHandler(
                self._log_path,
                maxBytes=self._max_log_size,
                backupCount=self._backup_count,
                encoding='utf-8'
            )
            formatter = logging.Formatter(
                '{"timestamp": "%(asctime)s", "level": "%(levelname)s", '
                '"job_id": "%(job_id)s", "job_name": "%(job_name)s", '
                '"message": "%(message)s", "duration_ms": %(duration_ms)d}',
                datefmt='%Y-%m-%dT%H:%M:%S'
            )
            handler.setFormatter(formatter)
            self._logger.addHandler(handler)

    @contextmanager
    def _db_connection(self) -> Any:
        """Context manager for database connections."""
        conn = sqlite3.connect(self._db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _load_jobs(self) -> None:
        """Load enabled jobs from database into memory."""
        with self._lock:
            try:
                with self._db_connection() as conn:
                    cursor = conn.execute(
                        "SELECT * FROM jobs WHERE enabled = 1"
                    )
                    for row in cursor:
                        job = self._row_to_job(row)
                        self._jobs[job.id] = job
                        self._compute_next_run(job)
            except sqlite3.Error as e:
                raise PersistenceError(f"Failed to load jobs: {e}") from e

    def _row_to_job(self, row: sqlite3.Row) -> Job:
        """Convert database row to Job object."""
        return Job(
            id=row['id'],
            name=row['name'],
            frequency=Frequency(row['frequency']),
            schedule_time=row['schedule_time'],
            function_name=row['function_name'],
            function_module=row['function_module'],
            args=json.loads(row['args']),
            kwargs=json.loads(row['kwargs']),
            enabled=bool(row['enabled']),
            created_at=row['created_at'],
            last_run=row['last_run'],
            next_run=row['next_run'],
            run_count=row['run_count']
        )

    def _job_to_row(self, job: Job) -> tuple:
        """Convert Job object to database row tuple."""
        return (
            job.id, job.name, job.frequency.value, job.schedule_time,
            job.function_name, job.function_module,
            json.dumps(job.args), json.dumps(job.kwargs),
            int(job.enabled), job.created_at,
            job.last_run, job.next_run, job.run_count
        )

    def _compute_next_run(self, job: Job) -> None:
        """Calculate and set the next run time for a job."""
        now = datetime.utcnow()
        schedule = job.schedule_time

        if job.frequency == Frequency.MINUTE:
            minute = int(schedule)
            next_run = now.replace(second=0, microsecond=0)
            if next_run.minute >= minute:
                next_run += timedelta(hours=1)
            next_run = next_run.replace(minute=minute)

        elif job.frequency == Frequency.HOURLY:
            hour, minute = map(int, schedule.split(':'))
            next_run = now.replace(minute=minute, second=0, microsecond=0)
            if next_run.hour >= hour:
                next_run += timedelta(days=1)
            next_run = next_run.replace(hour=hour)

        elif job.frequency == Frequency.DAILY:
            hour, minute = map(int, schedule.split(':'))
            next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if next_run <= now:
                next_run += timedelta(days=1)

        else:
            raise InvalidScheduleError(f"Unknown frequency: {job.frequency}")

        object.__setattr__(job, 'next_run', next_run.isoformat())

    def _validate_schedule(self, frequency: Frequency, schedule_time: str) -> None:
        """Validate schedule time format for given frequency."""
        try:
            if frequency == Frequency.MINUTE:
                minute = int(schedule_time)
                if not 0 <= minute <= 59:
                    raise ValueError
            elif frequency in (Frequency.HOURLY, Frequency.DAILY):
                hour, minute = map(int, schedule_time.split(':'))
                if not (0 <= hour <= 23 and 0 <= minute <= 59):
                    raise ValueError
            else:
                raise InvalidScheduleError(f"Unsupported frequency: {frequency}")
        except (ValueError, AttributeError) as e:
            raise InvalidScheduleError(
                f"Invalid schedule_time '{schedule_time}' for {frequency.value}: {e}"
            ) from e

    def _sanitize_name(self, name: str) -> str:
        """Sanitize job name to prevent injection."""
        sanitized = "".join(c for c in name if c.isalnum() or c in "-_ ")
        return sanitized.strip()[:100] or "unnamed_job"

    def register_function(self, func: Callable[..., Any], name: Optional[str] = None) -> str:
        """
        Register a function for use in scheduled jobs.

        Args:
            func: Callable to register.
            name: Optional custom name (defaults to function's qualified name).

        Returns:
            Registered function key.

        Raises:
            ValueError: If func is not callable.
        """
        if not callable(func):
            raise ValueError("Function must be callable")

        key = name or f"{func.__module__}.{func.__qualname__}"
        with self._lock:
            self._function_registry[key] = func
        return key

    def add_job(
        self,
        name: str,
        frequency: Union[Frequency, str],
        schedule_time: str,
        func: Union[Callable[..., Any], str],
        *args: Any,
        **kwargs: Any
    ) -> str:
        """
        Add a new scheduled job.

        Args:
            name: Human-readable job name.
            frequency: Frequency enum or string (minute/hourly/daily).
            schedule_time: Schedule specification:
                - minute: "MM" (0-59)
                - hourly: "HH:MM"
                - daily: "HH:MM"
            func: Registered function key or callable.
            *args: Positional arguments for the function.
            **kwargs: Keyword arguments for the function.

        Returns:
            Unique job ID.

        Raises:
            InvalidScheduleError: If schedule parameters are invalid.
            ValueError: If function is not registered or not callable.
        """
        if isinstance(frequency, str):
            try:
                frequency = Frequency(frequency.lower())
            except ValueError:
                raise InvalidScheduleError(f"Invalid frequency: {frequency}")

        self._validate_schedule(frequency, schedule_time)
        safe_name = self._sanitize_name(name)

        if isinstance(func, str):
            func_key = func
            if func_key not in self._function_registry:
                raise ValueError(f"Function not registered: {func_key}")
            func_obj = self._function_registry[func_key]
        elif callable(func):
            func_key = self.register_function(func)
            func_obj = func
        else:
            raise ValueError("func must be a registered function key or callable")

        job_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()

        job = Job(
            id=job_id,
            name=safe_name,
            frequency=frequency,
            schedule_time=schedule_time,
            function_name=func_obj.__name__,
            function_module=func_obj.__module__,
            args=args,
            kwargs=kwargs,
            created_at=now
        )
        self._compute_next_run(job)

        with self._lock:
            try:
                with self._db_connection() as conn:
                    conn.execute(
                        """INSERT INTO jobs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        self._job_to_row(job)
                    )
                    conn.commit()
                self._jobs[job_id] = job
            except sqlite3.Error as e:
                raise PersistenceError(f"Failed to add job: {e}") from e

        self._log_job_event(job_id, safe_name, "JOB_ADDED", f"Next run: {job.next_run}")
        return job_id

    def remove_job(self, job_id: str) -> None:
        """
        Remove a scheduled job.

        Args:
            job_id: ID of the job to remove.

        Raises:
            JobNotFoundError: If job_id does not exist.
        """
        with self._lock:
            if job_id not in self._jobs:
                raise JobNotFoundError(f"Job not found: {job_id}")

            job = self._jobs[job_id]
            try:
                with self._db_connection() as conn:
                    conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
                    conn.commit()
                del self._jobs[job_id]
            except sqlite3.Error as e:
                raise PersistenceError(f"Failed to remove job: {e}") from e

        self._log_job_event(job_id, job.name, "JOB_REMOVED", "Job removed")

    def enable_job(self, job_id: str) -> None:
        """
        Enable a disabled job.

        Args:
            job_id: ID of the job to enable.

        Raises:
            JobNotFoundError: If job_id does not exist.
        """
        self._set_job_enabled(job_id, True)

    def disable_job(self, job_id: str) -> None:
        """
        Disable a job without removing it.

        Args:
            job_id: ID of the job to disable.

        Raises:
            JobNotFoundError: If job_id does not exist.
        """
        self._set_job_enabled(job_id, False)

    def _set_job_enabled(self, job_id: str, enabled: bool) -> None:
        with self._lock:
            if job_id not in self._jobs:
                raise JobNotFoundError(f"Job not found: {job_id}")

            job = self._jobs[job_id]
            if job.enabled == enabled:
                return

            new_job = Job(
                **{**asdict(job), 'enabled': enabled}
            )
            if enabled:
                self._compute_next_run(new_job)
            else:
                object.__setattr__(new_job, 'next_run', None)

            try:
                with self._db_connection() as conn:
                    conn.execute(
                        "UPDATE jobs SET enabled = ?, next_run = ? WHERE id = ?",
                        (int(enabled), new_job.next_run, job_id)
                    )
                    conn.commit()
                self._jobs[job_id] = new_job
            except sqlite3.Error as e:
                raise PersistenceError(f"Failed to update job: {e}") from e

    def get_job(self, job_id: str) -> Job:
        """
        Get job details by ID.

        Args:
            job_id: Job ID to retrieve.

        Returns:
            Job object.

        Raises:
            JobNotFoundError: If job_id does not exist.
        """
        with self._lock:
            if job_id not in self._jobs:
                raise JobNotFoundError(f"Job not found: {job_id}")
            return self._jobs[job_id]

    def list_jobs(self, enabled_only: bool = False) -> List[Job]:
        """
        List all jobs.

        Args:
            enabled_only: If True, return only enabled jobs.

        Returns:
            List of Job objects.
        """
        with self._lock:
            jobs = list(self._jobs.values())
            if enabled_only:
                jobs = [j for j in jobs if j.enabled]
            return sorted(jobs, key=lambda j: j.next_run or "")

    def run_job_now(self, job_id: str) -> Any:
        """
        Execute a job immediately outside its schedule.

        Args:
            job_id: ID of the job to run.

        Returns:
            Function return value.

        Raises:
            JobNotFoundError: If job_id does not exist.
        """
        with self._lock:
            if job_id not in self._jobs:
                raise JobNotFoundError(f"Job not found: {job_id}")
            job =