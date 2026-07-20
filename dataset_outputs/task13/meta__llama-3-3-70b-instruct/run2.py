import logging
import os
import pickle
import schedule
import time
from datetime import datetime
from enum import Enum
from typing import Callable, Dict

class SchedulingFrequency(Enum):
    """Enum for scheduling frequencies."""
    DAILY = "daily"
    HOURLY = "hourly"
    MINUTELY = "minutely"

class TaskScheduler:
    """A task scheduler that runs scheduled jobs at specified intervals."""
    
    def __init__(self, storage_file: str = "tasks.pkl"):
        """
        Initialize the task scheduler.

        Args:
        storage_file (str): The file to store tasks in. Defaults to "tasks.pkl".
        """
        self.storage_file = storage_file
        self.tasks: Dict[str, Dict[str, str]] = self.load_tasks()
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)
        self.handler = logging.FileHandler("task_scheduler.log")
        self.handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
        self.logger.addHandler(self.handler)

    def load_tasks(self) -> Dict[str, Dict[str, str]]:
        """
        Load tasks from the storage file.

        Returns:
        Dict[str, Dict[str, str]]: A dictionary of tasks.
        """
        if os.path.exists(self.storage_file):
            with open(self.storage_file, "rb") as f:
                return pickle.load(f)
        else:
            return {}

    def save_tasks(self) -> None:
        """
        Save tasks to the storage file.
        """
        with open(self.storage_file, "wb") as f:
            pickle.dump(self.tasks, f)

    def add_task(self, task_name: str, func: Callable[[], None], frequency: SchedulingFrequency, interval: int = 1) -> None:
        """
        Add a scheduled task.

        Args:
        task_name (str): The name of the task.
        func (Callable[[], None]): The function to run.
        frequency (SchedulingFrequency): The scheduling frequency.
        interval (int): The interval at which to run the task. Defaults to 1.
        """
        if task_name in self.tasks:
            self.logger.warning(f"Task {task_name} already exists.")
            return
        self.tasks[task_name] = {"func": func.__name__, "frequency": frequency.value, "interval": interval}
        self.save_tasks()
        self.schedule_task(task_name, func, frequency, interval)
        self.logger.info(f"Task {task_name} added.")

    def remove_task(self, task_name: str) -> None:
        """
        Remove a scheduled task.

        Args:
        task_name (str): The name of the task.
        """
        if task_name not in self.tasks:
            self.logger.warning(f"Task {task_name} does not exist.")
            return
        del self.tasks[task_name]
        self.save_tasks()
        self.logger.info(f"Task {task_name} removed.")

    def schedule_task(self, task_name: str, func: Callable[[], None], frequency: SchedulingFrequency, interval: int = 1) -> None:
        """
        Schedule a task to run at the specified interval.

        Args:
        task_name (str): The name of the task.
        func (Callable[[], None]): The function to run.
        frequency (SchedulingFrequency): The scheduling frequency.
        interval (int): The interval at which to run the task. Defaults to 1.
        """
        if frequency == SchedulingFrequency.DAILY:
            schedule.every(interval).days.do(func)
        elif frequency == SchedulingFrequency.HOURLY:
            schedule.every(interval).hours.do(func)
        elif frequency == SchedulingFrequency.MINUTELY:
            schedule.every(interval).minutes.do(func)
        else:
            self.logger.error(f"Invalid frequency {frequency.value}.")

    def run_pending_tasks(self) -> None:
        """
        Run any pending tasks.
        """
        schedule.run_pending()

def example_task() -> None:
    """An example task that logs a message."""
    logging.getLogger(__name__).info("Example task ran.")

def main() -> None:
    """The main function."""
    scheduler = TaskScheduler()
    scheduler.add_task("example_task", example_task, SchedulingFrequency.MINUTELY, 1)
    while True:
        scheduler.run_pending_tasks()
        time.sleep(1)

if __name__ == "__main__":
    main()