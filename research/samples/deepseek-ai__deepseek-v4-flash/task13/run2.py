from __future__ import annotations

import atexit
import logging
import sys
from typing import Any, Callable, Dict, Optional, Union

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.triggers.interval import IntervalTrigger

# Configure logging
logger = logging.getLogger("TaskScheduler")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
logger.addHandler(handler)
# Also log to file
file_handler = logging.FileHandler("task_scheduler.log")
file_handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
logger.addHandler(file_handler)


class TaskScheduler:
    """
    A persistent task scheduler that runs jobs at specified intervals.

    Supports daily, hourly, and minute-level scheduling frequencies.
    Uses APScheduler with a SQLAlchemy job store backed by SQLite for persistence.

    Security: Ensure that the callable provided for a job is trusted, as the job
    store serialises callables using pickle (insecure in untrusted environments).
    """

    def __init__(self, db_path: str = "tasks.db") -> None:
        """
        Initialise the scheduler with a SQLite-backed job store.

        Args:
            db_path: Path to the SQLite database file for job persistence.
        """
        self._scheduler: BackgroundScheduler = BackgroundScheduler(
            jobstores={
                "default": SQLAlchemyJobStore(url=f"sqlite:///{db_path}")
            },
            # Prevents orphaned jobs from being executed after scheduler restart
            # without a trigger (requires explicit start time)
            job_defaults={"coalesce": True, "max_instances": 1}
        )
        logger.info("TaskScheduler initialised with database: %s", db_path)

        # Register shutdown handler
        atexit.register(self.shutdown)

    def start(self) -> None:
        """Start the scheduler. Jobs will begin executing according to their triggers."""
        if not self._scheduler.running:
            self._scheduler.start()
            logger.info("Scheduler started.")
        else:
            logger.warning("Scheduler is already running.")

    def stop(self) -> None:
        """Shut down the scheduler gracefully (waits for running jobs to finish)."""
        self.shutdown()

    def shutdown(self) -> None:
        """Shut down the scheduler, waiting for any executing jobs to finish."""
        if self._scheduler.running:
            self._scheduler.shutdown(wait=True)
            logger.info("Scheduler shut down gracefully.")
        else:
            logger.info("Scheduler was not running.")

    def add_task(
        self,
        task_id: str,
        func: Callable[..., Any],
        trigger: Union[str, Dict[str, int]],
        args: Optional[tuple[Any, ...]] = None,
        kwargs: Optional[Dict[str, Any]] = None,
        replace_existing: bool = True,
    ) -> None:
        """
        Add a new scheduled task.

        Args:
            task_id: Unique identifier for the task.
            func: Callable to execute. Must be picklable and safe.
            trigger: Scheduling frequency. Either a string ('daily', 'hourly', 'minute')
                     or a dictionary with keys like 'days', 'hours', 'minutes', 'weeks',
                     'seconds' etc. for a custom IntervalTrigger.
            args: Positional arguments for the callable.
            kwargs: Keyword arguments for the callable.
            replace_existing: If True, replace any existing job with the same ID.

        Raises:
            ValueError: If task_id is empty or trigger is invalid.
            TypeError: If func is not callable.
        """
        if not task_id or not isinstance(task_id, str):
            raise ValueError("task_id must be a non-empty string.")

        if not callable(func):
            raise TypeError("func must be callable.")

        interval_trigger = self._resolve_trigger(trigger)
        if interval_trigger is None:
            raise ValueError(
                "trigger must be 'daily', 'hourly', 'minute', or a dict with interval parameters."
            )

        try:
            self._scheduler.add_job(
                func,
                trigger=interval_trigger,
                args=args or (),
                kwargs=kwargs or {},
                id=task_id,
                replace_existing=replace_existing,
            )
            logger.info("Task '%s' added/updated with trigger: %s", task_id, trigger)
        except Exception as e:
            logger.error("Failed to add task '%s': %s", task_id, e)
            raise

    def remove_task(self, task_id: str) -> None:
        """
        Remove a scheduled task by its ID.

        Args:
            task_id: The unique identifier of the task to remove.

        Raises:
            KeyError: If no task with that ID exists.
        """
        try:
            self._scheduler.remove_job(task_id)
            logger.info("Task '%s' removed successfully.", task_id)
        except KeyError:
            logger.warning("Attempted to remove non-existent task '%s'.", task_id)
            raise
        except Exception as e:
            logger.error("Failed to remove task '%s': %s", task_id, e)
            raise

    def list_tasks(self) -> list[dict[str, Any]]:
        """
        Return a list of all scheduled tasks with their details.

        Returns:
            List of dictionaries containing job id, trigger, and next run time.
        """
        jobs = self._scheduler.get_jobs()
        task_list = []
        for job in jobs:
            task_list.append({
                "id": job.id,
                "trigger": str(job.trigger),
                "next_run_time": str(job.next_run_time) if job.next_run_time else None,
            })
        return task_list

    def _resolve_trigger(
        self, trigger: Union[str, Dict[str, int]]
    ) -> Optional[IntervalTrigger]:
        """
        Convert a user-friendly trigger specification to an APScheduler IntervalTrigger.

        Args:
            trigger: A string or dict.

        Returns:
            An IntervalTrigger instance, or None if invalid.
        """
        if isinstance(trigger, str):
            trigger_lower = trigger.lower()
            if trigger_lower == "daily":
                return IntervalTrigger(days=1)
            elif trigger_lower == "hourly":
                return IntervalTrigger(hours=1)
            elif trigger_lower == "minute":
                return IntervalTrigger(minutes=1)
            else:
                return None
        elif isinstance(trigger, dict):
            # Validate that all values are positive integers
            for key, value in trigger.items():
                if not isinstance(value, int) or value <= 0:
                    raise ValueError(f"Interval parameter '{key}' must be a positive integer.")
            return IntervalTrigger(**trigger)
        else:
            return None


# Example usage (to be executed only when running this module directly)
if __name__ == "__main__":
    import time

    def say_hello(name: str = "World") -> None:
        print(f"Hello, {name}!")
        logger.info("Job executed: say_hello('%s')", name)

    # Create scheduler instance
    scheduler = TaskScheduler(db_path="example_tasks.db")

    # Add tasks
    try:
        scheduler.add_task("hello_every_minute", say_hello, "minute", args=["Minute Friend"])
        scheduler.add_task("hello_hourly", say_hello, "hourly", kwargs={"name": "Hourly Friend"})
        scheduler.add_task("hello_daily", say_hello, {"days": 1}, kwargs={"name": "Daily Friend"})
    except Exception as e:
        logger.error("Could not add tasks: %s", e)
        sys.exit(1)

    # List tasks
    logger.info("Scheduled tasks: %s", scheduler.list_tasks())

    # Start scheduler
    scheduler.start()

    # Let scheduler run for a few seconds to demonstrate
    try:
        time.sleep(10)
    except KeyboardInterrupt:
        pass
    finally:
        # Remove a task as example
        try:
            scheduler.remove_task("hello_daily")
        except KeyError:
            pass

        scheduler.stop()