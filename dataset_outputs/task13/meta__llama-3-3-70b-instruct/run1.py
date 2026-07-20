import os
import logging
from typing import Dict, List
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime
import json

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class TaskScheduler:
    """
    A task scheduler that runs scheduled jobs at specified intervals.

    Features:
    - Add/remove scheduled tasks
    - Persistent storage of tasks
    - Task execution logging
    - Support for different scheduling frequencies (daily, hourly, minute-level)
    """

    def __init__(self, tasks_file: str = 'tasks.json'):
        """
        Initializes the task scheduler.

        Args:
        - tasks_file (str): The file path to store tasks (default: 'tasks.json')
        """
        self.tasks_file = tasks_file
        self.scheduler = BlockingScheduler()
        self.tasks: Dict[str, Dict] = self.load_tasks()

    def load_tasks(self) -> Dict[str, Dict]:
        """
        Loads tasks from the tasks file.

        Returns:
        - A dictionary of tasks
        """
        if os.path.exists(self.tasks_file):
            with open(self.tasks_file, 'r') as f:
                return json.load(f)
        else:
            return {}

    def save_tasks(self) -> None:
        """
        Saves tasks to the tasks file.
        """
        with open(self.tasks_file, 'w') as f:
            json.dump(self.tasks, f)

    def add_task(self, task_id: str, func: callable, frequency: str, **kwargs) -> None:
        """
        Adds a scheduled task.

        Args:
        - task_id (str): The task ID
        - func (callable): The task function
        - frequency (str): The scheduling frequency (daily, hourly, minute-level)
        - **kwargs: Additional keyword arguments for the task function
        """
        if task_id in self.tasks:
            raise ValueError(f"Task '{task_id}' already exists")

        trigger: CronTrigger
        if frequency == 'daily':
            trigger = CronTrigger(hour=0, minute=0)
        elif frequency == 'hourly':
            trigger = CronTrigger(minute=0)
        elif frequency == 'minute-level':
            trigger = CronTrigger(second=0)
        else:
            raise ValueError(f"Invalid frequency '{frequency}'")

        self.tasks[task_id] = {'func': func.__name__, 'frequency': frequency, 'kwargs': kwargs}
        self.scheduler.add_job(func, trigger, **kwargs)
        self.save_tasks()

    def remove_task(self, task_id: str) -> None:
        """
        Removes a scheduled task.

        Args:
        - task_id (str): The task ID
        """
        if task_id not in self.tasks:
            raise ValueError(f"Task '{task_id}' does not exist")

        self.scheduler.remove_job(task_id)
        del self.tasks[task_id]
        self.save_tasks()

    def run(self) -> None:
        """
        Runs the task scheduler.
        """
        self.scheduler.start()

def example_task(**kwargs) -> None:
    """
    An example task function.
    """
    logging.info(f"Task executed with kwargs: {kwargs}")

if __name__ == '__main__':
    scheduler = TaskScheduler()
    scheduler.add_task('example', example_task, 'minute-level', foo='bar')
    scheduler.run()