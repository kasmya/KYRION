import logging
import os
import pickle
import schedule
import time
from datetime import datetime
from typing import Callable, Dict

# Set up logging
logging.basicConfig(filename='scheduler.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class TaskScheduler:
    """A task scheduler that runs scheduled jobs at specified intervals."""
    
    def __init__(self, storage_file: str = 'tasks.pkl'):
        """
        Initializes the task scheduler with a storage file.
        
        Args:
        storage_file (str): The file to store tasks persistently. Defaults to 'tasks.pkl'.
        """
        self.storage_file = storage_file
        self.tasks: Dict[str, Dict] = self.load_tasks()
        self.scheduler = schedule.Scheduler()
        
    def load_tasks(self) -> Dict[str, Dict]:
        """
        Loads tasks from the storage file.
        
        Returns:
        Dict[str, Dict]: A dictionary of tasks.
        """
        if os.path.exists(self.storage_file):
            with open(self.storage_file, 'rb') as f:
                return pickle.load(f)
        else:
            return {}
        
    def save_tasks(self) -> None:
        """
        Saves tasks to the storage file.
        """
        with open(self.storage_file, 'wb') as f:
            pickle.dump(self.tasks, f)
            
    def add_task(self, task_name: str, task: Callable, frequency: str, interval: int) -> None:
        """
        Adds a scheduled task.
        
        Args:
        task_name (str): The name of the task.
        task (Callable): The task function.
        frequency (str): The frequency of the task (daily, hourly, minute).
        interval (int): The interval of the task.
        
        Raises:
        ValueError: If the frequency is not supported.
        """
        if frequency not in ['daily', 'hourly', 'minute']:
            raise ValueError("Unsupported frequency")
        
        self.tasks[task_name] = {'task': task, 'frequency': frequency, 'interval': interval}
        self.save_tasks()
        
        if frequency == 'daily':
            schedule.every(interval).days.do(task)
        elif frequency == 'hourly':
            schedule.every(interval).hours.do(task)
        else:
            schedule.every(interval).minutes.do(task)
            
    def remove_task(self, task_name: str) -> None:
        """
        Removes a scheduled task.
        
        Args:
        task_name (str): The name of the task.
        
        Raises:
        KeyError: If the task does not exist.
        """
        if task_name not in self.tasks:
            raise KeyError("Task does not exist")
        
        del self.tasks[task_name]
        self.save_tasks()
        
    def run_tasks(self) -> None:
        """
        Runs scheduled tasks.
        """
        while True:
            schedule.run_pending()
            time.sleep(1)
            
    def log_task_execution(self, task_name: str, success: bool) -> None:
        """
        Logs task execution.
        
        Args:
        task_name (str): The name of the task.
        success (bool): Whether the task executed successfully.
        """
        if success:
            logging.info(f"Task {task_name} executed successfully")
        else:
            logging.error(f"Task {task_name} failed to execute")

def example_task() -> None:
    """An example task."""
    print("Example task executed")
    logging.info("Example task executed")

if __name__ == "__main__":
    scheduler = TaskScheduler()
    scheduler.add_task('example', example_task, 'minute', 1)
    scheduler.run_tasks()