"""
distributed_queue.py

A minimal distributed task queue built on top of Redis Queue (RQ).
Features:
- Enqueue tasks with arguments and optional retry policy
- Parallel task processing using RQ workers
- Task status tracking (queued, started, finished, failed)
- Automatic retry of failed tasks with exponential back‑off

Only the Python standard library and the well‑known ``rq`` package are used.
"""

from __future__ import annotations

import os
import sys
import time
import logging
import traceback
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, Optional, Tuple, Union

import redis
from rq import Queue, Worker, Retry, get_current_job
from rq.job import Job
from rq.exceptions import NoSuchJobError, InvalidJobOperation, QueuesError

# --------------------------------------------------------------------------- #
# Configuration (use environment variables for credentials – security best practice)
# --------------------------------------------------------------------------- #
REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
QUEUE_NAME: str = os.getenv("RQ_QUEUE_NAME", "default")
MAX_RETRIES: int = int(os.getenv("RQ_MAX_RETRIES", "3"))
RETRY_BACKOFF_SECONDS: int = int(os.getenv("RQ_RETRY_BACKOFF_SECONDS", "5"))
WORKER_TIMEOUT: int = int(os.getenv("RQ_WORKER_TIMEOUT", "180"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Helper data structures
# --------------------------------------------------------------------------- #
@dataclass
class TaskResult:
    """Simple container for a task's outcome."""
    job_id: str
    status: str
    result: Optional[Any] = None
    error: Optional[str] = None
    enqueued_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


# --------------------------------------------------------------------------- #
# Core Queue manager
# --------------------------------------------------------------------------- #
class TaskQueue:
    """
    High‑level wrapper around an RQ queue providing safe task enqueuing,
    status queries and configurable retry behaviour.
    """

    def __init__(self, redis_url: str = REDIS_URL, queue_name: str = QUEUE_NAME) -> None:
        """
        Initialise Redis connection and the underlying RQ queue.

        Raises
        ------
        redis.ConnectionError
            If the Redis server cannot be reached.
        """
        try:
            self._redis = redis.from_url(redis_url)
            # Quick health‑check
            self._redis.ping()
        except redis.ConnectionError as exc:
            logger.exception("Unable to connect to Redis at %s", redis_url)
            raise

        self._queue = Queue(name=queue_name, connection=self._redis, default_timeout=WORKER_TIMEOUT)
        logger.info("TaskQueue initialised on Redis %s, queue '%s'", redis_url, queue_name)

    def enqueue(
        self,
        func: Callable[..., Any],
        args: Optional[Tuple[Any, ...]] = None,
        kwargs: Optional[Dict[str, Any]] = None,
        *,
        retry: Optional[Retry] = None,
        ttl: Optional[int] = None,
    ) -> str:
        """
        Enqueue a callable for asynchronous execution.

        Parameters
        ----------
        func : Callable[..., Any]
            Function to execute.
        args : tuple, optional
            Positional arguments for ``func``.
        kwargs : dict, optional
            Keyword arguments for ``func``.
        retry : rq.Retry, optional
            Retry policy. If ``None`` a default policy based on environment
            variables is used.
        ttl : int, optional
            Time‑to‑live for the job (seconds). ``None`` means keep forever.

        Returns
        -------
        str
            The RQ job identifier.

        Raises
        ------
        InvalidJobOperation
            If the job cannot be enqueued.
        """
        args = args or ()
        kwargs = kwargs or {}

        if retry is None:
            retry = Retry(
                max=self._max_retries(),
                interval=self._retry_backoff_seconds(),
                backoff=True,
            )

        try:
            job: Job = self._queue.enqueue(
                func,
                *args,
                **kwargs,
                retry=retry,
                ttl=ttl,
                result_ttl=self._result_ttl(),
            )
            logger.info("Enqueued job %s for function %s", job.id, func.__name__)
            return job.id
        except Exception as exc:
            logger.exception("Failed to enqueue job for %s", func)
            raise InvalidJobOperation(str(exc)) from exc

    def get_result(self, job_id: str) -> TaskResult:
        """
        Retrieve the current status and result of a job.

        Parameters
        ----------
        job_id : str
            Identifier returned by :meth:`enqueue`.

        Returns
        -------
        TaskResult
            Data class describing the job's state.

        Raises
        ------
        NoSuchJobError
            If the job id is unknown.
        """
        try:
            job = Job.fetch(job_id, connection=self._redis)
        except NoSuchJobError as exc:
            logger.warning("Job %s not found", job_id)
            raise

        result = TaskResult(
            job_id=job.id,
            status=job.get_status(),
            result=job.result if job.is_finished else None,
            error=job.exc_info if job.is_failed else None,
            enqueued_at=job.enqueued_at,
            finished_at=job.finished_at,
        )
        logger.debug("Fetched status for job %s: %s", job_id, result.status)
        return result

    def cancel(self, job_id: str) -> bool:
        """
        Attempt to cancel a pending job.

        Parameters
        ----------
        job_id : str

        Returns
        -------
        bool
            ``True`` if the job was cancelled, ``False`` otherwise.
        """
        try:
            job = Job.fetch(job_id, connection=self._redis)
            if job.is_queued:
                job.cancel()
                logger.info("Cancelled job %s", job_id)
                return True
        except (NoSuchJobError, InvalidJobOperation):
            pass
        logger.info("Could not cancel job %s (may already be running or finished)", job_id)
        return False

    # ------------------------------------------------------------------- #
    # Internal helpers (focus on configurability and security)
    # ------------------------------------------------------------------- #
    @staticmethod
    def _max_retries() -> int:
        return max(0, MAX_RETRIES)

    @staticmethod
    def _retry_backoff_seconds() -> int:
        return max(1, RETRY_BACKOFF_SECONDS)

    @staticmethod
    def _result_ttl() -> int:
        """Result TTL in seconds (keep results for 1 day by default)."""
        return 86_400

# --------------------------------------------------------------------------- #
# Example task implementation
# --------------------------------------------------------------------------- #
def example_task(x: int, y: int) -> int:
    """
    Simple example task that adds two integers with an artificial failure
    probability to demonstrate retries.

    Parameters
    ----------
    x : int
    y : int

    Returns
    -------
    int
        Sum of ``x`` and ``y``.
    """
    job = get_current_job()
    logger.info("Executing job %s: example_task(%s, %s)", job.id, x, y)

    # Simulate intermittent failure for demonstration
    if (x + y) % 5 == 0:
        logger.warning("Intentional failure in job %s", job.id)
        raise ValueError("Simulated transient error")

    result = x + y
    logger.info("Job %s completed successfully: %s", job.id, result)
    return result

# --------------------------------------------------------------------------- #
# Worker entry‑point
# --------------------------------------------------------------------------- #
def start_worker() -> None:
    """
    Launch a dedicated RQ worker that listens to the configured queue.
    This function is intended to be run in a separate process.
    """
    redis_conn = redis.from_url(REDIS_URL)
    q = Queue(name=QUEUE_NAME, connection=redis_conn)
    worker = Worker([q], connection=redis_conn, name=f"worker-{os.getpid()}")
    logger.info("Starting RQ worker %s for queue '%s'", worker.name, QUEUE_NAME)
    worker.work(with_scheduler=True)


# --------------------------------------------------------------------------- #
# Sample usage (run only when executed as