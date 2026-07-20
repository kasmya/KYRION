import logging
import os
import pickle
import schedule
import time
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Callable, Optional

# Security: Set logging configuration to track task executions and errors
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler("task_scheduler.log"), logging.StreamHandler()]
)

class ScheduleFrequency(Enum):
    """Enumeration for supported scheduling frequencies"""
    DAILY = "daily"
    HOURLY = "hourly"
    MINUTE = "minute"

@dataclass
class ScheduledTask:
    """Dataclass to represent a scheduled task"""
    id: str
    func: Callable
    frequency: ScheduleFrequency
    minute: Optional[int] = None  # Specific minute for minute-level scheduling
    hour: Optional[int] = None    # Specific hour for hourly scheduling

    def __post_init__(self):
        """Validation for scheduling parameters"""
        if self.frequency == ScheduleFrequency.MINUTE and self.minute is None:
            raise ValueError("Minute must be specified for minute-level scheduling")
        if self.frequency == ScheduleFrequency.HOURLY and self.hour is None:
            raise ValueError("Hour must be specified for hourly scheduling")

class TaskScheduler:
    """Task Scheduler with persistent storage and logging"""
    def __init__(self, storage_file: str = "scheduled_tasks.pkl"):
        """
        Initialize the task scheduler with a storage file for persistence.

        :param storage_file: File path for storing scheduled tasks (defaults to "scheduled_tasks.pkl")
        """
        self.storage_file = storage_file
        self.tasks: dict[str, ScheduledTask] = self.load_tasks()

    def load_tasks(self) -> dict[str, ScheduledTask]:
        """Load scheduled tasks from the storage file if it exists"""
        if os.path.exists(self.storage_file):
            with open(self.storage_file, "rb") as file:
                return pickle.load(file)
        return {}

    def save_tasks(self) -> None:
        """Save the current tasks to the storage file"""
        with open(self.storage_file, "wb") as file:
            pickle.dump(self.tasks, file)

    def add_task(self, task: ScheduledTask) -> None:
        """
        Add a new scheduled task.

        :param task: The ScheduledTask instance to be added
        """
        if task.id in self.tasks:
            raise ValueError(f"Task ID '{task.id}' already exists")
        self.tasks[task.id] = task
        self.schedule_task(task)
        self.save_tasks()

    def remove_task(self, task_id: str) -> None:
        """
        Remove a scheduled task by its ID.

        :param task_id: ID of the task to remove
        """
        if task_id not in self.tasks:
            raise ValueError(f"Task ID '{task_id}' not found")
        del self.tasks[task_id]
        self.save_tasks()
        # Note: Un-scheduling is not directly supported by 'schedule' library;
        #       Workaround: Restart scheduler or use a more advanced scheduler like APScheduler

    def schedule_task(self, task: ScheduledTask) -> None:
        """
        Schedule the task based on its frequency.

        :param task: The ScheduledTask to schedule
        """
        if task.frequency == ScheduleFrequency.DAILY:
            schedule.every().day.at("00:00").do(self.execute_task, task.id)  # Daily at midnight
        elif task.frequency == ScheduleFrequency.HOURLY:
            schedule.every().hour.at(f"{task.hour:02d}:00").do(self.execute_task, task.id)
        elif task.frequency == ScheduleFrequency.MINUTE:
            schedule.every().minute.at(f"{task.minute:02d}") \
                .do(self.execute_task, task.id)  # Execute at the specified minute every hour

    def execute_task(self, task_id: str) -> None:
        """
        Execute a scheduled task by its ID and log the execution.

        :param task_id: ID of the task to execute
        """
        task = self.tasks.get(task_id)
        if task:
            try:
                task.func()
                logging.info(f"Task '{task_id}' executed successfully")
            except Exception as e:
                logging.error(f"Error executing task '{task_id}': {e}")
        else:
            logging.warning(f"Task '{task_id}' not found for execution")

    def run(self) -> None:
        """Start the task scheduler"""
        while True:
            schedule.run_pending()
            time.sleep(1)

# Example Usage
if __name__ == "__main__":
    def example_task():
        print("Example task executed")
        logging.info("Example task logged")

    scheduler = TaskScheduler()
    task_id = "example"
    new_task = ScheduledTask(task_id, example_task, ScheduleFrequency.MINUTE, minute=30)
    scheduler.add_task(new_task)
    scheduler.run()