import logging
from logging.handlers import RotatingFileHandler
import os
import pickle
from typing import Callable, Dict, Optional
import schedule
import time
from enum import Enum
import getpass
import hashlib
import argparse

# Configuration
LOG_FILE = 'task_scheduler.log'
LOG_MAX_BYTES = 10 * 1024 * 1024  # 10MB
LOG_BACKUPS = 5
PERSISTENCE_FILE = 'scheduled_tasks.dat'

# Security: Basic authentication for task modification
class Auth:
    def __init__(self):
        self.username = 'scheduler'
        self.password_hash = self._hash_password('password123')  # Default password, should be changed

    def _hash_password(self, password: str) -> str:
        """Hash a password for storing."""
        return hashlib.sha256(password.encode()).hexdigest()

    def authenticate(self, username: str, password: str) -> bool:
        """Check if the provided credentials match the stored ones."""
        return username == self.username and self._hash_password(password) == self.password_hash

auth = Auth()

class ScheduleFrequency(Enum):
    """Enums for different scheduling frequencies."""
    MINUTE = 1
    HOURLY = 2
    DAILY = 3

class TaskScheduler:
    """
    A task scheduler with persistence, logging, and basic authentication.
    
    Attributes:
    - jobs (Dict[str, Dict]): Stored tasks with their frequencies and last run times.
    - logger (logging.Logger): Logger instance for task execution logging.
    """
    def __init__(self):
        self.jobs: Dict[str, Dict] = self.load_tasks()
        self.logger = self._setup_logging()

    def _setup_logging(self) -> logging.Logger:
        """Configure logging with rotation."""
        logger = logging.getLogger('task_scheduler')
        logger.setLevel(logging.INFO)
        handler = RotatingFileHandler(LOG_FILE, maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUPS)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        return logger

    def load_tasks(self) -> Dict[str, Dict]:
        """Load persisted tasks or return an empty dict if the file doesn't exist."""
        if os.path.exists(PERSISTENCE_FILE):
            with open(PERSISTENCE_FILE, 'rb') as f:
                return pickle.load(f)
        return {}

    def save_tasks(self) -> None:
        """Persist the current task schedule."""
        with open(PERSISTENCE_FILE, 'wb') as f:
            pickle.dump(self.jobs, f)

    def authenticate_task_modification(self, username: str, password: str) -> bool:
        """Check credentials before allowing task modifications."""
        return auth.authenticate(username, password)

    def add_task(self, task_name: str, job: Callable[[], None], frequency: ScheduleFrequency, username: str, password: str) -> None:
        """
        Add a new scheduled task.
        
        Args:
        - task_name (str): Unique name for the task.
        - job (Callable[[], None]): The function to execute.
        - frequency (ScheduleFrequency): How often to run the task.
        - username (str): Username for authentication.
        - password (str): Password for authentication.
        
        Raises:
        - ValueError: If authentication fails or task name already exists.
        """
        if not self.authenticate_task_modification(username, password):
            raise ValueError("Authentication failed")
        if task_name in self.jobs:
            raise ValueError("Task name already exists")
        
        # Schedule the job based on the frequency
        if frequency == ScheduleFrequency.MINUTE:
            schedule.every(1).minutes.do(job)  # Example: every minute, adjust as needed
        elif frequency == ScheduleFrequency.HOURLY:
            schedule.every(1).hours.do(job)  # Example: every hour, adjust as needed
        elif frequency == ScheduleFrequency.DAILY:
            schedule.every(1).days.do(job)  # Example: every day, adjust as needed
        
        self.jobs[task_name] = {
            'job': job,
            'frequency': frequency,
            'last_run': None
        }
        self.save_tasks()
        self.logger.info(f"Task '{task_name}' added successfully")

    def remove_task(self, task_name: str, username: str, password: str) -> None:
        """
        Remove a scheduled task.
        
        Args:
        - task_name (str): Name of the task to remove.
        - username (str): Username for authentication.
        - password (str): Password for authentication.
        
        Raises:
        - ValueError: If authentication fails or task does not exist.
        """
        if not self.authenticate_task_modification(username, password):
            raise ValueError("Authentication failed")
        if task_name not in self.jobs:
            raise ValueError("Task does not exist")
        
        # Unscheduling is not directly supported by schedule library in a simple way,
        # so we filter out the job from the scheduled jobs list
        schedule.jobs = [job for job in schedule.jobs if job.func != self.jobs[task_name]['job']]
        del self.jobs[task_name]
        self.save_tasks()
        self.logger.info(f"Task '{task_name}' removed successfully")

    def run_pending(self) -> None:
        """Run any pending scheduled tasks."""
        schedule.run_pending()
        time.sleep(1)  # Pause for 1 second before checking again

    def start(self) -> None:
        """Continuously run the scheduler in the background."""
        while True:
            self.run_pending()

def example_job() -> None:
    """An example job that logs a message."""
    print("Job executed")
    logging.getLogger('task_scheduler').info("Example job executed")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Task Scheduler CLI")
    subparsers = parser.add_subparsers(dest="command")
    
    # Add task parser
    add_parser = subparsers.add_parser("add", help="Add a new task")
    add_parser.add_argument("task_name", help="Name of the task")
    add_parser.add_argument("frequency", choices=['minute', 'hourly', 'daily'], help="Frequency of the task")
    add_parser.add_argument("-u", "--username", required=True, help="Username")
    add_parser.add_argument("-p", "--password", required=True, help="Password")
    
    # Remove task parser
    remove_parser = subparsers.add_parser("remove", help="Remove a task")
    remove_parser.add_argument("task_name", help="Name of the task to remove")
    remove_parser.add_argument("-u", "--username", required=True, help="Username")
    remove_parser.add_argument("-p", "--password", required=True, help="Password")
    
    # Start scheduler parser
    start_parser = subparsers.add_parser("start", help="Start the scheduler")
    
    args = parser.parse_args()
    
    scheduler = TaskScheduler()
    
    if args.command == "add":
        frequency = ScheduleFrequency.MINUTE if args.frequency == 'minute' else \
                    ScheduleFrequency.HOURLY if args.frequency == 'hourly' else ScheduleFrequency.DAILY
        scheduler.add_task(args.task_name, example_job, frequency, args.username, args.password)
    elif args.command == "remove":
        scheduler.remove_task(args.task_name, args.username, args.password)
    elif args.command == "start":
        scheduler.start()
    else:
        parser.print_help()