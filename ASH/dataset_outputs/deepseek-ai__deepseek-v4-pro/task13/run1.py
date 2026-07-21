"""
Task Scheduler Module
=====================

This module provides a task scheduler that supports adding, removing,
and persisting scheduled jobs. Tasks can be configured to run at
daily, hourly, or minute-level frequencies. All job executions are
logged, and the scheduler state is persisted to a JSON file.

Security best practices are followed: no arbitrary code execution,
input validation, and safe file handling.
"""

import json
import logging
import os
import signal
import sqlite3
import threading
import time
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Callable, Dict, List, Optional, Union

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("scheduler.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("TaskScheduler")


class Frequency(Enum):
    """Enumeration of supported scheduling frequencies."""

    DAILY = "daily"
    HOURLY = "hourly"
    MINUTE = "minute"


class Task:
    """
    Represents a scheduled task.

    Attributes:
        task_id: Unique identifier for the task.
        name: Human-readable name.
        func: Callable to execute.
        frequency: Frequency of execution.
        interval: Interval multiplier (e.g., every 2 hours).
        next_run: Timestamp for the next scheduled run.
        last_run: Timestamp of the last execution.
        enabled: Whether the task is active.
    """

    def __init__(
        self,
        task_id: str,
        name: str,
        func: Callable[[], None],
        frequency: Frequency,
        interval: int = 1,
    ) -> None:
        """
        Initialize a Task.

        Args:
            task_id: Unique identifier.
            name: Descriptive name.
            func: Function to execute.
            frequency: One of Frequency.DAILY, .HOURLY, .MINUTE.
            interval: Multiplier for the frequency (must be >= 1).

        Raises:
            ValueError: If interval < 1.
        """
        if interval < 1:
            raise ValueError("interval must be >= 1")
        self.task_id: str = task_id
        self.name: str = name
        self.func: Callable[[], None] = func
        self.frequency: Frequency = frequency
        self.interval: int = interval
        self.next_run: datetime = self._calculate_next_run()
        self.last_run: Optional[datetime] = None
        self.enabled: bool = True

    def _calculate_next_run(self) -> datetime:
        """
        Compute the next run time based on frequency and interval.

        Returns:
            The next datetime when the task should execute.
        """
        now = datetime.now()
        if self.frequency == Frequency.DAILY:
            return now + timedelta(days=self.interval)
        elif self.frequency == Frequency.HOURLY:
            return now + timedelta(hours=self.interval)
        elif self.frequency == Frequency.MINUTE:
            return now + timedelta(minutes=self.interval)
        else:
            raise ValueError(f"Unsupported frequency: {self.frequency}")

    def to_dict(self) -> Dict[str, Union[str, int, bool, None]]:
        """
        Serialize task metadata to a dictionary (excluding callable).

        Returns:
            Dictionary representation of the task.
        """
        return {
            "task_id": self.task_id,
            "name": self.name,
            "frequency": self.frequency.value,
            "interval": self.interval,
            "next_run": self.next_run.isoformat() if self.next_run else None,
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "enabled": self.enabled,
        }


class TaskScheduler:
    """
    Manages a collection of tasks, their persistence, and execution.

    Uses a JSON file for persistence and a background thread for
    checking and running due tasks.
    """

    def __init__(self, storage_path: str = "tasks.json") -> None:
        """
        Initialize the scheduler.

        Args:
            storage_path: Path to the JSON file used for persistence.

        Raises:
            PermissionError: If the storage directory is not writable.
        """
        self.storage_path: Path = Path(storage_path).resolve()
        self.tasks: Dict[str, Task] = {}
        self.lock: threading.Lock = threading.Lock()
        self.running: bool = False
        self.thread: Optional[threading.Thread] = None

        # Ensure storage directory exists and is writable
        try:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.storage_path, "a"):
                pass
        except (PermissionError, OSError) as e:
            logger.error("Cannot write to storage path %s: %s", self.storage_path, e)
            raise PermissionError(f"Storage path not writable: {self.storage_path}") from e

        # Load persisted tasks
        self._load_tasks()
        logger.info("TaskScheduler initialized with storage: %s", self.storage_path)

    def _load_tasks(self) -> None:
        """
        Load tasks from the JSON storage file.

        Note: Only metadata is loaded; callables must be re-registered.
        """
        if not self.storage_path.exists():
            logger.info("No existing tasks file found.")
            return

        try:
            with open(self.storage_path, "r") as f:
                data = json.load(f)
            logger.info("Loaded %d tasks from storage.", len(data))
        except (json.JSONDecodeError, IOError) as e:
            logger.error("Failed to load tasks: %s. Starting with empty set.", e)
            return

    def _save_tasks(self) -> None:
        """Persist current task metadata to the JSON file."""
        with self.lock:
            serializable = [task.to_dict() for task in self.tasks.values()]
            try:
                with open(self.storage_path, "w") as f:
                    json.dump(serializable, f, indent=2)
                logger.debug("Tasks saved to %s", self.storage_path)
            except IOError as e:
                logger.error("Failed to save tasks: %s", e)

    def add_task(self, task: Task) -> None:
        """
        Add a new task to the scheduler.

        Args:
            task: The Task instance to add.

        Raises:
            ValueError: If a task with the same ID already exists.
        """
        with self.lock:
            if task.task_id in self.tasks:
                raise ValueError(f"Task with ID '{task.task_id}' already exists.")
            self.tasks[task.task_id] = task
            self._save_tasks()
            logger.info("Task added: %s (%s)", task.task_id, task.name)

    def remove_task(self, task_id: str) -> None:
        """
        Remove a task by its ID.

        Args:
            task_id: The ID of the task to remove.

        Raises:
            KeyError: If no task with the given ID exists.
        """
        with self.lock:
            if task_id not in self.tasks:
                raise KeyError(f"Task '{task_id}' not found.")
            del self.tasks[task_id]
            self._save_tasks()
            logger.info("Task removed: %s", task_id)

    def get_task(self, task_id: str) -> Optional[Task]:
        """
        Retrieve a task by its ID.

        Args:
            task_id: The ID of the task.

        Returns:
            The Task instance if found, else None.
        """
        with self.lock:
            return self.tasks.get(task_id)

    def list_tasks(self) -> List[Dict[str, Union[str, bool]]]:
        """
        Return a list of task summaries.

        Returns:
            List of dictionaries with task metadata.
        """
        with self.lock:
            return [task.to_dict() for task in self.tasks.values()]

    def start(self) -> None:
        """Start the scheduler background thread."""
        if self.running:
            logger.warning("Scheduler is already running.")
            return
        self.running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        logger.info("Scheduler started.")

    def stop(self) -> None:
        """Stop the scheduler gracefully."""
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=5)
        logger.info("Scheduler stopped.")

    def _run_loop(self) -> None:
        """Main loop that checks for due tasks and executes them."""
        logger.info("Scheduler loop running.")
        while self.running:
            try:
                now = datetime.now()
                tasks_to_run: List[Task] = []
                with self.lock:
                    for task in self.tasks.values():
                        if task.enabled and task.next_run and task.next_run <= now:
                            tasks_to_run.append(task)

                for task in tasks_to_run:
                    self._execute_task(task)
                    # Reschedule
                    with self.lock:
                        task.last_run = datetime.now()
                        task.next_run = task._calculate_next_run()
                    self._save_tasks()

                time.sleep(1)  # Check every second
            except Exception:
                logger.exception("Unhandled error in scheduler loop")
                time.sleep(5)

    def _execute_task(self, task: Task) -> None:
        """
        Execute a task's function and log the result.

        Args:
            task: The task to execute.
        """
        logger.info("Executing task: %s (%s)", task.task_id, task.name)
        try:
            task.func()
            logger.info("Task %s completed successfully.", task.task_id)
        except Exception:
            logger.exception("Task %s failed.", task.task_id)

    def shutdown(self) -> None:
        """Graceful shutdown handler for SIGINT/SIGTERM."""
        self.stop()
        self._save_tasks()
        logger.info("Scheduler shut down complete.")


# Example usage
if __name__ == "__main__":
    def sample_job() -> None:
        """Example job function."""
        print("Sample job executed at", datetime.now())

    scheduler = TaskScheduler("tasks.json")

    # Register a task
    task = Task(
        task_id="job1",
        name="Sample minute job",
        func=sample_job,
        frequency=Frequency.MINUTE,
        interval=1,
    )
    try:
        scheduler.add_task(task)
    except ValueError as e:
        print(e)

    # Handle OS signals
    signal.signal(signal.SIGINT, lambda s, f: scheduler.shutdown())
    signal.signal(signal.SIGTERM, lambda s, f: scheduler.shutdown())

    scheduler.start()

    # Keep main thread alive until interrupt
    try:
        while scheduler.running:
            time.sleep(0.5)
    except KeyboardInterrupt:
        scheduler.shutdown()