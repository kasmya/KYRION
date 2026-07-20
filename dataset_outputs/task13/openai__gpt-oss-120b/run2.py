"""
task_scheduler.py

A lightweight task scheduler built on APScheduler that supports:
- Adding, removing, and listing scheduled tasks
- Persistent storage of tasks in a JSON file
- Execution logging with rotating file handler
- Scheduling frequencies: daily, hourly, or minute-level
- Type hints, docstrings, and robust error handling

Only standard library modules and APScheduler are used.
"""

from __future__ import annotations

import importlib
import json
import logging
import os
import sys
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Literal, Optional, TypedDict

from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR, JobExecutionEvent
from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.job import Job
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

# --------------------------------------------------------------------------- #
# Configuration constants
# --------------------------------------------------------------------------- #

DEFAULT_STORAGE_PATH = Path(__file__).with_name("tasks.json")
LOG_FILE = Path(__file__).with_name("scheduler.log")
MAX_LOG_SIZE = 10 * 1024 * 1024  # 10 MB
BACKUP_COUNT = 5

# --------------------------------------------------------------------------- #
# Logging configuration
# --------------------------------------------------------------------------- #

logger = logging.getLogger("TaskScheduler")
logger.setLevel(logging.INFO)
handler = logging.handlers.RotatingFileHandler(
    LOG_FILE, maxBytes=MAX_LOG_SIZE, backupCount=BACKUP_COUNT, encoding="utf-8"
)
formatter = logging.Formatter(
    "%(asctime)s | %(levelname)s | %(threadName)s | %(name)s | %(message)s"
)
handler.setFormatter(formatter)
logger.addHandler(handler)

# --------------------------------------------------------------------------- #
# Types and data structures
# --------------------------------------------------------------------------- #

ScheduleFreq = Literal["daily", "hourly", "minutely"]


class TaskConfig(TypedDict, total=False):
    """Optional configuration for a scheduled task."""
    hour: int  # 0-23, used for daily/hourly triggers
    minute: int  # 0-59, used for all triggers


@dataclass
class Task:
    """Represent a scheduled task."""

    task_id: str
    func_path: str  # e.g. "my_pkg.module.func"
    args: List[Any] = field(default_factory=list)
    kwargs: Dict[str, Any] = field(default_factory=dict)
    frequency: ScheduleFreq = "minutely"
    config: TaskConfig = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the task to a dict for JSON storage."""
        return asdict(self)

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "Task":
        """Create a Task instance from a dict."""
        return Task(**data)


class SchedulerError(Exception):
    """Base exception class for scheduler errors."""


class TaskNotFoundError(SchedulerError):
    """Raised when a task cannot be found."""


class InvalidFunctionError(SchedulerError):
    """Raised when the supplied function path cannot be imported."""


# --------------------------------------------------------------------------- #
# Helper functions
# --------------------------------------------------------------------------- #


def import_callable(path: str) -> Callable[..., Any]:
    """
    Safely import a callable from a dotted path.

    Parameters
    ----------
    path: str
        Fully-qualified dotted path to a callable (e.g., "pkg.mod.func").

    Returns
    -------
    Callable
        The imported callable.

    Raises
    ------
    InvalidFunctionError
        If the import fails or the attribute is not callable.
    """
    try:
        module_path, _, attr = path.rpartition(".")
        if not module_path:
            raise InvalidFunctionError(f"'{path}' does not contain a module component.")
        module = importlib.import_module(module_path)
        func = getattr(module, attr)
        if not callable(func):
            raise InvalidFunctionError(f"'{path}' is not a callable.")
        return func
    except (ImportError, AttributeError) as exc:
        raise InvalidFunctionError(f"Cannot import '{path}': {exc}") from exc


def build_trigger(task: Task) -> CronTrigger:
    """
    Build an APScheduler CronTrigger based on the task's frequency and config.

    Parameters
    ----------
    task: Task

    Returns
    -------
    CronTrigger
    """
    if task.frequency == "daily":
        hour = task.config.get("hour", 0)
        minute = task.config.get("minute", 0)
        return CronTrigger(hour=hour, minute=minute)
    if task.frequency == "hourly":
        minute = task.config.get("minute", 0)
        return CronTrigger(minute=minute)
    # minutely (default)
    return CronTrigger(second=0)


# --------------------------------------------------------------------------- #
# Main scheduler class
# --------------------------------------------------------------------------- #


class TaskScheduler:
    """
    Task scheduler that persists tasks, provides CRUD operations, and logs execution.
    """

    def __init__(self, storage_path: Path = DEFAULT_STORAGE_PATH):
        """
        Initialize the scheduler.

        Parameters
        ----------
        storage_path: Path
            Path to the JSON file used for persisting tasks.
        """
        self._storage_path = storage_path
        self._scheduler = BackgroundScheduler(
            executors={"default": ThreadPoolExecutor(max_workers=10)},
            job_defaults={"coalesce": False, "max_instances": 3},
        )
        self._tasks: Dict[str, Task] = {}
        self._lock = threading.RLock()
        self._load_tasks()
        self._scheduler.add_listener(self._job_listener, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)
        self._scheduler.start()
        logger.info("TaskScheduler initialized and background scheduler started.")

    # ----------------------------------------------------------------------- #
    # Persistence
    # ----------------------------------------------------------------------- #

    def _load_tasks(self) -> None:
        """Load tasks from the JSON storage file."""
        if not self._storage_path.exists():
            logger.info("No existing task storage found; starting fresh.")
            return
        try:
            with self._storage_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            for task_data in data:
                task = Task.from_dict(task_data)
                self._tasks[task.task_id] = task
                self._schedule_task(task)
            logger.info("Loaded %d tasks from storage.", len(self._tasks))
        except (json.JSONDecodeError, OSError) as exc:
            logger.error("Failed to load tasks from storage: %s", exc)
            raise SchedulerError("Could not load tasks.") from exc

    def _save_tasks(self) -> None:
        """Persist current tasks to the JSON storage file."""
        try:
            with self._storage_path.open("w", encoding="utf-8") as f:
                json.dump([t.to_dict() for t in self._tasks.values()], f, indent=2)
            logger.info("Persisted %d tasks to storage.", len(self._tasks))
        except OSError as exc:
            logger.error("Failed to persist tasks: %s", exc)
            raise SchedulerError("Could not persist tasks.") from exc

    # ----------------------------------------------------------------------- #
    # Job handling
    # ----------------------------------------------------------------------- #

    def _schedule_task(self, task: Task) -> None:
        """Schedule a task with APScheduler."""
        try:
            func = import_callable(task.func_path)
            trigger = build_trigger(task)
            self._scheduler.add_job(
                func,
                trigger,
                args=task.args,
                kwargs=task.kwargs,
                id=task.task_id,
                replace_existing=True,
                misfire_grace_time=60,
                coalesce=False,
                max_instances=1,
            )
            logger.info(
                "Scheduled task %s (freq=%s, config=%s).",
                task.task_id,
                task.frequency,
                task.config,
            )
        except InvalidFunctionError as exc:
            logger.error("Failed to schedule task %s: %s", task.task_id, exc)
            raise SchedulerError(f"Cannot schedule task {task.task_id}.") from exc

    def _unschedule_task(self, task_id: str) -> None:
        """Remove a job from APScheduler."""
        try:
            self._scheduler.remove_job(task_id)
            logger.info("Unscheduled task %s.", task_id)
        except Exception as exc:  # APScheduler raises JobLookupError
            logger.warning("