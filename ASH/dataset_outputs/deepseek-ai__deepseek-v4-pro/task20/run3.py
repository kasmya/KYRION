"""
Distributed Task Queue Module

Provides a distributed task queue implementation with enqueue functionality,
parallel worker processing, task status tracking, and automatic retry of failed tasks.
Uses Redis as the backend for task storage and message brokering.
"""

import json
import logging
import signal
import sys
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

import redis
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)

DEFAULT_REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
DEFAULT_QUEUE_NAME = "task_queue"
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_DELAY = 5  # seconds
TASK_STATUS_PENDING = "pending"
TASK_STATUS_PROCESSING = "processing"
TASK_STATUS_SUCCESS = "success"
TASK_STATUS_FAILED = "failed"
TASK_STATUS_RETRYING = "retrying"


class TaskQueueError(Exception):
    """Base exception for task queue errors."""


class TaskEnqueueError(TaskQueueError):
    """Exception raised when enqueueing a task fails."""


class TaskProcessingError(TaskQueueError):
    """Exception raised during task processing."""


class Task:
    """Represents a single task in the queue.

    Attributes:
        task_id: Unique identifier for the task.
        payload: JSON-serializable data for the task.
        status: Current status of the task.
        retries: Number of retries attempted so far.
        max_retries: Maximum number of retries allowed.
        retry_delay: Delay in seconds between retries.
        created_at: Timestamp when the task was created.
        updated_at: Timestamp when the task was last updated.
        error_message: Error message if the task failed.
    """

    def __init__(
        self,
        payload: Any,
        task_id: Optional[str] = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_delay: int = DEFAULT_RETRY_DELAY,
    ) -> None:
        """Initialize a new task instance.

        Args:
            payload: JSON-serializable data for the task.
            task_id: Optional custom task ID. If None, a UUID is generated.
            max_retries: Maximum number of retries for this task.
            retry_delay: Delay in seconds between retries.
        """
        self.task_id = task_id or str(uuid.uuid4())
        self.payload = payload
        self.status = TASK_STATUS_PENDING
        self.retries = 0
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.created_at = datetime.now(timezone.utc)
        self.updated_at = self.created_at
        self.error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize task to a dictionary.

        Returns:
            Dictionary representation of the task.
        """
        return {
            "task_id": self.task_id,
            "payload": self.payload,
            "status": self.status,
            "retries": self.retries,
            "max_retries": self.max_retries,
            "retry_delay": self.retry_delay,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "error_message": self.error_message,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Task":
        """Deserialize task from a dictionary.

        Args:
            data: Dictionary containing task attributes.

        Returns:
            A Task instance populated with the data.
        """
        task = cls(
            task_id=data["task_id"],
            payload=data["payload"],
            max_retries=data.get("max_retries", DEFAULT_MAX_RETRIES),
            retry_delay=data.get("retry_delay", DEFAULT_RETRY_DELAY),
        )
        task.status = data["status"]
        task.retries = data["retries"]
        task.created_at = datetime.fromisoformat(data["created_at"])
        task.updated_at = datetime.fromisoformat(data["updated_at"])
        task.error_message = data.get("error_message")
        return task


class TaskQueue:
    """Distributed task queue backed by Redis.

    Provides enqueue, dequeue, status tracking, and automatic retry functionality.

    Attributes:
        redis_client: Redis client instance.
        queue_name: Name of the Redis list used as the queue.
        task_prefix: Prefix for task hash keys in Redis.
    """

    def __init__(
        self,
        redis_url: str = DEFAULT_REDIS_URL,
        queue_name: str = DEFAULT_QUEUE_NAME,
    ) -> None:
        """Initialize the task queue with a Redis connection.

        Args:
            redis_url: Redis connection URL (e.g., 'redis://localhost:6379/0').
            queue_name: Name of the Redis list to use as the queue.

        Raises:
            TaskQueueError: If connection to Redis fails.
        """
        self.queue_name = queue_name
        self._task_prefix = f"task:{queue_name}:"
        try:
            self.redis_client = redis.Redis.from_url(redis_url, decode_responses=True)
            self.redis_client.ping()
        except RedisError as e:
            raise TaskQueueError(f"Failed to connect to Redis: {e}") from e

    def _task_key(self, task_id: str) -> str:
        """Generate the Redis key for a task.

        Args:
            task_id: The task ID.

        Returns:
            Redis key string.
        """
        return f"{self._task_prefix}{task_id}"

    def enqueue(self, payload: Any, **task_kwargs: Any) -> str:
        """Enqueue a new task into the queue.

        Args:
            payload: JSON-serializable data for the task.
            **task_kwargs: Additional keyword arguments for Task initialization.

        Returns:
            The task ID of the enqueued task.

        Raises:
            TaskEnqueueError: If the task cannot be enqueued.
        """
        task = Task(payload=payload, **task_kwargs)
        try:
            # Sanitize payload by ensuring it's JSON-serializable
            json.dumps(task.payload)
        except (TypeError, ValueError) as e:
            raise TaskEnqueueError(f"Payload is not JSON-serializable: {e}") from e

        try:
            # Store task metadata in a hash
            self.redis_client.hset(self._task_key(task.task_id), mapping=task.to_dict())
            # Push task ID onto the queue list
            self.redis_client.rpush(self.queue_name, task.task_id)
            logger.info("Enqueued task %s", task.task_id)
            return task.task_id
        except RedisError as e:
            raise TaskEnqueueError(f"Failed to enqueue task: {e}") from e

    def dequeue(self, timeout: int = 0) -> Optional[Task]:
        """
        Dequeue a task from the queue, blocking if timeout > 0.

        Args:
            timeout: Seconds to block waiting for a task. 0 means non-blocking.

        Returns:
            A Task object if available, None otherwise.

        Raises:
            TaskQueueError: If a Redis error occurs.
        """
        try:
            if timeout > 0:
                result = self.redis_client.blpop(self.queue_name, timeout=timeout)
            else:
                result = self.redis_client.lpop(self.queue_name)

            if result is None:
                return None

            # blpop returns a tuple (key, value)
            task_id = result[1] if isinstance(result, tuple) else result
            return self.get_task(task_id)
        except RedisError as e:
            raise TaskQueueError(f"Failed to dequeue task: {e}") from e

    def get_task(self, task_id: str) -> Optional[Task]:
        """
        Retrieve a task by its ID.

        Args:
            task_id: The task ID.

        Returns:
            Task object if found, None otherwise.

        Raises:
            TaskQueueError: If a Redis error occurs.
        """
        try:
            data = self.redis_client.hgetall(self._task_key(task_id))
            if not data:
                return None
            return Task.from_dict(data)
        except RedisError as e:
            raise TaskQueueError(f"Failed to get task {task_id}: {e}") from e

    def update_task(self, task: Task) -> None:
        """
        Update a task's stored state in Redis.

        Args:
            task: The task object with updated fields.

        Raises:
            TaskQueueError: If the update fails.
        """
        task.updated_at = datetime.now(timezone.utc)
        try:
            self.redis_client.hset(
                self._task_key(task.task_id), mapping=task.to_dict()
            )
        except RedisError as e:
            raise TaskQueueError(f"Failed to update task {task.task_id}: {e}") from e

    def mark_processing(self, task: Task) -> None:
        """
        Mark a task as processing.

        Args:
            task: The task to mark.
        """
        task.status = TASK_STATUS_PROCESSING
        self.update_task(task)

    def mark_success(self, task: Task) -> None:
        """
        Mark a task as successfully completed.

        Args:
            task: The task to mark.
        """
        task.status = TASK_STATUS_SUCCESS
        self.update_task(task)

    def mark_failed(self, task: Task, error_message: str) -> None:
        """
        Mark a task as failed and optionally schedule a retry.

        Args:
            task: The failed task.
            error_message: Description of the failure.
        """
        task.status = TASK_STATUS_FAILED
        task.error_message = error_message
        self.update_task(task)
        self._maybe_retry(task)

    def _maybe_retry(self, task: Task) -> None:
        """
        Schedule a retry for a failed task if retries remain.

        Args:
            task: The failed task.
        """
        if task.retries < task.max_retries:
            task.retries += 1
            task.status = TASK_STATUS_RETRYING
            task.error_message = f"Retry {task.retries}/{task.max_retries}"
            self.update_task(task)
            # Re-enqueue after delay using scheduled set
            retry_time = time.time() + task.retry_delay
            try:
                self.redis_client.zadd(
                    f"{self.queue_name}:delayed", {task.task_id: retry_time}
                )
                logger.info(
                    "Scheduled retry %d for task %s in %d seconds",
                    task.retries,
                    task.task_id,
                    task.retry_delay,
                )
            except RedisError as e:
                logger.error("Failed to schedule retry for task %s: %s", task.task_id, e)

    def requeue_delayed_tasks(self) -> None:
        """
        Move tasks whose delay has elapsed from the delayed set to the main queue.
        Should be called periodically.
        """
        try:
            now = time.time()
            delayed_key = f"{self.queue_name}:delayed"
            task_ids = self.redis_client.zrangebyscore(delayed_key, 0, now)
            for task_id in task_ids:
                self.redis_client.rpush(self.queue_name, task_id)
                self.redis_client.zrem(delayed_key, task_id)
                logger.info("Requeued delayed task %s", task_id)
        except RedisError as e:
            logger.error("Failed to requeue delayed tasks: %s", e)


def process_tasks(
    queue: TaskQueue,
    handler: Callable[[Any], Any],
    worker_id: Optional[str] = None,
    poll_timeout: int = 1,
) -> None:
    """
    Worker function that continuously processes tasks from the queue.

    Args:
        queue: The TaskQueue instance.
        handler: A callable that takes the task payload and returns True on success,
                 False on failure (to trigger retry).
        worker_id: Optional identifier for this worker.
        poll_timeout: Seconds to block waiting for a task.
    """
    worker_id = worker_id or str(uuid.uuid4())[:8]
    logger.info("Worker %s started", worker_id)

    while True:
        try:
            # Periodically move delayed tasks into main queue
            queue.requeue_delayed_tasks()

            task = queue.dequeue(timeout=poll_timeout)
            if task is None:
                continue

            logger.info("Worker %s picked up task %s", worker_id, task.task_id)
            queue.mark_processing(task)

            try:
                # Execute handler with payload
                success = handler(task.payload)
                if success:
                    queue.mark_success(task)
                    logger.info("Worker %s completed task %s", worker_id, task.task_id)
                else:
                    raise TaskProcessingError("Handler returned failure status")
            except Exception as e:
                error_msg = f"{type(e).__name__}: {str(e)}"
                logger.error("Worker %s failed task %s: %s", worker_id, task.task_id, error_msg)
                queue.mark_failed(task, error_msg)

        except TaskQueueError as e:
            logger.error("Worker %s queue error: %s", worker_id, e)
            time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Worker %s shutting down", worker_id)
            break


def get_task_status(queue: TaskQueue, task_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve the current status and details of a task.

    Args:
        queue: The TaskQueue instance.
        task_id: The task ID.

    Returns:
        A dictionary with task details, or None if not found.
    """
    task = queue.get_task(task_id)
    if task:
        return task.to_dict()
    return None


def retry_failed_tasks(queue: TaskQueue) -> int:
    """
    Manually retry all tasks currently in failed state that have retries left.

    Args:
        queue: The TaskQueue instance.

    Returns:
        Number of tasks queued for retry.
    """
    count = 0
    # Scan for all task keys with failed status
    try:
        for key in queue.redis_client.scan_iter(f"{queue._task_prefix}*"):
            data = queue.redis_client.hgetall(key)
            if data.get("status") == TASK_STATUS_FAILED:
                task = Task.from_dict(data)
                if task.retries < task.max_retries:
                    queue._maybe_retry(task)
                    count += 1
        return count
    except RedisError as e:
        raise TaskQueueError(f"Failed to retry tasks: {e}") from e