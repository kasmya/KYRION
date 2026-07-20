"""Distributed Task Queue implementation using RQ.

Features
--------
* Add tasks to a Redis‑backed queue.
* Parallel processing via RQ workers.
* Per‑task status tracking (queued, started, finished, failed, cancelled).
* Automatic retry of failed tasks with exponential back‑off.
* Security‑aware Redis connection (TLS, password from environment).

Only the Python standard library and well‑known packages (redis, rq) are used.
"""

from __future__ import annotations

import os
import json
import sys
import time
import logging
import argparse
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, Optional, Tuple

from redis import Redis, ConnectionPool
from rq import Queue, Worker, Retry, Connection
from rq.job import Job, JobStatus
from rq.exceptions import NoSuchJobError, InvalidJobOperationError

# --------------------------------------------------------------------------- #
# Configuration & Logging
# --------------------------------------------------------------------------- #

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger(__name__)

REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
REDIS_TLS: bool = os.getenv("REDIS_TLS", "false").lower() in ("1", "true", "yes")
REDIS_PASSWORD: Optional[str] = os.getenv("REDIS_PASSWORD")  # may be None


def _create_redis_connection() -> Redis:
    """Create a Redis client respecting security‑related environment variables."""
    ssl_params = {"ssl": REDIS_TLS} if REDIS_TLS else {}
    pool = ConnectionPool.from_url(
        REDIS_URL,
        password=REDIS_PASSWORD,
        decode_responses=False,
        **ssl_params,
    )
    return Redis(connection_pool=pool)


# --------------------------------------------------------------------------- #
# Exceptions
# --------------------------------------------------------------------------- #

class TaskQueueError(Exception):
    """Base exception for TaskQueue related errors."""


class TaskNotFoundError(TaskQueueError):
    """Raised when a job ID does not correspond to any known job."""


class TaskRetryError(TaskQueueError):
    """Raised when a task cannot be retried."""


# --------------------------------------------------------------------------- #
# Core implementation
# --------------------------------------------------------------------------- #

class TaskQueue:
    """High‑level wrapper around RQ for enqueuing and tracking tasks."""

    def __init__(self, queue_name: str = "default", default_timeout: int = 300):
        """
        Initialise the task queue.

        Parameters
        ----------
        queue_name: str
            Name of the RQ queue.
        default_timeout: int
            Default job execution timeout in seconds.
        """
        self.redis = _create_redis_connection()
        self.queue = Queue(name=queue_name, connection=self.redis, default_timeout=default_timeout)
        log.debug("TaskQueue initialised with queue=%s", queue_name)

    # ------------------------------------------------------------------- #
    # Task Submission
    # ------------------------------------------------------------------- #

    def add_task(
        self,
        func: Callable[..., Any],
        *args: Any,
        retry_attempts: int = 3,
        retry_backoff: bool = True,
        **kwargs: Any,
    ) -> str:
        """
        Enqueue a callable for asynchronous execution.

        Parameters
        ----------
        func: Callable
            The function to execute.
        args, kwargs: Any
            Arguments passed to ``func``.
        retry_attempts: int
            Number of automatic retries after failure.
        retry_backoff: bool
            If True, uses exponential back‑off between attempts.

        Returns
        -------
        str
            The RQ job identifier.
        """
        retry = Retry(max=retry_attempts, interval=[2 ** i for i in range(retry_attempts)] if retry_backoff else [0] * retry_attempts)

        try:
            job: Job = self.queue.enqueue(func, args=args, kwargs=kwargs, retry=retry)
            log.info("Enqueued job %s for function %s", job.id, func.__name__)
            return job.id
        except Exception as exc:  # pragma: no cover
            log.exception("Failed to enqueue task")
            raise TaskQueueError(f"Unable to enqueue task: {exc}") from exc

    # ------------------------------------------------------------------- #
    # Status Retrieval
    # ------------------------------------------------------------------- #

    def get_status(self, job_id: str) -> Dict[str, Any]:
        """
        Retrieve the status and meta‑information of a job.

        Parameters
        ----------
        job_id: str
            Identifier returned by :meth:`add_task`.

        Returns
        -------
        dict
            Dictionary containing ``status``, ``result`` (if available), and timestamps.
        """
        try:
            job: Job = Job.fetch(job_id, connection=self.redis)
        except NoSuchJobError as exc:
            log.warning("Job %s not found", job_id)
            raise TaskNotFoundError(f"Job {job_id} does not exist") from exc

        info: Dict[str, Any] = {
            "id": job.id,
            "status": job.get_status(),
            "enqueued_at": self._iso(job.enqueued_at),
            "started_at": self._iso(job.started_at),
            "ended_at": self._iso(job.ended_at),
            "result": None,
        }

        if job.is_finished:
            info["result"] = job.result
        elif job.is_failed:
            info["error_message"] = str(job.exc_info)

        return info

    @staticmethod
    def _iso(dt: Optional[datetime]) -> Optional[str]:
        """Return ISO formatted datetime or ``None``."""
        return dt.isoformat() if dt else None

    # ------------------------------------------------------------------- #
    # Retry handling
    # ------------------------------------------------------------------- #

    def retry_failed(self, job_id: str) -> str:
        """
        Re‑queue a failed job.

        Parameters
        ----------
        job_id: str
            Identifier of the failed job.

        Returns
        -------
        str
            New job identifier for the retried job.
        """
        try:
            job: Job = Job.fetch(job_id, connection=self.redis)
        except NoSuchJobError as exc:
            raise TaskNotFoundError(f"Job {job_id} not found") from exc

        if not job.is_failed:
            raise TaskRetryError(f"Job {job_id} is not in a failed state (current: {job.get_status()})")

        # Preserve original args/kwargs for retry
        func = job.func
        args = job.args
        kwargs = job.kwargs
        retry = job.retries + 1 if job.retries is not None else 1

        new_job: Job = self.queue.enqueue(
            func,
            args=args,
            kwargs=kwargs,
            retry=Retry(max=retry, interval=[2 ** i for i in range(retry)]),
        )
        log.info("Retried job %s as new job %s", job_id, new_job.id)
        return new_job.id

    # ------------------------------------------------------------------- #
    # Administrative helpers
    # ------------------------------------------------------------------- #

    def cancel(self, job_id: str) -> None:
        """Cancel a queued or running job."""
        try:
            job: Job = Job.fetch(job_id, connection=self.redis)
            job.cancel()
            log.info("Cancelled job %s", job_id)
        except NoSuchJobError as exc:
            raise TaskNotFoundError(f"Job {job_id} not found") from exc
        except InvalidJobOperationError as exc:
            raise TaskQueue