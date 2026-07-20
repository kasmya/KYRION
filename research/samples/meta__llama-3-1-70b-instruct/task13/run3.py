import logging
import os
import pickle
import schedule
import time
from typing import Callable, Dict

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class TaskScheduler:
    def __init__(self, storage_file: str = 'tasks.dat'):
        """
        Initialize the task scheduler.

        Args:
            storage_file (str): The file used to store tasks persistently.
        """
        self.storage_file = storage_file
        self.tasks: Dict[str, schedule.Job] = self.load_tasks()

    def load_tasks(self) -> Dict[str, schedule.Job]:
        """
        Load tasks from the storage file.

        Returns:
            Dict[str, schedule.Job]: A dictionary of tasks.
        """
        if os.path.exists(self.storage_file):
            with open(self.storage_file, 'rb') as file:
                return pickle.load(file)
        return {}

    def save_tasks(self) -> None:
        """
        Save tasks to the storage file.
        """
        with open(self.storage_file, 'wb') as file:
            pickle.dump(self.tasks, file)

    def add_task(self, name: str, func: Callable, interval: int, unit: str = 'minutes') -> None:
        """
        Add a scheduled task.

        Args:
            name (str): The task name.
            func (Callable): The task function.
            interval (int): The interval between executions.
            unit (str): The unit of the interval (minutes, hours, days).
        """
        if name in self.tasks:
            logger.warning(f'Task {name} already exists.')
            return
        try:
            if unit == 'minutes':
                job = schedule.every(interval).minutes.do(func)
            elif unit == 'hours':
                job = schedule.every(interval).hours.do(func)
            elif unit == 'days':
                job = schedule.every(interval).days.do(func)
            else:
                raise ValueError(f'Invalid unit: {unit}')
            self.tasks[name] = job
            self.save_tasks()
            logger.info(f'Task {name} added.')
        except Exception as e:
            logger.error(f'Failed to add task {name}: {str(e)}')

    def remove_task(self, name: str) -> None:
        """
        Remove a scheduled task.

        Args:
            name (str): The task name.
        """
        if name not in self.tasks:
            logger.warning(f'Task {name} does not exist.')
            return
        del self.tasks[name]
        self.save_tasks()
        logger.info(f'Task {name} removed.')

    def run_pending(self) -> None:
        """
        Run all scheduled tasks that are due.
        """
        schedule.run_pending()

def task_example():
    logger.info('Task executed.')

if __name__ == '__main__':
    scheduler = TaskScheduler()
    scheduler.add_task('example', task_example, 1, unit='minutes')
    while True:
        scheduler.run_pending()
        time.sleep(1)