import os
import logging
import json
import schedule
import time
from datetime import datetime, timedelta
from typing import Callable, Dict, Any

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class TaskScheduler:
    """
    A task scheduler that runs scheduled jobs at specified intervals.

    Features:
    - Add/remove scheduled tasks
    - Persistent storage of tasks
    - Task execution logging
    - Support for different scheduling frequencies (daily, hourly, minute-level)
    """

    def __init__(self, storage_file: str = 'tasks.json'):
        """
        Initializes the task scheduler.

        Args:
        - storage_file: The file used for persistent storage of tasks.
        """
        self.storage_file = storage_file
        self.tasks: Dict[str, Dict[str, Any]] = self.load_tasks()
        self.schedule = schedule

    def load_tasks(self) -> Dict[str, Dict[str, Any]]:
        """
        Loads tasks from the storage file.

        Returns:
        - A dictionary of tasks.
        """
        if os.path.exists(self.storage_file):
            with open(self.storage_file, 'r') as file:
                return json.load(file)
        return {}

    def save_tasks(self) -> None:
        """
        Saves tasks to the storage file.
        """
        with open(self.storage_file, 'w') as file:
            json.dump(self.tasks, file)

    def add_task(self, name: str, func: Callable, interval: int, unit: str) -> None:
        """
        Adds a new task to the scheduler.

        Args:
        - name: The name of the task.
        - func: The function to be executed.
        - interval: The interval at which the task should be executed.
        - unit: The unit of the interval (minutes, hours, days).

        Raises:
        - ValueError: If the unit is not valid.
        """
        if unit not in ['minutes', 'hours', 'days']:
            raise ValueError('Invalid unit')

        self.tasks[name] = {'func': func, 'interval': interval, 'unit': unit}
        self.save_tasks()
        self.schedule_task(name)

    def remove_task(self, name: str) -> None:
        """
        Removes a task from the scheduler.

        Args:
        - name: The name of the task.
        """
        if name in self.tasks:
            del self.tasks[name]
            self.save_tasks()
            self.unschedule_task(name)

    def schedule_task(self, name: str) -> None:
        """
        Schedules a task.

        Args:
        - name: The name of the task.
        """
        task = self.tasks[name]
        if task['unit'] == 'minutes':
            self.schedule.every(task['interval']).minutes.do(task['func'])
        elif task['unit'] == 'hours':
            self.schedule.every(task['interval']).hours.do(task['func'])
        elif task['unit'] == 'days':
            self.schedule.every(task['interval']).days.do(task['func'])

    def unschedule_task(self, name: str) -> None:
        """
        Unschedules a task.

        Args:
        - name: The name of the task.
        """
        self.schedule.clear(name)

    def run(self) -> None:
        """
        Runs the task scheduler.
        """
        while True:
            self.schedule.run_pending()
            time.sleep(1)

def example_task():
    logger.info('Task executed')

def main():
    scheduler = TaskScheduler()
    scheduler.add_task('example', example_task, 1, 'minutes')
    scheduler.run()

if __name__ == '__main__':
    main()