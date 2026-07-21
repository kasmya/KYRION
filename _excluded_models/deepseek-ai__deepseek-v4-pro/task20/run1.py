"""
Distributed task queue module.

Provides functionality to enqueue tasks, process them in parallel using
a pool of worker threads or processes, track task status, and retry failed
tasks. Uses Redis as the message broker and backend for task state.
"""

import json
import logging
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Union

import redis
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    """Enumeration of possible task statuses."""

    PENDING = "pending"
    PROCESSING = "processing"
    SUCCESS = "success"
    FAILED = "failed"
    RETRYING = "retrying"


@dataclass
class Task:
    """
    Represents a task with its metadata.

    Attributes:
        task_id: Unique identifier for the task.
        func_name: Fully qualified name of the callable.
        args: Positional arguments for the callable.
        kwargs: Keyword arguments for the callable.
        status: Current status of the task.
        max_retries: Maximum number of retry attempts.
        retries: Number of retries already performed.
        result: Result data if task succeeded.
        error: Error message if task failed.
        created_at: Timestamp of task creation.
    """

    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    func_name: str = ""
    args: List[Any] = field(default_factory=list)
    kwargs: Dict[str, Any] = field(default_factory=dict)
    status: TaskStatus = TaskStatus.PENDING
    max_retries: int = 3
    retries: int = 0
    result: Any = None
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)

    def to_json(self) -> str:
        """Serialize task to a JSON string."""
        data = {
            "task_id": self.task_id,
            "func_name": self.func_name,
            "args": self.args,
            "kwargs": self.kwargs,
            "status": self.status.value,
            "max_retries": self.max_retries,
            "retries": self.retries,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at,
        }
        return json.dumps(data, default=str)

    @classmethod
    def from_json(cls, json_str: str) -> "Task":
        """Deserialize a JSON string into a Task instance."""
        data = json.loads(json_str)
        task = cls(
            task_id=data["task_id"],
            func_name=data["func_name"],
            args=data["args"],
            kwargs=data["kwargs"],
            max_retries=data["max_retries"],
            retries=data["retries"],
            result=data["result"],
            error=data["error"],
            created_at=data["created_at"],
        )
        task.status = TaskStatus(data["status"])
        return task


