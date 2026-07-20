import logging
from typing import Any, Callable, Dict, List, Optional, Union

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.job import Job as APSJob

# Configure module logger
logger = logging.getLogger(__name__)


class TaskScheduler:
    """
    A persistent task scheduler supporting daily, hourly, and minute-level frequencies.

    Features:
    - Add/remove scheduled tasks.
    - Persistent storage via SQLAlchemy + SQLite.
    - Logging of task execution.
    - Support for interval and cron triggers.
    """

    def __init__(self, db_path: str = "scheduler.db", timezone: Optional[str] = None):
        """
        Initialize the scheduler with a SQLAlchemy job store.

        Args:
            db_path: Path to the SQLite database file for persistence.
            timezone: Timezone string (e.g., 'UTC', 'America/New_York').
                      Defaults to system local timezone.

        Raises:
            ValueError: If db_path is empty.
        """
        if not db_path:
            raise ValueError("db_path must be a non-empty string")

        # Use SQLAlchemy job store for persistence
        jobstore = SQLAlchemyJobStore(url=f"sqlite:///{db_path}")

        self._scheduler = BackgroundScheduler(
            jobstores={"default": jobstore},
            timezone=timezone,
            daemon=True,
            job_defaults={
                "coalesce": False,
                "max_instances": 1,
                "misfire_grace_time": 60,
            },
        )

        # Attach execution logging
        self._scheduler.add_listener(self._job_execution_listener, mask=0x0001 | 0x0002 | 0x0004 | 0x0008)

        self._running = False

    @staticmethod
    def _job_execution_listener(event) -> None:
        """Log job execution events."""
        event_codes = {
            0x0001: "EVENT_SCHEDULER_START",
            0x0002: "EVENT_SCHEDULER_SHUTDOWN",
            0x0004: "EVENT_JOB_ADDED",
            0x0008: "EVENT_JOB_REMOVED",
            0x0010: "EVENT_JOB_MODIFIED",
            0x0020: "EVENT_JOB_EXECUTED",
            0x0040: "EVENT_JOB_ERROR",
            0x0080: "EVENT_JOB_MISSED",
            0x0100: "EVENT_JOB_SUBMITTED",
            0x0200: "EVENT_JOB_MAX_INSTANCES",
        }
        event_name = event_codes.get(event.code, f"UNKNOWN ({event.code})")

        if event.code == 0x0040:  # EVENT_JOB_ERROR
            logger.error(
                "Job %s raised an exception: %s",
                event.job_id,
                event.exception,
            )
        elif event.code == 0x0020:  # EVENT_JOB_EXECUTED
            logger.info("Job %s executed successfully (return value: %s)", event.job_id, event.retval)
        else:
            logger.debug("Scheduler event: %s - job_id: %s", event_name, event.job_id)

    def start(self) -> None:
        """Start the scheduler (call after all jobs are added)."""
        if not self._running:
            self._scheduler.start()
            self._running = True
            logger.info("Scheduler started.")

    def stop(self, wait: bool = True) -> None:
        """
        Shut down the scheduler.

        Args:
            wait: If True, wait for any running jobs to finish.
        """
        if self._running:
            self._scheduler.shutdown(wait=wait)
            self._running = False
            logger.info("Scheduler stopped.")

    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.stop()

    def add_job(
        self,
        func: Callable,
        trigger_type: str,
        trigger_args: Union[str, Dict[str, Any]],
        job_id: Optional[str] = None,
        name: Optional[str] = None,
        args: Optional[tuple] = None,
        kwargs: Optional[Dict[str, Any]] = None,
    ) -> APSJob:
        """
        Add a new scheduled job.

        Args:
            func: Callable to execute.
            trigger_type: 'interval' or 'cron'.
                - For 'interval', trigger_args is a dict with keys like
                  'minutes', 'hours', 'days'. Example: {'minutes': 5}.
                - For 'cron', trigger_args is a cron expression string
                  (e.g., '0 9 * * *' for daily at 9 AM) or a dict of
                  cron fields (e.g., {'hour': 9, 'minute': 0}).
            trigger_args: Arguments for the trigger (see above).
            job_id: Unique identifier for the job. If None, generated automatically.
            name: Human-readable name for the job.
            args: Positional arguments passed to func when executed.
            kwargs: Keyword arguments passed to func when executed.

        Returns:
            The created APScheduler Job object.

        Raises:
            ValueError: If trigger_type is invalid or trigger_args malformed.
            TypeError: If func is not callable.
            KeyError: If job_id already exists.
        """
        if not callable(func):
            raise TypeError("func must be callable")

        trigger_type = trigger_type.lower()
        if trigger_type not in ("interval", "cron"):
            raise ValueError("trigger_type must be 'interval' or 'cron'")

        if trigger_type == "interval":
            if not isinstance(trigger_args, dict):
                raise ValueError("trigger_args must be a dict for interval triggers")
            trigger = IntervalTrigger(**trigger_args)
        else:  # cron
            if isinstance(trigger_args, str):
                trigger = CronTrigger.from_crontab(trigger_args)
            elif isinstance(trigger_args, dict):
                trigger = CronTrigger(**trigger_args)
            else:
                raise ValueError("trigger_args must be a string (cron expression) or dict for cron triggers")

        # Validate job_id uniqueness (APScheduler will raise on duplicate)
        if job_id and self._scheduler.get_job(job_id):
            raise KeyError(f"Job with ID '{job_id}' already exists")

        job = self._scheduler.add_job(
            func=func,
            trigger=trigger,
            id=job_id,
            name=name or (job_id or func.__name__),
            args=args or (),
            kwargs=kwargs or {},
        )

        logger.info("Job added: id=%s, name=%s, trigger=%s", job.id, job.name, job.trigger)
        return job

    def remove_job(self, job_id: str) -> None:
        """
        Remove a scheduled job by its ID.

        Args:
            job_id: The identifier of the job to remove.

        Raises:
            KeyError: If the job ID does not exist.
        """
        if not self._scheduler.get_job(job_id):
            raise KeyError(f"Job with ID '{job_id}' not found")
        self._scheduler.remove_job(job_id)
        logger.info("Job removed: id=%s", job_id)

    def list_jobs(self) -> List[Dict[str, Any]]:
        """
        Return a list of all scheduled jobs with their details.

        Returns:
            A list of dictionaries, each containing job metadata.
        """
        jobs = self._scheduler.get_jobs()
        return [
            {
                "id": job.id,
                "name": job.name,
                "next_run_time": str(job.next_run_time) if job.next_run_time else None,
                "trigger": str(job.trigger),
            }
            for job in jobs
        ]

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Get details of a specific job.

        Args:
            job_id: The identifier of the job.

        Returns:
            A dictionary with job details, or None if not found.
        """
        job = self._scheduler.get_job(job_id)
        if not job:
            return None
        return {
            "id": job.id,
            "name": job.name,
            "next_run_time": str(job.next_run_time) if job.next_run_time else None,
            "trigger": str(job.trigger),
        }

    def pause_job(self, job_id: str) -> None:
        """
        Pause a job (stop it from executing until resumed).

        Args:
            job_id: The identifier of the job to pause.

        Raises:
            KeyError: If the job ID does not exist.
        """
        job = self._scheduler.get_job(job_id)
        if not job:
            raise KeyError(f"Job with ID '{job_id}' not found")
        job.pause()
        logger.info("Job paused: id=%s", job_id)

    def resume_job(self, job_id: str) -> None:
        """
        Resume a paused job.

        Args:
            job_id: The identifier of the job to resume.

        Raises:
            KeyError: If the job ID does not exist.
        """
        job = self._scheduler.get_job(job_id)
        if not job:
            raise KeyError(f"Job with ID '{job_id}' not found")
        job.resume()
        logger.info("Job resumed: id=%s", job_id)