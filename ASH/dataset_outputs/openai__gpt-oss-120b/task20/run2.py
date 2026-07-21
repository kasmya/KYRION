"""
distributed_task_queue.py

A lightweight distributed task queue built on top of Redis. It provides:

* ``enqueue_task`` – Add a new task to the queue.
* ``start_worker`` – Launch one or more worker threads/processes that consume tasks.
* ``get_task_status`` – Retrieve the current status of a task.
* Automatic retry of failed tasks up to a configurable limit.

Only the Python standard library and the widely‑used ``redis`` package are required.
"""

from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, asdict
from typing import Any, Callable, Dict, List, Optional

import redis

# --------------------------------------------------------------------------- #
# Configuration & Logging
# --------------------------------------------------------------------------- #

DEFAULT_REDIS_HOST = "localhost"
DEFAULT_REDIS_PORT = 6379
DEFAULT_REDIS_DB = 0

_TASK_QUEUE_KEY = "dtq:queue"
_TASK_STATUS_HASH = "dtq:status"
_TASK_DATA_HASH = "dtq:data"

_logger = logging.getLogger(__name__)
_logger.setLevel(logging.INFO)
_handler = logging.StreamHandler()
_handler.setFormatter(
    logging.Formatter("%(asctime)s %(levelname)s %(name)s - %(message)s")
)
_logger.addHandler(_handler)


# --------------------------------------------------------------------------- #
# Data structures
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class Task:
    """Immutable representation of a task to be processed."""
    id: str
    name: str
    args: List[Any]
    kwargs: Dict[str, Any]
    max_retries: int
    created_at: float

    def to_json(self) -> str:
        """Serialize the task to a JSON string."""
        return json.dumps(asdict(self), default=str)

    @staticmethod
    def from_json(data: str) -> "Task":
        """Deserialize a JSON string back into a ``Task``."""
        payload = json.loads(data)
        return Task(
            id=payload["id"],
            name=payload["name"],
            args=payload["args"],
            kwargs=payload["kwargs"],
            max_retries=payload["max_retries"],
            created_at=payload["created_at"],
        )


# --------------------------------------------------------------------------- #
# Core queue implementation
# --------------------------------------------------------------------------- #

