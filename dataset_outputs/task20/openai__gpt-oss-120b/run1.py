"""
Distributed task queue implementation using RQ (Redis Queue).

Features:
- Add tasks to a queue with optional arguments and retry count.
- Parallel processing via separate worker processes.
- Task status tracking (queued, started, finished, failed).
- Automatic retry of failed tasks with exponential back‑off.
- Secure connection to Redis using environment variables.

Dependencies (install with pip):
    pip install rq redis
"""

from __future__ import annotations

import os
import sys
import time
import enum
import json
import logging
from pathlib import Path
from typing import Any, Callable, Tuple, Dict, Optional

from redis import Redis, ConnectionError as RedisConnectionError
from rq import Queue, Worker, Retry, get_current_job
from rq.job import Job, JobStatus
from rq.exceptions import NoSuchJobError

# --------------------------------------------------------------------------- #
# Configuration and Logging
# --------------------------------------------------------------------------- #

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

LOGGER = logging.getLogger(__name__)

def _load_env() -> Dict[str, str]:
    """
    Load required Redis configuration from environment variables.
    Raises:
        EnvironmentError: If a required variable is missing.
    """
    required = ("REDIS_HOST", "REDIS_PORT", "REDIS_DB")
    missing = [var for var in required if var not in os.environ]
    if missing:
        raise EnvironmentError(f"Missing required env vars: {', '.join(missing)}")
    return {
        "host": os.environ["REDIS_HOST"],
        "port": int(os.environ["REDIS_PORT"]),
        "db": int(os.environ["REDIS_DB"]),
        "password": os.environ.get("REDIS_PASSWORD"),
    }

def get_redis_connection() -> Redis:
    """
    Create a Redis client using safe defaults and environment‑derived settings.
    Returns:
        Redis: Configured Redis client.
    Raises:
        RedisConnectionError: If connection to Redis fails.
    """
    cfg = _load_env()
    try:
        client = Redis(
            host=cfg["host"],
            port=cfg["port"],
            db=cfg["db"],
            password=cfg["password"],
            socket_timeout=5,
            health_check_interval=30,
        )
        # Test connection early
        client.ping()
        LOGGER.debug("Connected to Redis at %(host)s:%(port)s db %(db)s", cfg)
        return client
    except RedisConnectionError as exc:
        LOGGER.exception("Unable to connect to Redis")
        raise

# --------------------------------------------------------------------------- #
# Enumerations
# --------------------------------------------------------------------------- #

class TaskStatus(str, enum.Enum):
    """Human‑readable wrapper around RQ's JobStatus."""
    QUEUED = JobStatus.QUEUED
    STARTED = JobStatus.STARTED
    FINISHED = JobStatus.FINISHED
    FAILED = JobStatus.FAILED
    CANCELLED = JobStatus.CANCELED
    DEFERRED = JobStatus.DEFERRED

# --------------------------------------------------------------------------- #
# Queue Wrapper
# --------------------------------------------------------------------------- #

class TaskQueue:
    """
    High‑level interface encapsulating an RQ Queue.
    """

    def __init__(self, name: str = "default") -> None:
        """
        Initialise the queue with a shared Redis connection.
        Args:
            name: Queue name; workers can listen to multiple queues.
        """
        self._redis = get_redis_connection()
        self._queue = Queue(name=name, connection=self._redis)
        LOGGER.info("TaskQueue '%s' initialised.", name)

    def enqueue(
        self,
        func: Callable[..., Any],
        *args: Any,
        retry: int = 3,
        **kwargs: Any,
    ) -> str:
        """
        Enqueue a callable for asynchronous execution.

        Args:
            func: The function to execute.
            *args: Positional arguments for the function.
            retry: Number of retry attempts on failure.
            **kwargs: Keyword arguments for the function.

        Returns:
            str: The job identifier (UUID).

        Raises:
            Exception: Propagates errors during job creation.
        """
        try:
            job: Job = self._queue.enqueue(
                func,
                args=args,
                kwargs=kwargs,
                retry=Retry(max=retry, interval=[10, 30, 60]),  # exponential back‑off
                result_ttl=86400,   # keep result for 1 day
                failure_ttl=86400, # keep failure info for 1 day
            )
            LOGGER.info("Enqueued job %s for function %s", job.id, func.__name__)
            return job.id
        except Exception as exc:
            LOGGER.exception("Failed to enqueue job")
            raise

    def get_status(self, job_id: str) -> Tuple[TaskStatus, Optional[Any]]:
        """
        Retrieve the current status and result (if finished) of a job.

        Args:
            job_id: Identifier of the job.

        Returns:
            (TaskStatus, result|None): Status enum and result if available.

        Raises:
            NoSuchJobError: If the job_id does not exist.
        """
        try:
            job = Job.fetch(job_id, connection=self._redis)
            status = TaskStatus(job.get_status())
            result = job.result if status is TaskStatus.FINISHED else None
            LOGGER.debug("Job %s status: %s", job_id, status)
            return status, result
        except NoSuchJobError:
            LOGGER.error("Job %s not found", job_id)
            raise
        except Exception:
            LOGGER.exception("Error retrieving status for job %s", job_id)
            raise

    def requeue_failed(self, job_id: str) -> str:
        """
        Immediately re‑queue a failed job for another attempt.

        Args:
            job_id: Identifier of the failed job.

        Returns:
            str: New job identifier.

        Raises:
            NoSuchJobError: If the job does not exist.
            ValueError: If the job is not in a FAILED state.
        """
        job = Job.fetch(job_id, connection=self._redis)
        if job.get_status() != JobStatus.FAILED:
            raise ValueError(f"Job {job_id} is not in FAILED state.")
        # Clone the job with same arguments and retry count
        new_job = job.requeue()
        LOGGER.info("Re‑queued failed job %s as new job %s", job_id, new_job.id)
        return new_job.id

# --------------------------------------------------------------------------- #
# Example Task Functions
# --------------------------------------------------------------------------- #

def example_task(x: int, y: int) -> int:
    """
    Simple arithmetic task that may raise an exception for demonstration.

    Args:
        x: First operand.
        y: Second operand.

    Returns:
        int: Sum of x and y.

    Raises:
        ValueError: If sum exceeds 100 (simulated failure).
    """
    job = get_current_job()
    if job:
        # Attach meta data for debugging (optional)
        job.meta["attempt"] = job.meta.get("attempt", 0) + 1
        job.save_meta()
    result = x + y
    if result > 100:
        raise ValueError(f"Result {result} exceeds allowed maximum.")
    return result

def io_bound_task(duration: float) -> str:
    """
    Simulated I/O‑bound task that sleeps.

    Args:
        duration: Seconds to sleep.

    Returns:
        str: Confirmation message.
    """
    time.sleep(duration)
    return f"Slept for {duration