import logging
import sys
from datetime import datetime
from typing import Callable, Dict, Optional, Union

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR
from apscheduler.executors.pool import ThreadPoolExecutor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class TaskScheduler:
    """
    A persistent, logging-enabled task scheduler supporting daily, hourly,
    and minute-level task execution using APScheduler.

    Attributes:
        scheduler (BackgroundScheduler): The underlying APScheduler instance.
        job_store (SQLAlchemyJobStore): Persistent job store (SQLite by default).
        _tasks (dict): In-memory map of task IDs to job references for fast lookup.
    """

    def __init__(self, db_url: str = "sqlite:///tasks.db"):
        """
        Initialize the scheduler with persistent storage.

        Args:
            db_url: Database connection URL for APScheduler's job store.
                    Defaults to 'sqlite:///tasks.db'.
        """
        self._tasks: Dict[str, str] = {}  # task_name -> job_id

        # Configure job store for persistence
        jobstores = {
            'default': SQLAlchemyJobStore(url=db_url)
        }

        # Configure executors (single thread for safety)
        executors = {
            'default': ThreadPoolExecutor(1)
        }

        # Create the scheduler
        self.scheduler = BackgroundScheduler(
            jobstores=jobstores,
            executors=executors,
            timezone='UTC'  # Use UTC to avoid timezone issues
        )

        # Add listeners for logging job execution
        self.scheduler.add_listener(
            self._job_executed_listener,
            EVENT_JOB_EXECUTED | EVENT_JOB_ERROR
        )

        logger.info("TaskScheduler initialized with persistent storage at %s", db_url)

    def _job_executed_listener(self, event):
        """Log job execution results."""
        if event.exception:
            logger.error(
                "Job %s failed: %s", event.job_id, str(event.exception)
            )
        else:
            logger.info("Job %s executed successfully", event.job_id)

    def _validate_callable(self, func: Callable) -> None:
        """
        Validate that the given callable is safe to schedule.
        Security: Only allow user-defined functions (not built-in or dangerous).

        Args:
            func: The callable to validate.

        Raises:
            ValueError: If func is a built-in or not callable.
        """
        if not callable(func):
            raise ValueError("Provided function is not callable.")
        # Avoid scheduling dangerous built-ins
        if getattr(func, '__module__', '').startswith('builtins'):
            raise ValueError("Built-in functions are not allowed for security.")

    def add_task(
        self,
        task_name: str,
        func: Callable,
        trigger: str,
        **trigger_args
    ) -> None:
        """
        Schedule a new task.

        Args:
            task_name: Unique identifier for the task.
            func: Callable to execute (must be a user-defined function).
            trigger: One of "daily", "hourly", "minute", or "interval".
            **trigger_args: Additional trigger arguments.
                - For "daily": hour (0-23, default 9), minute (0-59, default 0)
                - For "hourly": minute (0-59, default 0)
                - For "minute": (no extra args)
                - For "interval": seconds (required)

        Raises:
            ValueError: If task_name already exists, trigger is unknown, or args invalid.
        """
        if task_name in self._tasks:
            raise ValueError(f"Task '{task_name}' already exists.")

        self._validate_callable(func)

        # Build the appropriate trigger
        if trigger == "daily":
            hour = trigger_args.get("hour", 9)
            minute = trigger_args.get("minute", 0)
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                raise ValueError("Invalid hour/minute for daily trigger.")
            aps_trigger = CronTrigger(hour=hour, minute=minute)
        elif trigger == "hourly":
            minute = trigger_args.get("minute", 0)
            if not (0 <= minute <= 59):
                raise ValueError("Invalid minute for hourly trigger.")
            aps_trigger = CronTrigger(minute=minute)
        elif trigger == "minute":
            aps_trigger = IntervalTrigger(minutes=1)
        elif trigger == "interval":
            seconds = trigger_args.get("seconds")
            if seconds is None or seconds <= 0:
                raise ValueError("Interval trigger requires positive 'seconds' argument.")
            aps_trigger = IntervalTrigger(seconds=seconds)
        else:
            raise ValueError(f"Unknown trigger type: {trigger}. Use 'daily', 'hourly', 'minute', or 'interval'.")

        # Add job to scheduler
        job = self.scheduler.add_job(
            func,
            trigger=aps_trigger,
            id=task_name,  # Use task_name as job ID for easy removal
            name=task_name,
            replace_existing=False  # Fail if duplicate ID (since we check above)
        )

        self._tasks[task_name] = job.id
        logger.info("Task '%s' added with trigger '%s'", task_name, trigger)

    def remove_task(self, task_name: str) -> None:
        """
        Remove a scheduled task.

        Args:
            task_name: Identifier of the task to remove.

        Raises:
            ValueError: If task_name does not exist.
        """
        if task_name not in self._tasks:
            raise ValueError(f"Task '{task_name}' not found.")

        self.scheduler.remove_job(task_name)
        del self._tasks[task_name]
        logger.info("Task '%s' removed", task_name)

    def start(self) -> None:
        """Start the scheduler. Idempotent if already started."""
        if not self.scheduler.running:
            self.scheduler.start()
            logger.info("Scheduler started.")
        else:
            logger.warning("Scheduler is already running.")

    def shutdown(self, wait: bool = True) -> None:
        """
        Gracefully shut down the scheduler. Persisted tasks will remain.

        Args:
            wait: If True, wait for running jobs to finish.
        """
        self.scheduler.shutdown(wait=wait)
        self._tasks.clear()
        logger.info("Scheduler shut down.")

    def get_tasks(self) -> Dict[str, str]:
        """
        Return a dictionary of task names to their job IDs.

        Returns:
            Dict mapping task names to job IDs.
        """
        return self._tasks.copy()

    def __enter__(self):
        """Context manager support."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager cleanup."""
        self.shutdown()


# Example usage (if executed directly)
if __name__ == "__main__":
    def my_task():
        """Example task function."""
        print(f"Task executed at {datetime.utcnow().isoformat()}")

    scheduler = TaskScheduler()

    try:
        # Add tasks with different frequencies
        scheduler.add_task("daily_task", my_task, "daily", hour=10, minute=30)
        scheduler.add_task("hourly_task", my_task, "hourly", minute=15)
        scheduler.add_task("minute_task", my_task, "minute")
        scheduler.add_task("interval_task", my_task, "interval", seconds=30)

        # Start and let it run for a bit (in a real scenario, you'd keep the process alive)
        scheduler.start()

        import time
        time.sleep(10)

        # Remove one task
        scheduler.remove_task("interval_task")

        print("Current tasks:", scheduler.get_tasks())

        time.sleep(5)

    except Exception as e:
        logger.error("Error in example: %s", e)
    finally:
        scheduler.shutdown()