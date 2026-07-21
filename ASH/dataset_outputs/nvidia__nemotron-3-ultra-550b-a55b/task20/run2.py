"""
Distributed Task Queue Implementation

This module provides a distributed task queue system using Redis as the backend.
It supports enqueueing tasks, processing them with parallel workers, tracking task status,
and retrying failed tasks with exponential backoff.

Security considerations:
- Uses JSON serialization instead of pickle to prevent arbitrary code execution
- Validates all inputs and uses a function registry to restrict executable functions
- Implements proper error handling and connection pooling
- Supports Redis authentication via URL credentials

Requirements:
- redis-py (pip install redis)
- Running Redis server (local or remote)

Example usage:
    from distributed_task_queue import TaskQueue, worker, register_function
    
    @register_function
    def add_numbers(a: int, b: int) -> int:
        return a + b
    
    queue = TaskQueue("redis://localhost:6379")
    task_id = queue.enqueue("add_numbers", 5, 3)
    # Start workers in separate processes/threads
    # worker(queue, worker_id="worker-1")
"""

import json
import time
import uuid
import logging
import traceback
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Union
from functools import wraps

import redis
from redis.connection import ConnectionPool
from redis.exceptions import RedisError, ConnectionError, TimeoutError

# Configure module logger
logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


class TaskStatus(str, Enum):
    """Enumeration of possible task statuses."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"


@dataclass
class Task:
    """Represents a task in the queue system."""
    id: str
    function_name: str
    args: List[Any] = field(default_factory=list)
    kwargs: Dict[str, Any] = field(default_factory=dict)
    status: TaskStatus = TaskStatus.PENDING
    retries: int = 0
    max_retries: int = 3
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    result: Any = None
    error: Optional[str] = None
    worker_id: Optional[str] = None
    scheduled_for: Optional[str] = None  # For delayed retries

    def to_json(self) -> str:
        """Serialize task to JSON string."""
        data = asdict(self)
        data["status"] = self.status.value
        return json.dumps(data, default=str)

    @classmethod
    def from_json(cls, json_str: str) -> "Task":
        """Deserialize task from JSON string."""
        data = json.loads(json_str)
        data["status"] = TaskStatus(data["status"])
        return cls(**data)


class FunctionRegistry:
    """Registry for allowed functions to prevent arbitrary code execution."""
    
    _functions: Dict[str, Callable] = {}
    
    @classmethod
    def register(cls, func: Callable) -> Callable:
        """Register a function for use in the task queue."""
        if not callable(func):
            raise TypeError("Only callable objects can be registered")
        cls._functions[func.__name__] = func
        return func
    
    @classmethod
    def get(cls, name: str) -> Callable:
        """Get a registered function by name."""
        if name not in cls._functions:
            raise ValueError(f"Function '{name}' is not registered")
        return cls._functions[name]
    
    @classmethod
    def list_registered(cls) -> List[str]:
        """List all registered function names."""
        return list(cls._functions.keys())


def register_function(func: Callable) -> Callable:
    """Decorator to register a function for use in the task queue."""
    return FunctionRegistry.register(func)


class TaskQueue:
    """
    Distributed task queue using Redis as backend.
    
    Provides methods for enqueueing tasks, dequeuing for processing,
    tracking status, and handling retries with exponential backoff.
    """
    
    # Redis key prefixes
    TASK_PREFIX = "task:"
    QUEUE_PENDING = "queue:pending"
    QUEUE_PROCESSING = "queue:processing"
    QUEUE_SCHEDULED = "queue:scheduled"  # Sorted set for delayed retries
    QUEUE_COMPLETED = "queue:completed"
    QUEUE_FAILED = "queue:failed"
    
    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/0",
        queue_name: str = "default",
        max_retries: int = 3,
        base_retry_delay: float = 1.0,
        max_retry_delay: float = 300.0,
        connection_pool: Optional[ConnectionPool] = None,
        socket_timeout: float = 5.0,
        socket_connect_timeout: float = 5.0,
    ):
        """
        Initialize the task queue.
        
        Args:
            redis_url: Redis connection URL (supports authentication)
            queue_name: Name of the queue (allows multiple queues per Redis instance)
            max_retries: Default maximum retry attempts for tasks
            base_retry_delay: Base delay in seconds for exponential backoff
            max_retry_delay: Maximum delay cap for retries
            connection_pool: Optional pre-configured connection pool
            socket_timeout: Socket timeout for Redis operations
            socket_connect_timeout: Socket connection timeout
            
        Raises:
            ConnectionError: If unable to connect to Redis
            ValueError: If queue_name contains invalid characters
        """
        if not queue_name.isalnum() and "_" not in queue_name and "-" not in queue_name:
            raise ValueError("queue_name must be alphanumeric with underscores or hyphens")
        
        self.queue_name = queue_name
        self.max_retries = max_retries
        self.base_retry_delay = base_retry_delay
        self.max_retry_delay = max_retry_delay
        
        # Prefix all keys with queue name
        self._prefix_keys()
        
        # Initialize Redis connection
        try:
            if connection_pool:
                self.redis = redis.Redis(connection_pool=connection_pool)
            else:
                self.redis = redis.from_url(
                    redis_url,
                    socket_timeout=socket_timeout,
                    socket_connect_timeout=socket_connect_timeout,
                    decode_responses=True,
                )
            # Test connection
            self.redis.ping()
            logger.info(f"Connected to Redis at {redis_url}")
        except (ConnectionError, TimeoutError) as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise ConnectionError(f"Cannot connect to Redis: {e}") from e
    
    def _prefix_keys(self) -> None:
        """Apply queue name prefix to all Redis keys."""
        prefix = f"{self.queue_name}:"
        self.TASK_KEY = f"{prefix}{self.TASK_PREFIX}"
        self.PENDING_KEY = f"{prefix}{self.QUEUE_PENDING}"
        self.PROCESSING_KEY = f"{prefix}{self.QUEUE_PROCESSING}"
        self.SCHEDULED_KEY = f"{prefix}{self.QUEUE_SCHEDULED}"
        self.COMPLETED_KEY = f"{prefix}{self.QUEUE_COMPLETED}"
        self.FAILED_KEY = f"{prefix}{self.QUEUE_FAILED}"
    
    def _task_key(self, task_id: str) -> str:
        """Generate Redis key for a task."""
        return f"{self.TASK_KEY}{task_id}"
    
    def enqueue(
        self,
        function_name: str,
        *args: Any,
        max_retries: Optional[int] = None,
        delay: float = 0,
        **kwargs: Any
    ) -> str:
        """
        Enqueue a new task for execution.
        
        Args:
            function_name: Name of registered function to execute
            *args: Positional arguments for the function
            max_retries: Override default max retries (None uses queue default)
            delay: Delay in seconds before task becomes available (0 for immediate)
            **kwargs: Keyword arguments for the function
            
        Returns:
            Task ID of the enqueued task
            
        Raises:
            ValueError: If function is not registered or arguments not JSON serializable
            RedisError: If Redis operation fails
        """
        # Validate function exists
        try:
            FunctionRegistry.get(function_name)
        except ValueError as e:
            raise ValueError(f"Cannot enqueue unregistered function: {e}") from e
        
        # Validate JSON serializability
        try:
            json.dumps(args)
            json.dumps(kwargs)
        except (TypeError, ValueError) as e:
            raise ValueError(f"Arguments must be JSON serializable: {e}") from e
        
        task_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        
        task = Task(
            id=task_id,
            function_name=function_name,
            args=list(args),
            kwargs=kwargs,
            max_retries=max_retries if max_retries is not None else self.max_retries,
            created_at=now,
            updated_at=now,
        )
        
        pipe = self.redis.pipeline()
        pipe.set(self._task_key(task_id), task.to_json())
        
        if delay > 0:
            scheduled_time = time.time() + delay
            task.scheduled_for = datetime.fromtimestamp(scheduled_time, tz=timezone.utc).isoformat()
            task.status = TaskStatus.PENDING  # Will be moved to pending when due
            pipe.zadd(self.SCHEDULED_KEY, {task_id: scheduled_time})
        else:
            pipe.rpush(self.PENDING_KEY, task_id)
        
        try:
            pipe.execute()
            logger.info(f"Enqueued task {task_id} ({function_name})")
            return task_id
        except RedisError as e:
            logger.error(f"Failed to enqueue task: {e}")
            raise
    
    def dequeue(self, worker_id: str, count: int = 1) -> List[Task]:
        """
        Dequeue tasks for processing by a worker.
        
        Args:
            worker_id: Unique identifier for the worker
            count: Maximum number of tasks to dequeue
            
        Returns:
            List of dequeued tasks (may be fewer than requested)
            
        Raises:
            RedisError: If Redis operation fails
        """
        if not worker_id:
            raise ValueError("worker_id cannot be empty")
        
        # First, move any due scheduled tasks to pending
        self._move_due_scheduled_tasks()
        
        tasks = []
        pipe = self.redis.pipeline()
        
        for _ in range(count):
            # Atomic pop from pending and push to processing
            task_id = self.redis.lpop(self.PENDING_KEY)
            if not task_id:
                break
            
            # Get task data
            task_json = self.redis.get(self._task_key(task_id))
            if not task_json:
                logger.warning(f"Task {task_id} not found in storage, skipping")
                continue
            
            task = Task.from_json(task_json)
            task.status = TaskStatus.PROCESSING
            task.worker_id = worker_id
            task.updated_at = datetime.now(timezone.utc).isoformat()
            
            # Update in Redis
            pipe.set(self._task_key(task_id), task.to_json())
            pipe.sadd(self.PROCESSING_KEY, task_id)
            tasks.append(task)
        
        if tasks:
            try:
                pipe.execute()
                logger.debug(f"Worker {worker_id} dequeued {len(tasks)} tasks")
            except RedisError as e:
                logger.error(f"Failed to dequeue tasks: {e}")
                raise
        
        return tasks
    
    def _move_due_scheduled_tasks(self) -> None:
        """Move tasks from scheduled queue to pending queue when their time is due."""
        now = time.time()
        due_tasks = self.redis.zrangebyscore(self.SCHEDULED_KEY, 0, now)
        if due_tasks:
            pipe = self.redis.pipeline()
            for task_id in due_tasks:
                pipe.zrem(self.SCHEDULED_KEY, task_id)
                pipe.rpush(self.PENDING_KEY, task_id)
                # Update task status
                task_json = self.redis.get(self._task_key(task_id))
                if task_json:
                    task = Task.from_json(task_json)
                    task.status = TaskStatus.PENDING
                    task.scheduled_for = None
                    task.updated_at = datetime.now(timezone.utc).isoformat()
                    pipe.set(self._task_key(task_id), task.to_json())
            try:
                pipe.execute()
            except RedisError as e:
                logger.error(f"Failed to move scheduled tasks: {e}")
    
    def complete_task(self, task_id: str, result: Any) -> bool:
        """
        Mark a task as completed with a result