class TaskQueue:
    """
    Distributed task queue backed by Redis.

    Enqueues tasks into a Redis list, processes them using a pool of workers,
    tracks status in Redis hashes, and retries failed tasks up to a maximum
    number of attempts.

    Args:
        redis_client: Configured redis.Redis client instance.
        queue_key: Redis key for the pending tasks list.
        status_key_prefix: Prefix for per-task status hash keys.
        retry_set_key: Redis key for the set of task IDs scheduled for retry.
        num_workers: Number of worker threads/processes.
        use_processes: If True, use ProcessPoolExecutor instead of threads.
    """

    def __init__(
        self,
        redis_client: redis.Redis,
        queue_key: str = "task_queue:pending",
        status_key_prefix: str = "task_status:",
        retry_set_key: str = "task_queue:retry",
        num_workers: int = 4,
        use_processes: bool = False,
    ) -> None:
        """
        Initialize the TaskQueue.

        Args:
            redis_client: A redis.Redis instance connected to the broker.
            queue_key: Redis list key holding pending task JSON payloads.
            status_key_prefix: Prefix used for Redis hashes storing task status.
            retry_set_key: Redis set key tracking tasks that need retry.
            num_workers: Number of parallel workers.
            use_processes: If True, spawn processes instead of threads.
        """
        self._redis = redis_client
        self._queue_key = queue_key
        self._status_prefix = status_key_prefix
        self._retry_set_key = retry_set_key
        self._num_workers = num_workers
        self._use_processes = use_processes
        self._executor: Optional[Union[ThreadPoolExecutor, "ProcessPoolExecutor"]] = None  # type: ignore[name-defined]
        self._registry: Dict[str, Callable[..., Any]] = {}

    def register_task(self, func: Callable[..., Any]) -> None:
        """
        Register a callable so it can be invoked by name.

        Args:
            func: A callable to register. Its __qualname__ is used as identifier.

        Raises:
            ValueError: If a function with the same name is already registered.
        """
        name = func.__qualname__
        if name in self._registry:
            raise ValueError(f"Function '{name}' is already registered.")
        self._registry[name] = func
        logger.info("Registered task function '%s'", name)

    def _status_key(self, task_id: str) -> str:
        """Return the Redis key for a task's status hash."""
        return f"{self._status_prefix}{task_id}"

    def enqueue(
        self,
        func: Callable[..., Any],
        *args: Any,
        max_retries: int = 3,
        **kwargs: Any,
    ) -> str:
        """
        Enqueue a task for asynchronous execution.

        Args:
            func: The callable to execute. Must be registered via register_task.
            *args: Positional arguments forwarded to the callable.
            max_retries: Maximum retry attempts on failure.
            **kwargs: Keyword arguments forwarded to the callable.

        Returns:
            The unique task ID assigned to the enqueued task.

        Raises:
            ValueError: If the function has not been registered.
            RedisError: On communication failure with Redis.
        """
        name = func.__qualname__
        if name not in self._registry:
            raise ValueError(
                f"Function '{name}' is not registered. Call register_task first."
            )

        task = Task(
            func_name=name,
            args=list(args),
            kwargs=kwargs,
            max_retries=max_retries,
        )
        payload = task.to_json()

        # Atomically push the task and initialise its status
        try:
            pipe = self._redis.pipeline()
            pipe.lpush(self._queue_key, payload)
            pipe.hset(
                self._status_key(task.task_id),
                mapping={
                    "status": TaskStatus.PENDING.value,
                    "retries": 0,
                    "max_retries": max_retries,
                },
            )
            pipe.execute()
        except RedisError as exc:
            logger.error("Failed to enqueue task: %s", exc)
            raise

        logger.info("Enqueued task '%s' with id %s", name, task.task_id)
        return task.task_id

    def get_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve the current status and metadata of a task.

        Args:
            task_id: The unique identifier of the task.

        Returns:
            A dictionary with keys 'status', 'retries', 'max_retries',
            'result', 'error', or None if the task ID is unknown.

        Raises:
            RedisError: On communication failure with Redis.
        """
        try:
            data = self._redis.hgetall(self._status_key(task_id))
        except RedisError as exc:
            logger.error("Failed to get status for task %s: %s", task_id, exc)
            raise

        if not data:
            return None

        # Decode bytes to strings
        decoded: Dict[str, Any] = {k.decode(): v.decode() for k, v in data.items()}
        if "result" in decoded:
            try:
                decoded["result"] = json.loads(decoded["result"])
            except (json.JSONDecodeError, TypeError):
                pass
        return decoded

    def start_workers(self) -> None:
        """
        Start the worker pool to consume tasks from the queue.

        Workers run until stop_workers is called or the process is interrupted.
        This method blocks the calling thread.
        """
        if self._use_processes:
            from concurrent.futures import ProcessPoolExecutor

            self._executor = ProcessPoolExecutor(max_workers=self._num_workers)
        else:
            self._executor = ThreadPoolExecutor(max_workers=self._num_workers)

        logger.info(
            "Starting %d workers (%s)",
            self._num_workers,
            "processes" if self._use_processes else "threads",
        )

        try:
            self._run_loop()
        except KeyboardInterrupt:
            logger.info("Worker loop interrupted by user.")
        finally:
            self.stop_workers()

    def stop_workers(self) -> None:
        """Gracefully shut down the worker pool."""
        if self._executor:
            self._executor.shutdown(wait=True, cancel_futures=True)
            self._executor = None
            logger.info("Worker pool shut down.")

    def _run_loop(self) -> None:
        """Main loop that fetches tasks and submits them to the executor."""
        futures: Dict[Future[Any], str] = {}
        executor = self._executor
        if executor is None:
            raise RuntimeError("Executor not initialised. Call start_workers first.")

        while True:
            # Keep the executor fed with tasks
            while len(futures) < self._num_workers * 2:
                task = self._fetch_task()
                if task is None:
                    break  # No pending tasks right now
                future = executor.submit(self._execute_task, task)
                futures[future] = task.task_id

            if not futures:
                # No tasks in queue and no running futures; brief sleep
                time.sleep(0.5)
                continue

            # Wait for at least one future to complete
            done_futures = as_completed(futures.keys(), timeout=1.0)
            for future in done_futures:
                task_id = futures.pop(future)
                try:
                    future.result()  # re-raise any exceptions from the worker
                except Exception as exc:
                    logger.error("Unhandled exception in task %s: %s", task_id, exc)

    def _fetch_task(self) -> Optional[Task]:
        """
        Atomically pop a task from the pending queue and mark it PROCESSING.

        Returns:
            A Task instance or None if the queue is empty.

        Raises:
            RedisError: On communication failure with Redis.
        """
        try:
            # BRPOP is blocking; use RPOP with immediate return to avoid blocking the loop
            payload = self._redis.rpop(self._queue_key)
        except RedisError as exc:
            logger.error("Error fetching task: %s", exc)
            raise

        if payload is None:
            return None

        try:
            task = Task.from_json(payload.decode() if isinstance(payload, bytes) else payload)
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            logger.error("Malformed task payload discarded: %s", exc)
            return None

        # Mark as processing
        try:
            self._redis.hset(
                self._status_key(task.task_id),
                mapping={"status": TaskStatus.PROCESSING.value},
            )
        except RedisError as exc:
            logger.error("Failed to update status for task %s: %s", task.task_id, exc)
            # Re-queue the task to avoid losing it
            self._redis.lpush(self._queue_key, task.to_json())
            return None

        return task

    def _execute_task(self, task: Task) -> None:
        """
        Execute a single task, handle retries, and update Redis status.

        Args:
            task: The Task instance to execute.
        """
        func = self._registry.get(task.func_name)
        if func is None:
            error_msg = f"Unknown function '{task.func_name}'"
            self._mark_failed(task, error_msg, permanent=True)
            return

        try:
            result = func(*task.args, **task.kwargs)
            self._mark_success(task, result)
        except Exception as exc:
            error_msg = f"{type(exc).__name__}: {exc}"
            logger.warning("Task %s failed: %s", task.task_id, error_msg)
            self._handle_failure(task, error_msg)

    def _mark_success(self, task: Task, result: Any) -> None:
        """
        Record a successful task completion in Redis.

        Args:
            task: The completed task.
            result: The return value of the task function.
        """
        try:
            result_json = json.dumps(result, default=str)
        except (TypeError, ValueError) as exc:
            logger.error("Cannot serialise result for task %s: %s", task.task_id, exc)
            result_json = json.dumps({"serialisation_error": str(exc)})

        try:
            self._redis.hset(
                self._status_key(task.task_id),
                mapping={
                    "status": TaskStatus.SUCCESS.value,
                    "result": result_json,
                },
            )
        except RedisError as exc:
            logger.error("Failed to record success for task %s: %s", task.task_id, exc)
        else:
            logger.info("Task %s completed successfully.", task.task_id)

    def _handle_failure(self, task: Task, error_msg: str) -> None:
        """
        Decide whether to retry a failed task or mark it permanently failed.

        Args:
            task: The failed task.
            error_msg: String representation of the error.
        """
        task.retries += 1
        if task.retries <= task.max_retries:
            self._schedule_retry(task, error_msg)
        else:
            self._mark_failed(task, error_msg, permanent=True)

    def _schedule_retry(self, task: Task, error_msg: str) -> None:
        """
        Update task status to RETRYING and push it back into the pending queue.

        Args:
            task: The task to retry.
            error_msg: Error message from the last attempt.
        """
        task.status = TaskStatus.RETRYING
        try:
            pipe = self._redis.pipeline()
            pipe.hset(
                self._status_key(task.task_id),
                mapping={
                    "status": TaskStatus.RETRYING.value,
                    "retries": task.retries,
                    "error": error_msg,
                },
            )
            pipe.lpush(self._queue_key, task.to_json())
            pipe.execute()
        except RedisError as exc:
            logger.error("Failed to schedule retry for task %s: %s", task.task_id, exc)
        else:
            logger.info(
                "Task %s scheduled for retry (%d/%d).",
                task.task_id,
                task.retries,
                task.max_retries,
            )

    def _mark_failed(
        self, task: Task, error_msg: str, permanent: bool = False
    ) -> None:
        """
        Mark a task as FAILED (optionally permanent) in Redis.

        Args:
            task: The failed task.
            error_msg: Error description.
            permanent: If True, no further retries will be attempted.
        """
        try:
            self._redis.hset(
                self._status_key(task.task_id),
                mapping={
                    "status": TaskStatus.FAILED.value,
                    "error": error_msg,
                    "retries": task.retries,
                },
            )
        except RedisError as exc:
            logger.error(
                "Failed to persist failure for task %s: %s", task.task_id, exc
            )
        else:
            logger.info(
                "Task %s marked as failed%s.", task.task_id,
                " permanently" if permanent else "",
            )


# ---------------------------------------------------------------------------
# Minimal example usage (runnable as script for demonstration)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import os
    import signal
    import sys
    from typing import NoReturn

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    def example_task(name: str, delay: float = 0.1) -> str:
        """Example task that simply returns a greeting after a short delay."""
        time.sleep(delay)
        if name.lower() == "fail":
            raise RuntimeError("Simulated failure")
        return f"Hello, {name}!"

    def main() -> NoReturn:
        """Run a small demonstration of the distributed task queue."""
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        client = redis.Redis.from_url(redis_url, decode_responses=True)

        queue = TaskQueue(
            redis_client=client,
            num_workers=2,
            use_processes=False,
        )
        queue.register_task(example_task)

        # Enqueue a few tasks
        ids = []
        for name in ["Alice", "Bob", "fail", "Charlie"]:
            tid = queue.enqueue(example_task, name, max_retries=2)
            ids.append(tid)
            logger.info("Enqueued task %s", tid)

        # Run workers in the main thread (blocking)
        def shutdown(signum: int, frame: Any) -> None:
            logger.info("Signal received, shutting down workers.")
            queue.stop_workers()
            sys.exit(0)

        signal.signal(signal.SIGINT, shutdown)
        signal.signal(signal.SIGTERM, shutdown)

        queue.start_workers()

    main()