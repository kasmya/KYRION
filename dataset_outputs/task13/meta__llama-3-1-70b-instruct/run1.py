import os
import logging
import json
import schedule
import time
from typing import Callable, Any
from enum import Enum

class Frequency(Enum):
    """Enumeration of supported frequencies"""
    DAILY = 1
    HOURLY = 2
    MINUTELY = 3

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
        Initialize the task scheduler.
        
        Args:
        - storage_file (str): The file to use for persistent storage of tasks.
        """
        self.storage_file = storage_file
        self.tasks = self.load_tasks()
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)
        handler = logging.FileHandler('task_scheduler.log')
        handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
        self.logger.addHandler(handler)
        
    def load_tasks(self) -> dict:
        """
        Load tasks from persistent storage.
        
        Returns:
        - dict: A dictionary of tasks.
        """
        if os.path.exists(self.storage_file):
            with open(self.storage_file, 'r') as file:
                return json.load(file)
        else:
            return {}
        
    def save_tasks(self) -> None:
        """
        Save tasks to persistent storage.
        """
        with open(self.storage_file, 'w') as file:
            json.dump(self.tasks, file)
        
    def add_task(self, name: str, frequency: Frequency, interval: int, job: Callable[..., Any]) -> None:
        """
        Add a scheduled task.
        
        Args:
        - name (str): The name of the task.
        - frequency (Frequency): The frequency of the task.
        - interval (int): The interval of the task.
        - job (Callable[..., Any]): The job to be executed.
        """
        if name in self.tasks:
            raise ValueError('Task already exists')
        
        self.tasks[name] = {'frequency': frequency.name, 'interval': interval, 'job': job}
        self.save_tasks()
        
        if frequency == Frequency.DAILY:
            schedule.every().day.at(f'{interval}:00').do(job)  # Use 24-hour clock
        elif frequency == Frequency.HOURLY:
            schedule.every().hour.do(job)
        elif frequency == Frequency.MINUTELY:
            schedule.every(interval).minutes.do(job)
        
    def remove_task(self, name: str) -> None:
        """
        Remove a scheduled task.
        
        Args:
        - name (str): The name of the task.
        """
        if name not in self.tasks:
            raise ValueError('Task does not exist')
        
        del self.tasks[name]
        self.save_tasks()
        
    def run_pending(self) -> None:
        """
        Run all pending tasks.
        """
        schedule.run_pending()
        self.logger.info('Ran pending tasks')
        
    def start(self) -> None:
        """
        Start the task scheduler.
        """
        while True:
            self.run_pending()
            time.sleep(1)

# Example usage:
if __name__ == '__main__':
    scheduler = TaskScheduler()
    
    def example_job():
        print('Hello, world!')
    
    scheduler.add_task('example', Frequency.MINUTELY, 1, example_job)
    scheduler.start()