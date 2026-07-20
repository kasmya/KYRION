"""
Task Scheduler with persistence, logging and flexible intervals.

Features
--------
- Add, remove, list scheduled tasks.
- Persistent storage of tasks in a JSON file.
- Execution logging with rotating file handler.
- Scheduling frequencies: daily (at a specific time), hourly, every N minutes.
- Type hints, docstrings and comprehensive error handling.
- Security: tasks must reference callables that are importable from whitelisted
  modules only.

Dependencies
------------
- APScheduler (install via `pip install APScheduler`)

Only the standard library and APScheduler are used.
"""

from __future__ import annotations

import importlib
import json
import logging
import logging.handlers
import os
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Literal, Optional

from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED, JobExecutionEvent
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
TASKS_FILE = Path("tasks.json")
LOG_FILE = Path("task_scheduler.log")
MAX_LOG_BYTES = 5 * 1024 * 1024  # 5 MB
BACKUP_COUNT = 3
# Whitelisted top‑level packages from which tasks may be imported.
WHITELISTED_MODULES = {"mytasks", "builtins"}

# --------------------------------------------------------------------------- #
# Logging Setup
# --------------------------------------------------------------------------- #
logger = logging.getLogger("TaskScheduler")
logger.setLevel(logging.INFO)
handler = logging.handlers.RotatingFileHandler(
    LOG_FILE, maxBytes=MAX_LOG_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8"
)
formatter = logging.Formatter(
    "%(asctime)s | %(levelname)s | %(threadName)s | %(message)s"
)
handler.setFormatter(formatter)
logger.addHandler(handler)


# --------------------------------------------------------------------------- #
# Data Model
# --------------------------------------------------------------------------- #
ScheduleType = Literal["daily", "hourly", "interval"]


@dataclass
class Task:
    """Definition of a scheduled task."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    func_path: str = ""  # "module:function"
    schedule_type: ScheduleType = "interval"
    # For daily: "HH:MM"
    # For hourly: minute offset "MM"
    # For interval: number of minutes as int string
    schedule_value: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON‑serialisable representation."""
        return asdict(self)

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "Task":
        """Create a Task instance from a dict."""
        return Task(**data)


# --------------------------------------------------------------------------- #
# Helper Functions
# --------------------------------------------------------------------------- #
def _import_callable(func_path: str) -> Callable[..., Any]:
    """
    Import a callable given a ``module:function`` path.

    Raises
    ------
    ValueError
        If the module is not whitelisted or the path is malformed.
    ImportError
        If the module or attribute cannot be imported.
    """
    if ":" not in func_path:
        raise ValueError(f"Invalid func_path '{func_path}'. Expected format 'module:function'.")

    module_name, attr_name = func_path.split(":", 1)

    # Security check: only allow whitelisted top‑level packages.
    top_pkg = module_name.split(".", 1)[0]
    if top_pkg not in WHITELISTED_MODULES:
        raise ValueError(f"Import from module '{module_name}' is not allowed.")

    module = importlib.import_module(module_name)
    try:
        func = getattr(module, attr_name)
    except AttributeError as exc:
        raise ImportError(f"Module '{module_name}' has no attribute '{attr_name}'.") from exc

    if not callable(func):
        raise TypeError(f"Imported object '{func_path}' is not callable.")
    return func


def _load_tasks(file_path: Path) -> List[Task]:
    """Load tasks from JSON file; return empty list if file does not exist."""
    if not file_path.is_file():
        return []
    try:
        with file_path.open("r", encoding="utf-8") as f:
            raw = json.load(f)
        return [Task.from_dict(item) for item in raw]
    except (json.JSONDecodeError, OSError) as exc:
        logger.error("Failed to load tasks from %s: %s", file_path, exc)
        return []


def _save_tasks(file_path: Path, tasks: List[Task]) -> None:
    """Persist tasks to JSON file."""
    try:
        with file_path.open("w", encoding="utf-8") as f:
            json.dump([t.to_dict() for t in tasks], f, indent=2)
    except OSError as exc:
        logger.error("Failed to persist tasks to %s: %s", file_path, exc)


# --------------------------------------------------------------------------- #
# Core Scheduler Class
# --------------------------------------------------------------------------- #
class TaskScheduler:
    """Manage scheduled tasks with persistence and logging."""

    def __init__(self, storage_file: Path = TASKS_FILE) -> None:
        """
        Parameters
        ----------
        storage_file : Path
            Path to the JSON file used for persisting tasks.
        """
        self.storage_file = storage_file
        self._tasks: Dict[str, Task] = {t.id: t for t in _load_tasks(storage_file)}
        self._scheduler = BackgroundScheduler()
        self._scheduler.add_listener(self._job_listener, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)
        self._lock = threading.RLock()
        self._is_running = False

    # ------------------------------------------------------------------- #
    # Private Helper Methods
    # ------------------------------------------------------------------- #
    def _job_listener(self, event: JobExecutionEvent) -> None:
        """Log job execution results."""
        job = self._scheduler.get_job(event.job_id)
        if job is None:
            return
        task_name = job.name or "Unnamed"
        if event.exception:
            logger.error("Task '%s' failed: %s", task_name, event.exception, exc_info=event.exception)
        else:
            logger.info("Task '%s' completed successfully.", task_name)

    def _build_trigger(self, task: Task) -> CronTrigger:
        """Create an APScheduler CronTrigger based on task's schedule."""
        if task.schedule_type == "daily":
            hour, minute = map(int, task.schedule_value.split(":"))
            return CronTrigger(hour=hour, minute=minute)
        if task.schedule_type == "hourly":
            minute = int(task.schedule_value)
            return CronTrigger(minute=minute)
        if task.schedule_type == "interval":
            minutes = int(task.schedule_value)
            return CronTrigger(minute=f"*/{minutes}")
        raise ValueError(f"Unsupported schedule_type: {task.schedule_type}")

    def _schedule_task(self, task: Task) -> None:
        """Add a task to the APScheduler instance."""
        try:
            func = _import_callable(task.func_path)
        except Exception as exc:
            logger.error("Cannot schedule task '%s' (%s): %s", task.name, task.id, exc)
            return

        trigger = self._build_trigger(task)
        self._scheduler.add_job(
            func,
            trigger,
            id=task.id,
            name=task.name,
            replace_existing=True,
            misfire_grace_time=60,
        )
        logger.info("Scheduled task '%s' (%s) with trigger %s.", task.name, task.id, trigger)

    def _unschedule_task(self, task_id: str) -> None:
        """Remove a job from APScheduler by ID."""
        try:
            self._scheduler.remove_job(task_id)
            logger.info("Removed scheduled job %s.", task_id)
        except Exception as exc:
            logger.warning("Failed to remove job %s: %s", task_id, exc)

    # ------------------------------------------------------------------- #
    # Public API
    # ------------------------------------------------------------------- #
    def start(self) -> None:
        """Start the background scheduler; safe to call multiple times."""
        with self._lock:
            if not self._is_running:
                for task in self._tasks.values():
                    self._schedule_task(task)
                self._scheduler.start()
                self._