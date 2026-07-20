import logging
import os
import pickle
import schedule
import time
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Callable, Dict, Optional

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler("scheduler.log"), logging.StreamHandler()]
)

class ScheduleFrequency(Enum):
    """Enumeration for scheduling frequencies."""
    MINUTE = 1
    HOURLY = 2
    DAILY = 3

@dataclass
class ScheduledTask:
    """Dataclass for representing a scheduled task."""
    name: str
    job: Callable[[], None]
    frequency: ScheduleFrequency
    minute: Optional[int] = None  # For minute-level scheduling
    hour: Optional[int] = None   # For hourly scheduling

    def __post_init__(self):
        """Validate frequency and time settings."""
        if self.frequency == ScheduleFrequency.MINUTE and self.minute is None:
            raise ValueError("Minute must be specified for MINUTE frequency")
        if self.frequency == ScheduleFrequency.HOURLY and self.hour is None:
            raise ValueError("Hour must be specified for HOURLY frequency")
        if self.frequency == ScheduleFrequency.DAILY and (self.hour is not None or self.minute is not None):
            raise ValueError("Hour and Minute must not be specified for DAILY frequency")

class TaskScheduler:
    """A task scheduler with persistent storage and logging."""
    def __init__(self, storage_path: str = "scheduled_tasks.dat"):
        """
        Initialize the task scheduler.

        :param storage_path: Path to store scheduled tasks persistently.
        """
        self.storage_path = storage_path
        self.tasks: Dict[str, ScheduledTask] = self.load_tasks()
        self.lock = False  # Simple lock for concurrent access protection

    def load_tasks(self) -> Dict[str, ScheduledTask]:
        """Load scheduled tasks from persistent storage."""
        if os.path.exists(self.storage_path):
            with open(self.storage_path, "rb") as file:
                return pickle.load(file)
        return {}

    def save_tasks(self) -> None:
        """Save scheduled tasks to persistent storage."""
        with open(self.storage_path, "wb") as file:
            pickle.dump(self.tasks, file)

    def add_task(self, task: ScheduledTask) -> None:
        """
        Add a scheduled task.

        :param task: The task to be scheduled.
        :raises ValueError: If a task with the same name already exists.
        """
        if task.name in self.tasks:
            raise ValueError(f"Task '{task.name}' already exists.")
        self.tasks[task.name] = task
        self.schedule_task(task)
        self.save_tasks()

    def remove_task(self, task_name: str) -> None:
        """
        Remove a scheduled task.

        :param task_name: Name of the task to remove.
        :raises KeyError: If the task does not exist.
        """
        if task_name not in self.tasks:
            raise KeyError(f"Task '{task_name}' does not exist.")
        del self.tasks[task_name]
        self.reschedule_all()
        self.save_tasks()

    def schedule_task(self, task: ScheduledTask) -> None:
        """
        Schedule a task based on its frequency.

        :param task: The task to schedule.
        """
        if task.frequency == ScheduleFrequency.MINUTE:
            schedule.every().minute.at(f"{task.minute:02d}").do(self.execute_task, task.name)
        elif task.frequency == ScheduleFrequency.HOURLY:
            schedule.every().day.at(f"{task.hour:02d}:00").do(self.execute_task, task.name)
        elif task.frequency == ScheduleFrequency.DAILY:
            schedule.every().day.at("00:00").do(self.execute_task, task.name)

    def reschedule_all(self) -> None:
        """Clear and reschedule all tasks."""
        schedule.clear()
        for task in self.tasks.values():
            self.schedule_task(task)

    def execute_task(self, task_name: str) -> None:
        """
        Execute a scheduled task and log the execution.

        :param task_name: Name of the task to execute.
        """
        if self.lock:
            logging.warning("Concurrent execution prevented. Task skipped.")
            return
        self.lock = True
        try:
            task = self.tasks[task_name]
            logging.info(f"Executing task '{task_name}'")
            task.job()
            logging.info(f"Task '{task_name}' executed successfully.")
        except Exception as e:
            logging.error(f"Error executing task '{task_name}': {e}", exc_info=True)
        finally:
            self.lock = False

    def run(self) -> None:
        """Start the scheduler."""
        logging.info("Scheduler started. Waiting for scheduled tasks to run...")
        while True:
            schedule.run_pending()
            time.sleep(1)

# Example Usage
if __name__ == "__main__":
    def example_job() -> None:
        logging.info("Example job executed.")

    scheduler = TaskScheduler()
    try:
        scheduler.add_task(ScheduledTask("example", example_job, ScheduleFrequency.MINUTE, minute=0))
        scheduler.run()
    except KeyboardInterrupt:
        logging.info("Scheduler stopped by user.")
    finally:
        scheduler.save_tasks()