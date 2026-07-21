"""
Distributed task queue module using Redis as a broker and multiprocessing for workers.

Provides functionality to enqueue tasks, process them in parallel with configurable
worker pools, track task status, and automatically retry failed tasks with exponential
backoff. Uses Redis for persistence and inter-process communication.

Security:
    - Task data is serialized with JSON to avoid code injection.
    - Redis connections use authentication when provided.
    - Input validation on task payloads.
"""

import json
import logging
import multiprocessing
import os
import signal
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

import redis

# Configure module logger
logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

# Redis key prefixes
TASK_PREFIX = "task:"
QUEUE_KEY = "task_queue"
STATUS_PREFIX = "task_status:"
RETRY_PREFIX = "task_retry:"
RESULT_PREFIX = "task_result:"

# Task status constants
STATUS_PENDING = "pending"
STATUS_PROCESSING = "processing"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"
STATUS_RETRYING = "retrying"


class TaskQueue:
    """
    Distributed task queue backed by Redis.

    Enqueues tasks, dispatches them to worker processes, tracks status,
    and handles retries for failed tasks.

    Attributes:
        redis_client: Configured Redis client instance.
        max_retries: Maximum number of retry attempts per task.
        retry_delay: Base delay in seconds for exponential backoff.
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/0",
        max_retries: int = 3,
        retry_delay: float = 1.0,
        redis_password: Optional[str] = None,
        redis_ssl: bool = False,
    ) -> None:
        """
        Initialize the task queue with a Redis connection.

        Args:
            redis_url: Redis connection URL (e.g., 'redis://host:port/db').
            max_retries: Maximum number of retries for failed tasks.
            retry_delay: Base delay in seconds for exponential backoff.
            redis_password: Optional Redis password for authentication.
            redis_ssl: Whether to use SSL/TLS for the Redis connection.

        Raises:
            ValueError: If max_retries or retry_delay are non-positive.
            redis.ConnectionError: If Redis connection fails.
        """
        if max_retries < 0:
            raise ValueError("max_retries must be non-negative")
        if retry_delay <= 0:
            raise ValueError("retry_delay must be positive")

        self.max_retries = max_retries
        self.retry_delay = retry_delay

        try:
            self.redis_client = redis.Redis.from_url(
                redis_url,
                password=redis_password,
                ssl=redis_ssl,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_keepalive=True,
            )
            # Verify connection
            self.redis_client.ping()
        except redis.ConnectionError as e:
            logger.error("Failed to connect to Redis: %s", e)
            raise

    def enqueue(
        self,
        task_func: str,
        args: Optional[List[Any]] = None,
        kwargs: Optional[Dict[str, Any]] = None,
        task_id: Optional[str] = None,
    ) -> str:
        """
        Enqueue a task for processing.

        Args:
            task_func: Fully qualified name of the callable (e.g., 'mymodule.myfunc').
            args: Positional arguments for the task.
            kwargs: Keyword arguments for the task.
            task_id: Optional custom task ID; generated if not provided.

        Returns:
            The task ID as a string.

        Raises:
            ValueError: If task_func is empty or contains dangerous characters.
            TypeError: If args/kwargs cannot be serialized to JSON.
        """
        if not task_func or not task_func.strip():
            raise ValueError("task_func must be a non-empty string")
        # Basic sanitization: allow only alphanumeric, dots, underscores
        if not all(c.isalnum() or c in "._" for c in task_func):
            raise ValueError("task_func contains invalid characters")

        args = args or []
        kwargs = kwargs or {}
        task_id = task_id or str(uuid.uuid4())

        # Validate task ID format
        if not isinstance(task_id, str) or not task_id.strip():
            raise ValueError("task_id must be a non-empty string")

        task_payload = {
            "task_id": task_id,
            "task_func": task_func,
            "args": args,
            "kwargs": kwargs,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "retries": 0,
        }

        try:
            serialized = json.dumps(task_payload)
        except (TypeError, ValueError) as e:
            raise TypeError(f"Task payload not JSON serializable: {e}") from e

        # Store task definition
        self.redis_client.hset(f"{TASK_PREFIX}{task_id}", mapping=task_payload)
        # Set initial status
        self.redis_client.set(f"{STATUS_PREFIX}{task_id}", STATUS_PENDING)
        # Push to queue
        self.redis_client.rpush(QUEUE_KEY, task_id)

        logger.info("Enqueued task %s: %s", task_id, task_func)
        return task_id

    def get_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve the current status and metadata of a task.

        Args:
            task_id: The task identifier.

        Returns:
            Dictionary with task details, or None if task not found.
        """
        task_key = f"{TASK_PREFIX}{task_id}"
        status_key = f"{STATUS_PREFIX}{task_id}"
        result_key = f"{RESULT_PREFIX}{task_id}"

        if not self.redis_client.exists(task_key):
            return None

        task_data = self.redis_client.hgetall(task_key)
        status = self.redis_client.get(status_key) or STATUS_PENDING
        result = self.redis_client.get(result_key)

        return {
            "task_id": task_id,
            "status": status,
            "task_func": task_data.get("task_func", ""),
            "args": json.loads(task_data.get("args", "[]")),
            "kwargs": json.loads(task_data.get("kwargs", "{}")),
            "created_at": task_data.get("created_at", ""),
            "retries": int(task_data.get("retries", 0)),
            "result": json.loads(result) if result else None,
        }

    def _set_status(self, task_id: str, status: str) -> None:
        """Set the status of a task atomically."""
        self.redis_client.set(f"{STATUS_PREFIX}{task_id}", status)

    def _increment_retries(self, task_id: str) -> int:
        """Increment retry counter and return new value."""
        return self.redis_client.hincrby(f"{TASK_PREFIX}{task_id}", "retries", 1)

    def _store_result(self, task_id: str, result: Any) -> None:
        """Store task result as JSON."""
        try:
            serialized = json.dumps(result)
        except TypeError:
            serialized = json.dumps({"error": "Result not serializable"})
        self.redis_client.set(f"{RESULT_PREFIX}{task_id}", serialized)

    def _requeue_with_delay(self, task_id: str, retry_count: int) -> None:
        """
        Requeue a failed task with exponential backoff delay.

        Instead of blocking, we store a scheduled retry time and a separate
        process can pick it up. For simplicity, we push back to the queue
        after sleeping in the worker. In production, use a sorted set for
        delayed jobs.
        """
        delay = self.retry_delay * (2 ** (retry_count - 1))
        logger.info(
            "Retrying task %s in %.2f seconds (attempt %d/%d)",
            task_id,
            delay,
            retry_count,
            self.max_retries,
        )
        time.sleep(delay)
        self._set_status(task_id, STATUS_PENDING)
        self.redis_client.rpush(QUEUE_KEY, task_id)

    def process_task(self, task_id: str, handler_registry: Dict[str, Callable]) -> bool:
        """
        Process a single task by executing its registered handler.

        Args:
            task_id: The task identifier.
            handler_registry: Mapping of task_func names to callable handlers.

        Returns:
            True if task completed successfully, False otherwise.

        Raises:
            ValueError: If handler not found in registry.
        """
        task_key = f"{TASK_PREFIX}{task_id}"
        if not self.redis_client.exists(task_key):
            logger.warning("Task %s not found", task_id)
            return False

        task_data = self.redis_client.hgetall(task_key)
        task_func = task_data["task_func"]
        args = json.loads(task_data.get("args", "[]"))
        kwargs = json.loads(task_data.get("kwargs", "{}"))

        if task_func not in handler_registry:
            raise ValueError(f"No handler registered for '{task_func}'")

        handler = handler_registry[task_func]

        try:
            self._set_status(task_id, STATUS_PROCESSING)
            result = handler(*args, **kwargs)
            self._store_result(task_id, result)
            self._set_status(task_id, STATUS_COMPLETED)
            logger.info("Task %s completed successfully", task_id)
            return True
        except Exception as e:
            logger.error("Task %s failed: %s", task_id, e)
            retries = self._increment_retries(task_id)

            if retries <= self.max_retries:
                self._set_status(task_id, STATUS_RETRYING)
                self._requeue_with_delay(task_id, retries)
            else:
                self._set_status(task_id, STATUS_FAILED)
                self._store_result(task_id, {"error": str(e)})
                logger.error(
                    "Task %s permanently failed after %d retries", task_id, retries
                )
            return False

    def worker_loop(
        self,
        handler_registry: Dict[str, Callable],
        worker_id: int = 0,
        shutdown_event: Optional[multiprocessing.synchronize.Event] = None,
    ) -> None:
        """
        Infinite worker loop that polls the queue and processes tasks.

        Args:
            handler_registry: Mapping of task_func names to callable handlers.
            worker_id: Identifier for logging purposes.
            shutdown_event: Optional multiprocessing Event to signal graceful shutdown.
        """
        logger.info("Worker %d started", worker_id)
        while True:
            if shutdown_event and shutdown_event.is_set():
                logger.info("Worker %d shutting down gracefully", worker_id)
                break

            try:
                # Blocking pop with timeout to allow periodic shutdown checks
                result = self.redis_client.blpop(QUEUE_KEY, timeout=1)
                if result is None:
                    continue
                _, task_id = result
                logger.debug("Worker %d picked up task %s", worker_id, task_id)
                self.process_task(task_id, handler_registry)
            except redis.ConnectionError as e:
                logger.error("Worker %d Redis connection error: %s", worker_id, e)
                time.sleep(5)  # Backoff before retrying connection
            except Exception as e:
                logger.exception("Worker %d unexpected error: %s", worker_id, e)
                time.sleep(1)

    def start_workers(
        self,
        handler_registry: Dict[str, Callable],
        num_workers: int = 4,
    ) -> List[multiprocessing.Process]:
        """
        Start a pool of worker processes.

        Args:
            handler_registry: Mapping of task_func names to callable handlers.
            num_workers: Number of worker processes to spawn.

        Returns:
            List of started multiprocessing.Process instances.

        Raises:
            ValueError: If num_workers is less than 1.
        """
        if num_workers < 1:
            raise ValueError("num_workers must be at least 1")

        shutdown_event = multiprocessing.Event()
        processes = []

        # Set up signal handling in main process to propagate shutdown
        original_sigint = signal.getsignal(signal.SIGINT)
        original_sigterm = signal.getsignal(signal.SIGTERM)

        def signal_handler(signum: int, frame: Any) -> None:
            logger.info("Received signal %d, initiating worker shutdown", signum)
            shutdown_event.set()
            # Restore original handlers
            signal.signal(signal.SIGINT, original_sigint)
            signal.signal(signal.SIGTERM, original_sigterm)

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        for i in range(num_workers):
            p = multiprocessing.Process(
                target=self.worker_loop,
                args=(handler_registry, i, shutdown_event),
                daemon=True,
            )
            p.start()
            processes.append(p)
            logger.info("Started worker process %d (PID %d)", i, p.pid)

        return processes

    def purge_queue(self) -> int:
        """
        Remove all pending tasks from the queue.

        Returns:
            Number of tasks removed.
        """
        count = self.redis_client.llen(QUEUE_KEY)
        self.redis_client.delete(QUEUE_KEY)
        logger.info("Purged %d tasks from queue", count)
        return count

    def get_queue_length(self) -> int:
        """
        Get the current number of pending tasks in the queue.

        Returns:
            Queue length as integer.
        """
        return self.redis_client.llen(QUEUE_KEY)

    def cleanup_task(self, task_id: str) -> bool:
        """
        Remove all Redis keys associated with a task.

        Args:
            task_id: The task identifier.

        Returns:
            True if keys were deleted, False if task not found.
        """
        keys = [
            f"{TASK_PREFIX}{task_id}",
            f"{STATUS_PREFIX}{task_id}",
            f"{RETRY_PREFIX}{task_id}",
            f"{RESULT_PREFIX}{task_id}",
        ]
        deleted = self.redis_client.delete(*keys)
        if deleted:
            logger.info("Cleaned up task %s", task_id)
        return deleted > 0


# Example handler registry (for demonstration; users would define their own)
def _example_handler(x: int, y: int) -> int:
    """Example task handler: adds two numbers."""
    return x + y


DEFAULT_HANDLER_REGISTRY: Dict[str, Callable] = {
    "example.add": _example_handler,
}


if __name__ == "__main__":
    # Example usage
    logging.basicConfig(level=logging.INFO)

    queue = TaskQueue(max_retries=2, retry_delay=0.5)

    # Enqueue a sample task
    tid = queue.enqueue("example.add", args=[5, 7])
    print(f"Enqueued task: {tid}")

    # Start workers
    workers = queue.start_workers(DEFAULT_HANDLER_REGISTRY, num_workers=2)

    # Wait a bit for processing
    time.sleep(2)

    # Check status
    status = queue.get_status(tid)
    print(f"Task status: {status}")

    # Cleanup
    for w in workers:
        w.terminate()
        w.join()