"""
Task Scheduler Module

A thread-safe task scheduler supporting recurring jobs with daily, hourly, and minute frequencies.
Features persistent storage via SQLite, execution logging, and comprehensive error handling.

Example:
    scheduler = TaskScheduler("tasks.db")
    scheduler.add_task("backup", "daily", "02:00", lambda: backup_database())
    scheduler.start()
"""

import logging
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

# Configure module logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)


class Frequency(Enum):
    """Supported scheduling frequencies."""
    MINUTE = "minute"
    HOURLY = "hourly"
    DAILY = "daily"


class TaskStatus(Enum):
    """Task execution status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Task:
    """Represents a scheduled task with metadata."""

    def __init__(
        self,
        task_id: str,
        name: str,
        frequency: Frequency,
        schedule_time: str,
        func: Callable[[], Any],
        args: Tuple[Any, ...] = (),
        kwargs: Optional[Dict[str, Any]] = None,
        enabled: bool = True,
        created_at: Optional[datetime] = None,
        last_run: Optional[datetime] = None,
        next_run: Optional[datetime] = None,
    ) -> None:
        """
        Initialize a Task.

        Args:
            task_id: Unique identifier for the task.
            name: Human-readable task name.
            frequency: Execution frequency (minute, hourly, daily).
            schedule_time: Time specification (e.g., "02:00" for daily, "30" for minute/hourly).
            func: Callable to execute.
            args: Positional arguments for func.
            kwargs: Keyword arguments for func.
            enabled: Whether the task is active.
            created_at: Task creation timestamp.
            last_run: Last execution timestamp.
            next_run: Next scheduled execution timestamp.
        """
        self.task_id = task_id
        self.name = name
        self.frequency = frequency
        self.schedule_time = schedule_time
        self.func = func
        self.args = args
        self.kwargs = kwargs or {}
        self.enabled = enabled
        self.created_at = created_at or datetime.now()
        self.last_run = last_run
        self.next_run = next_run

    def __repr__(self) -> str:
        return (
            f"Task(id={self.task_id}, name={self.name}, "
            f"freq={self.frequency.value}, time={self.schedule_time}, "
            f"enabled={self.enabled})"
        )


class TaskScheduler:
    """
    Thread-safe task scheduler with persistence and logging.

    Attributes:
        db_path: Path to SQLite database file.
        _running: Internal flag indicating scheduler state.
        _scheduler_thread: Background thread for task execution.
        _lock: Thread lock for synchronization.
    """

    def __init__(self, db_path: str = "tasks.db") -> None:
        """
        Initialize the TaskScheduler.

        Args:
            db_path: Path to SQLite database for task persistence.

        Raises:
            ValueError: If db_path is empty or invalid.
            sqlite3.Error: If database initialization fails.
        """
        if not db_path or not isinstance(db_path, str):
            raise ValueError("db_path must be a non-empty string")

        self.db_path = db_path
        self._running = False
        self._scheduler_thread: Optional[threading.Thread] = None
        self._lock = threading.RLock()
        self._tasks: Dict[str, Task] = {}

        self._init_database()
        self._load_tasks()

    def _init_database(self) -> None:
        """
        Initialize the SQLite database schema.

        Creates tables for tasks and execution logs if they don't exist.

        Raises:
            sqlite3.Error: If database operations fail.
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS tasks (
                        task_id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        frequency TEXT NOT NULL,
                        schedule_time TEXT NOT NULL,
                        func_module TEXT NOT NULL,
                        func_name TEXT NOT NULL,
                        args TEXT,
                        kwargs TEXT,
                        enabled INTEGER NOT NULL DEFAULT 1,
                        created_at TEXT NOT NULL,
                        last_run TEXT,
                        next_run TEXT
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS execution_logs (
                        log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        task_id TEXT NOT NULL,
                        status TEXT NOT NULL,
                        started_at TEXT NOT NULL,
                        completed_at TEXT,
                        error_message TEXT,
                        FOREIGN KEY (task_id) REFERENCES tasks (task_id)
                    )
                    """
                )
                conn.commit()
                logger.info("Database initialized at %s", self.db_path)
        except sqlite3.Error as e:
            logger.error("Failed to initialize database: %s", e)
            raise

    def _load_tasks(self) -> None:
        """
        Load tasks from database into memory.

        Raises:
            sqlite3.Error: If database query fails.
            ImportError: If task function cannot be imported.
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute("SELECT * FROM tasks WHERE enabled = 1")
                rows = cursor.fetchall()

            for row in rows:
                try:
                    func = self._import_function(row["func_module"], row["func_name"])
                    task = Task(
                        task_id=row["task_id"],
                        name=row["name"],
                        frequency=Frequency(row["frequency"]),
                        schedule_time=row["schedule_time"],
                        func=func,
                        args=eval(row["args"]) if row["args"] else (),
                        kwargs=eval(row["kwargs"]) if row["kwargs"] else {},
                        enabled=bool(row["enabled"]),
                        created_at=datetime.fromisoformat(row["created_at"]),
                        last_run=(
                            datetime.fromisoformat(row["last_run"])
                            if row["last_run"]
                            else None
                        ),
                        next_run=(
                            datetime.fromisoformat(row["next_run"])
                            if row["next_run"]
                            else None
                        ),
                    )
                    self._tasks[task.task_id] = task
                    logger.debug("Loaded task: %s", task)
                except (ImportError, AttributeError, SyntaxError) as e:
                    logger.error(
                        "Failed to load task %s: %s", row["task_id"], e
                    )
                    continue

            logger.info("Loaded %d tasks from database", len(self._tasks))
        except sqlite3.Error as e:
            logger.error("Failed to load tasks: %s", e)
            raise

    @staticmethod
    def _import_function(module_name: str, func_name: str) -> Callable[[], Any]:
        """
        Import a function by module and name.

        Args:
            module_name: Module containing the function.
            func_name: Name of the function.

        Returns:
            The imported callable.

        Raises:
            ImportError: If module or function not found.
        """
        try:
            module = __import__(module_name, fromlist=[func_name])
            return getattr(module, func_name)
        except (ImportError, AttributeError) as e:
            raise ImportError(
                f"Cannot import {func_name} from {module_name}"
            ) from e

    def _persist_task(self, task: Task) -> None:
        """
        Persist a single task to database.

        Args:
            task: Task to persist.

        Raises:
            sqlite3.Error: If database operation fails.
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO tasks
                    (task_id, name, frequency, schedule_time, func_module,
                     func_name, args, kwargs, enabled, created_at, last_run, next_run)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        task.task_id,
                        task.name,
                        task.frequency.value,
                        task.schedule_time,
                        task.func.__module__,
                        task.func.__name__,
                        repr(task.args),
                        repr(task.kwargs),
                        int(task.enabled),
                        task.created_at.isoformat(),
                        task.last_run.isoformat() if task.last_run else None,
                        task.next_run.isoformat() if task.next_run else None,
                    ),
                )
                conn.commit()
        except sqlite3.Error as e:
            logger.error("Failed to persist task %s: %s", task.task_id, e)
            raise

    def _remove_task_from_db(self, task_id: str) -> None:
        """
        Remove a task from database.

        Args:
            task_id: ID of task to remove.

        Raises:
            sqlite3.Error: If database operation fails.
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("DELETE FROM tasks WHERE task_id = ?", (task_id,))
                conn.commit()
        except sqlite3.Error as e:
            logger.error("Failed to remove task %s from database: %s", task_id, e)
            raise

    def _calculate_next_run(
        self, frequency: Frequency, schedule_time: str, from_time: datetime
    ) -> datetime:
        """
        Calculate next execution time based on frequency and schedule.

        Args:
            frequency: Task frequency.
            schedule_time: Time specification string.
            from_time: Reference time for calculation.

        Returns:
            Next execution datetime.

        Raises:
            ValueError: If schedule_time format is invalid.
        """
        try:
            if frequency == Frequency.MINUTE:
                minute = int(schedule_time)
                if not 0 <= minute <= 59:
                    raise ValueError("Minute must be 0-59")
                next_run = from_time.replace(second=0, microsecond=0)
                next_run += timedelta(minutes=1)
                next_run = next_run.replace(minute=minute)
                if next_run <= from_time:
                    next_run += timedelta(hours=1)
                return next_run

            elif frequency == Frequency.HOURLY:
                parts = schedule_time.split(":")
                if len(parts) != 2:
                    raise ValueError("Hourly format must be 'MM:SS'")
                minute, second = map(int, parts)
                if not 0 <= minute <= 59 or not 0 <= second <= 59:
                    raise ValueError("Invalid minute/second")
                next_run = from_time.replace(minute=minute, second=second, microsecond=0)
                if next_run <= from_time:
                    next_run += timedelta(hours=1)
                return next_run

            elif frequency == Frequency.DAILY:
                parts = schedule_time.split(":")
                if len(parts) not in (2, 3):
                    raise ValueError("Daily format must be 'HH:MM' or 'HH:MM:SS'")
                hour, minute = map(int, parts[:2])
                second = int(parts[2]) if len(parts) == 3 else 0
                if not 0 <= hour <= 23 or not 0 <= minute <= 59 or not 0 <= second <= 59:
                    raise ValueError("Invalid time components")
                next_run = from_time.replace(
                    hour=hour, minute=minute, second=second, microsecond=0
                )
                if next_run <= from_time:
                    next_run += timedelta(days=1)
                return next_run

        except ValueError as e:
            raise ValueError(f"Invalid schedule_time '{schedule_time}': {e}") from e

        raise ValueError(f"Unknown frequency: {frequency}")

    def _log_execution(
        self,
        task_id: str,
        status: TaskStatus,
        started_at: datetime,
        completed_at: Optional[datetime] = None,
        error_message: Optional[str] = None,
    ) -> None:
        """
        Log task execution to database.

        Args:
            task_id: Task identifier.
            status: Execution status.
            started_at: Execution start time.
            completed_at: Execution completion time.
            error_message: Error message if failed.

        Raises:
            sqlite3.Error: If database operation fails.
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO execution_logs
                    (task_id, status, started_at, completed_at, error_message)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        task_id,
                        status.value,
                        started_at.isoformat(),
                        completed_at.isoformat() if completed_at else None,
                        error_message,
                    ),
                )
                conn.commit()
        except sqlite3.Error as e:
            logger.error("Failed to log execution for task %s: %s", task_id, e)

    def _execute_task(self, task: Task) -> None:
        """
        Execute a task and handle logging.

        Args:
            task: Task to execute.
        """
        started_at = datetime.now()
        self._log_execution(task.task_id, TaskStatus.RUNNING, started_at)

        try:
            logger.info("Executing task: %s", task.name)
            task.func(*task.args, **task.kwargs)
            completed_at = datetime.now()
            self._log_execution(
                task.task_id, TaskStatus.COMPLETED, started_at, completed_at
            )
            logger.info("Task completed: %s (duration: %.2fs)",
                        task.name, (completed_at - started_at).total_seconds())
        except Exception as e:
            completed_at = datetime.now()
            error_msg = f"{type(e).__name__}: {e}"
            self._log_execution(
                task.task_id, TaskStatus.FAILED, started_at, completed_at, error_msg
            )
            logger.error("Task failed: %s - %s", task.name, error_msg)

    def _run_scheduler(self) -> None:
        """
        Main scheduler loop running in background thread.

        Checks tasks every second and executes due tasks.
        """
        logger.info("Scheduler started")
        while self._running:
            try:
                now = datetime.now()
                with self._lock:
                    tasks_to_run = [
                        task for task in self._tasks.values()
                        if task.enabled and task.next_run and task.next_run <= now
                    ]

                for task in tasks_to_run:
                    self._execute_task(task)
                    with self._lock:
                        task.last_run = datetime.now()
                        task.next_run = self._calculate_next_run(
                            task.frequency, task.schedule_time, task.last_run
                        )
                        self._persist_task(task)

            except Exception as e:
                logger.error("Scheduler error: %s", e)

            time.sleep(1)

        logger.info("Scheduler stopped")

    def add_task(
        self,
        name: str,
        frequency: Union[Frequency, str],
        schedule_time: str,
        func: Callable[[], Any],
        args: Tuple[Any, ...] = (),
        kwargs: Optional[Dict[str, Any]] = None,
        enabled: bool = True,
    ) -> str:
        """
        Add a new scheduled task.

        Args:
            name: Human-readable task name.
            frequency: Execution frequency (Frequency enum or string).
            schedule_time: Time specification (format depends on frequency).
            func: Callable to execute.
            args: Positional arguments for func.
            kwargs: Keyword arguments for func.
            enabled: Whether task starts enabled.

        Returns:
            Task ID of the created task.

        Raises:
            ValueError: If parameters are invalid.
            TypeError: If func is not callable.
        """
        if not name or not isinstance(name, str):
            raise ValueError("name must be a non-empty string")
        if not callable(func):
            raise TypeError("func must be callable")

        if isinstance(frequency, str):
            try:
                frequency = Frequency(frequency.lower())
            except ValueError:
                raise ValueError(f"Invalid frequency: {frequency}")

        # Validate schedule_time format by calculating next run
        self._calculate_next_run(frequency, schedule_time, datetime.now())

        task_id = str(uuid.uuid4())
        next_run = self._calculate_next_run(frequency, schedule_time, datetime.now())

        task = Task(
            task_id=task_id,
            name=name,
            frequency=frequency,
            schedule_time=schedule_time,
            func=func,
            args=args,
            kwargs=kwargs or {},
            enabled=enabled,
            next_run=next_run,
        )

        with self._lock:
            self._tasks[task_id] = task
            self._persist_task(task)

        logger.info("Added task: %s", task)
        return