class DistributedTaskQueue:
    """
    Core class that encapsulates all queue operations.

    Parameters
    ----------
    redis_url : str, optional
        Redis connection URL. If omitted, defaults to localhost:6379/0.
    """

    def __init__(self, redis_url: Optional[str] = None) -> None:
        self._redis = redis.Redis.from_url(redis_url or f"redis://{DEFAULT_REDIS_HOST}:{DEFAULT_REDIS_PORT}/{DEFAULT_REDIS_DB}")
        try:
            # Simple health‑check
            self._redis.ping()
        except redis.ConnectionError as exc:
            _logger.error("Unable to connect to Redis: %s", exc)
            raise RuntimeError("Redis connection failed") from exc

    # ------------------------------------------------------------------- #
    # Public API
    # ------------------------------------------------------------------- #

    def enqueue_task(
        self,
        name: str,
        args: Optional[List[Any]] = None,
        kwargs: Optional[Dict[str, Any]] = None,
        max_retries: int = 3,
    ) -> str:
        """
        Add a new task to the queue.

        Parameters
        ----------
        name : str
            Identifier of the task (must correspond to a registered handler).
        args : list, optional
            Positional arguments for the task.
        kwargs : dict, optional
            Keyword arguments for the task.
        max_retries : int, default 3
            Maximum number of retry attempts after failure.

        Returns
        -------
        str
            The unique task identifier.

        Raises
        ------
        ValueError
            If ``name`` is empty or ``max_retries`` is negative.
        RuntimeError
            If the task cannot be stored in Redis.
        """
        if not name:
            raise ValueError("Task name must be a non‑empty string")
        if max_retries < 0:
            raise ValueError("max_retries must be non‑negative")

        task = Task(
            id=str(uuid.uuid4()),
            name=name,
            args=args or [],
            kwargs=kwargs or {},
            max_retries=max_retries,
            created_at=time.time(),
        )
        try:
            pipe = self._redis.pipeline()
            pipe.rpush(_TASK_QUEUE_KEY, task.to_json())
            pipe.hset(_TASK_STATUS_HASH, task.id, "queued")
            pipe.hset(_TASK_DATA_HASH, task.id, json.dumps({"attempts": 0}))
            pipe.execute()
            _logger.info("Enqueued task %s (id=%s)", name, task.id)
            return task.id
        except redis.RedisError as exc:
            _logger.exception("Failed to enqueue task %s", name)
            raise RuntimeError("Failed to enqueue task") from exc

    def get_task_status(self, task_id: str) -> Optional[str]:
        """
        Retrieve the current status of a task.

        Parameters
        ----------
        task_id : str
            Unique identifier of the task.

        Returns
        -------
        str or None
            One of ``queued``, ``in_progress``, ``succeeded``, ``failed``.
            Returns ``None`` if the task identifier does not exist.
        """
        try:
            status = self._redis.hget(_TASK_STATUS_HASH, task_id)
            return status.decode() if status else None
        except redis.RedisError as exc:
            _logger.error("Redis error while fetching status for %s: %s", task_id, exc)
            return None

    def _set_status(self, task_id: str, status: str) -> None:
        """Internal helper to atomically set a task's status."""
        try:
            self._redis.hset(_TASK_STATUS_HASH, task_id, status)
        except redis.RedisError as exc:
            _logger.error("Failed to set status '%s' for task %s: %s", status, task_id, exc)

    def _increment_attempts(self, task_id: str) -> int:
        """Increment the attempt counter for a task and return the new count."""
        try:
            data = self._redis.hget(_TASK_DATA_HASH, task_id)
            if not data:
                attempts = 0
            else:
                attempts = json.loads(data).get("attempts", 0) + 1
            self._redis.hset(_TASK_DATA_HASH, task_id, json.dumps({"attempts": attempts}))
            return attempts
        except redis.RedisError as exc:
            _logger.error("Failed to increment attempts for task %s: %s", task_id, exc)
            return 0

    # ------------------------------------------------------------------- #
    # Worker management
    # ------------------------------------------------------------------- #

    def start_worker(
        self,
        handlers: Dict[str, Callable[..., Any]],
        num_threads: int = 1,
        poll_interval: float = 1.0,
        shutdown_event: Optional[threading.Event] = None,
    ) -> None:
        """
        Launch a pool of worker threads that continuously pull tasks from Redis.

        Parameters
        ----------
        handlers : dict
            Mapping from task name to a callable that implements the work.
        num_threads : int, default 1
            Number of concurrent worker threads.
        poll_interval : float, default 1.0
            Seconds to wait before re‑checking the queue when it is empty.
        shutdown_event : threading.Event, optional
            If provided, workers will exit when the event is set.

        Raises
        ------
        ValueError
            If ``num_threads`` is not positive or ``handlers`` is empty.
        """
        if not handlers:
            raise ValueError("At least one task handler must be provided")
        if num_threads <= 0:
            raise ValueError("num_threads must be a positive integer")

        _logger.info("Starting %d worker thread(s)", num_threads)

        def worker_loop() -> None:
            while not (shutdown_event and shutdown_event.is_set()):
                try:
                    raw = self._redis.blpop(_TASK_QUEUE_KEY, timeout=int(poll_interval))
                    if not raw:
                        continue  # timeout, loop again
                    _, payload = raw
                    task = Task.from_json(payload.decode())
                except (redis.RedisError, json.JSONDecodeError) as exc:
                    _logger.exception("Error retrieving task from queue: %s", exc)
                    time.sleep(poll_interval)
                    continue

                self._process_task(task, handlers)

        threads: List[threading.Thread] = []
        for _ in range(num_threads):
            t = threading.Thread(target=worker_loop, daemon=True)
            t.start()
            threads.append(t)

        # If a shutdown_event is supplied, wait for it; otherwise keep the main thread alive.
        if shutdown_event:
            shutdown_event.wait()
            _logger.info("Shutdown signal received; waiting for workers to finish")
            for t in threads:
                t.join()
        else:
            try:
                while True:
                    time.sleep(3600)  # keep alive indefinitely
            except KeyboardInterrupt:
                _logger.info("KeyboardInterrupt received; exiting workers")
                for t in threads:
                    t.join()

    def _process_task(
        self,
        task: Task,
        handlers: Dict[str, Callable[..., Any]],
    ) -> None:
        """
        Execute a single task, handling retries and status updates.

        Parameters
        ----------
        task : Task
            The task to be processed.
        handlers : dict
            Mapping from task name to callables.

        This method catches all exceptions raised by the handler to ensure the
        worker thread does not crash.
        """
        if task.name not in handlers:
            _logger.error("No handler registered for task name '%s'", task.name)
            self._set_status(task.id, "failed")
            return

        self._set_status(task.id, "in_progress")
        attempts = self._increment_attempts(task.id)

        try:
            result = handlers[task.name](*task.args, **task.kwargs)
            self._set_status(task.id, "succeeded")
            _logger.info("Task %s succeeded (id=%s, attempts=%d)", task.name, task.id, attempts)
        except Exception as exc:  # pylint: disable=broad-except
            _logger.exception("Task %s failed on attempt %d: %s", task.name, attempts, exc)
            if attempts <= task.max_retries:
                # Re‑queue task for another attempt
                try:
                    self._redis.rpush(_TASK_QUEUE_KEY, task.to_json())
                    self._set_status(task.id, "queued")
                    _logger.info("Re‑queued task %s (id=%s) for retry %d", task.name, task.id, attempts)
                except redis.RedisError as re:
                    _logger.error("Failed to re‑queue task %s (id=%s): %s", task.name, task.id, re)
                    self._set_status(task.id, "failed")
            else:
                self._set_status(task.id, "failed")
                _logger.error("Task %s exhausted retries (id=%s)", task.name, task.id)


# --------------------------------------------------------------------------- #
# Convenience module‑level functions
# --------------------------------------------------------------------------- #

_global_queue = DistributedTaskQueue()


def enqueue_task(
    name: str,
    args: Optional[List[Any]] = None,
    kwargs: Optional[Dict[str, Any]] = None,
    max_retries: int = 3,
) -> str:
    """
    Convenience wrapper around :meth:`DistributedTaskQueue.enqueue_task`.

    See the method documentation for parameter details.
    """
    return _global_queue.enqueue_task(name, args, kwargs, max_retries)


def get_task_status(task_id: str) -> Optional[str]:
    """
    Convenience wrapper around :meth:`DistributedTaskQueue.get_task_status`.
    """
    return _global_queue.get_task_status(task_id)


def start_worker(
    handlers: Dict[str, Callable[..., Any]],
    num_threads: int = 1,
    poll_interval: float = 1.0,
    shutdown_event: Optional[threading.Event] = None,
) -> None:
    """
    Convenience wrapper around :meth:`DistributedTaskQueue.start_worker`.
    """
    _global_queue.start_worker(handlers, num_threads, poll_interval, shutdown_event)