"""
Distributed Task Queue Module

A self-contained, secure task queue implementation using Python's standard library.
Supports parallel task processing, status tracking, and automatic retry with exponential backoff.

Security Features:
- Function allowlisting prevents arbitrary code execution
- JSON serialization avoids pickle vulnerabilities
- Input validation and sanitization
- Execution timeouts prevent resource exhaustion
- Structured logging for audit trails

Example Usage:
    from task_queue import TaskQueue, worker_process, register_function
    
    @register_function
    def add_numbers(a: int, b: int) -> int:
        return a + b
    
    queue = TaskQueue()
    task_id = queue.enqueue("add_numbers", (2, 3), {})
    # Start workers in separate processes...
"""

import json
import logging
import multiprocessing as mp
import os
import queue
import signal
import sys
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from functools import wraps
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
from threading import Lock, Thread
from multiprocessing.managers import BaseManager, SyncManager
from multiprocessing.synchronize import Lock as MpLock


# Configure module logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
))
logger.addHandler(handler)


class TaskStatus(Enum):
    """Enumeration of possible task states."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"
    CANCELLED = "cancelled"


@dataclass
class Task:
    """
    Represents a unit of work in the queue.
    
    Attributes:
        id: Unique identifier for the task.
        func_name: Name of the registered function to execute.
        args: Positional arguments for the function.
        kwargs: Keyword arguments for the function.
        status: Current state of the task.
        retries: Number of retry attempts made.
        max_retries: Maximum number of retries allowed.
        result: Return value from successful execution.
        error: Error message if task failed.
        created_at: Timestamp when task was enqueued.
        started_at: Timestamp when task execution began.
        completed_at: Timestamp when task finished (success or final failure).
        worker_id: Identifier of the worker processing this task.
    """
    id: str
    func_name: str
    args: Tuple[Any, ...]
    kwargs: Dict[str, Any]
    status: TaskStatus = TaskStatus.PENDING
    retries: int = 0
    max_retries: int = 3
    result: Any = None
    error: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    worker_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert task to a JSON-serializable dictionary."""
        data = asdict(self)
        data['status'] = self.status.value
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Task':
        """Create Task instance from dictionary."""
        data = data.copy()
        data['status'] = TaskStatus(data['status'])
        return cls(**data)


class FunctionRegistry:
    """
    Thread-safe registry of allowed functions for task execution.
    
    Prevents arbitrary code execution by maintaining an explicit allowlist
    of functions that can be invoked through the task queue.
    """
    
    _instance: Optional['FunctionRegistry'] = None
    _lock = Lock()
    
    def __new__(cls) -> 'FunctionRegistry':
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._functions: Dict[str, Callable] = {}
                    cls._instance._lock = Lock()
        return cls._instance
    
    def register(self, func: Callable) -> Callable:
        """
        Register a function for use in the task queue.
        
        Args:
            func: The function to register. Must have a __name__ attribute.
            
        Returns:
            The original function, unmodified.
            
        Raises:
            ValueError: If function name is already registered.
        """
        with self._lock:
            if func.__name__ in self._functions:
                raise ValueError(f"Function '{func.__name__}' already registered")
            self._functions[func.__name__] = func
            logger.info(f"Registered function: {func.__name__}")
        return func
    
    def get(self, name: str) -> Optional[Callable]:
        """
        Retrieve a registered function by name.
        
        Args:
            name: Name of the function to retrieve.
            
        Returns:
            The function if registered, None otherwise.
        """
        with self._lock:
            return self._functions.get(name)
    
    def list_functions(self) -> List[str]:
        """Return list of registered function names."""
        with self._lock:
            return list(self._functions.keys())


def register_function(func: Callable) -> Callable:
    """
    Decorator to register a function with the global FunctionRegistry.
    
    Args:
        func: Function to register.
        
    Returns:
        The original function.
        
    Example:
        @register_function
        def my_task(x: int) -> int:
            return x * 2
    """
    return FunctionRegistry().register(func)


class TaskQueue:
    """
    Thread-safe task queue with status tracking and retry logic.
    
    Uses a multiprocessing Manager for shared state across processes,
    enabling true parallel execution with multiple worker processes.
    """
    
    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        task_timeout: float = 300.0
    ) -> None:
        """
        Initialize the task queue.
        
        Args:
            max_retries: Default maximum retry attempts for tasks.
            base_delay: Base delay in seconds for exponential backoff.
            max_delay: Maximum delay in seconds between retries.
            task_timeout: Maximum execution time per task in seconds.
        """
        self._manager: SyncManager = mp.Manager()
        self._task_queue: "mp.Queue[Dict[str, Any]]" = self._manager.Queue()
        self._tasks: "Dict[str, Task]" = self._manager.dict()
        self._tasks_lock: MpLock = self._manager.Lock()
        self._max_retries = max_retries
        self._base_delay = base_delay
        self._max_delay = max_delay
        self._task_timeout = task_timeout
        self._shutdown_event = self._manager.Event()
        logger.info("TaskQueue initialized")
    
    def enqueue(
        self,
        func_name: str,
        args: Tuple[Any, ...] = (),
        kwargs: Optional[Dict[str, Any]] = None,
        max_retries: Optional[int] = None
    ) -> str:
        """
        Add a task to the queue for execution.
        
        Args:
            func_name: Name of registered function to execute.
            args: Positional arguments for the function.
            kwargs: Keyword arguments for the function.
            max_retries: Override default max retries for this task.
            
        Returns:
            Unique task ID.
            
        Raises:
            ValueError: If function is not registered or arguments not JSON-serializable.
        """
        # Validate function exists
        if FunctionRegistry().get(func_name) is None:
            raise ValueError(f"Function '{func_name}' is not registered")
        
        # Validate JSON serializability (security: no pickle)
        try:
            json.dumps(args)
            json.dumps(kwargs or {})
        except (TypeError, ValueError) as e:
            raise ValueError(f"Arguments must be JSON-serializable: {e}")
        
        task_id = str(uuid.uuid4())
        task = Task(
            id=task_id,
            func_name=func_name,
            args=args,
            kwargs=kwargs or {},
            max_retries=max_retries if max_retries is not None else self._max_retries
        )
        
        with self._tasks_lock:
            self._tasks[task_id] = task
            self._task_queue.put(task.to_dict())
        
        logger.info(f"Enqueued task {task_id}: {func_name}")
        return task_id
    
    def get_status(self, task_id: str) -> Optional[TaskStatus]:
        """
        Get the current status of a task.
        
        Args:
            task_id: ID of the task to check.
            
        Returns:
            TaskStatus if task exists, None otherwise.
        """
        with self._tasks_lock:
            task = self._tasks.get(task_id)
            return task.status if task else None
    
    def get_task(self, task_id: str) -> Optional[Task]:
        """
        Get full task details including result or error.
        
        Args:
            task_id: ID of the task to retrieve.
            
        Returns:
            Task object if found, None otherwise.
        """
        with self._tasks_lock:
            return self._tasks.get(task_id)
    
    def get_result(self, task_id: str, timeout: Optional[float] = None) -> Any:
        """
        Wait for task completion and return result.
        
        Args:
            task_id: ID of the task to wait for.
            timeout: Maximum time to wait in seconds. None waits indefinitely.
            
        Returns:
            Task result if completed successfully.
            
        Raises:
            ValueError: If task not found.
            TimeoutError: If timeout exceeded.
            RuntimeError: If task failed.
        """
        start_time = time.time()
        while True:
            task = self.get_task(task_id)
            if task is None:
                raise ValueError(f"Task {task_id} not found")
            
            if task.status == TaskStatus.COMPLETED:
                return task.result
            elif task.status == TaskStatus.FAILED:
                raise RuntimeError(f"Task failed: {task.error}")
            
            if timeout is not None and (time.time() - start_time) >= timeout:
                raise TimeoutError(f"Task {task_id} did not complete within {timeout}s")
            
            time.sleep(0.1)
    
    def retry_failed(self, task_id: str) -> bool:
        """
        Manually retry a failed task.
        
        Args:
            task_id: ID of the failed task to retry.
            
        Returns:
            True if task was re-queued, False if task not found or not failed.
        """
        with self._tasks_lock:
            task = self._tasks.get(task_id)
            if task is None or task.status != TaskStatus.FAILED:
                return False
            
            # Reset for retry
            task.status = TaskStatus.PENDING
            task.retries = 0
            task.error = None
            task.started_at = None
            task.completed_at = None
            task.worker_id = None
            self._task_queue.put(task.to_dict())
            logger.info(f"Manually re-queued failed task {task_id}")
            return True
    
    def list_tasks(self, status: Optional[TaskStatus] = None) -> List[Task]:
        """
        List all tasks, optionally filtered by status.
        
        Args:
            status: Filter tasks by status. None returns all tasks.
            
        Returns:
            List of Task objects.
        """
        with self._tasks_lock:
            tasks = list(self._tasks.values())
            if status:
                tasks = [t for t in tasks if t.status == status]
            return tasks
    
    def shutdown(self) -> None:
        """Signal shutdown to all workers."""
        self._shutdown_event.set()
        logger.info("Shutdown signal sent")
    
    def is_shutdown(self) -> bool:
        """Check if shutdown has been signaled."""
        return self._shutdown_event.is_set()


def _execute_task(
    task_data: Dict[str, Any],
    task_queue: TaskQueue,
    worker_id: str
) -> None:
    """
    Execute a single task with timeout and error handling.
    
    Args:
        task_data: Serialized task dictionary.
        task_queue: TaskQueue instance for status updates.
        worker_id: Identifier of the executing worker.
    """
    task = Task.from_dict(task_data)
    func = FunctionRegistry().get(task.func_name)
    
    if func is None:
        _update_task_status(
            task_queue, task.id, TaskStatus.FAILED,
            error=f"Function '{task.func_name}' not registered",
            worker_id=worker_id
        )
        return
    
    # Update status to running
    _update_task_status(
        task_queue, task.id, TaskStatus.RUNNING,
        started_at=datetime.now(timezone.utc).isoformat(),
        worker_id=worker_id
    )
    
    try:
        # Execute with timeout using a thread
        result_container: Dict[str, Any] = {}
        error_container: Dict[str, BaseException] = {}
        
        def target() -> None:
            try:
                result_container['result'] = func(*task.args, **task.kwargs)
            except BaseException as e:
                error_container['error'] = e
        
        thread = Thread(target=target)
        thread.start()
        thread.join(timeout=task_queue._task_timeout)
        
        if thread.is_alive():
            # Timeout - cannot forcibly kill thread in Python, but we can mark as failed
            raise TimeoutError(f"Task exceeded {task_queue._task_timeout}s timeout")
        
        if 'error' in error_container:
            raise error_container['error']
        
        result = result_container.get('result')
        _update_task_status(
            task_queue, task.id, TaskStatus.COMPLETED,
            result=result,
            completed_at=datetime.now(timezone.utc).isoformat()
        )
        logger.info(f"Task {task.id} completed successfully")
        
    except Exception as e:
        _handle_task_failure(task_queue, task, e, worker_id)


def _update_task_status(
    task_queue: TaskQueue,
    task_id: str,
    status: TaskStatus,
    **kwargs: Any
) -> None:
    """Thread-safe task status update."""
    with task_queue._tasks_lock:
        task = task_queue._tasks.get(task_id)
        if task:
            task.status = status
            for key, value in kwargs.items():
                setattr(task, key, value)


def _handle_task_failure(
    task_queue: TaskQueue,
    task: Task,
    error: Exception,
    worker_id: str
) -> None:
    """Handle task failure with retry logic."""
    error_msg = f"{type(error).__name__}: {str(error)}"
    logger.warning(f"Task {task.id} failed (attempt {task.retries + 1}/{task.max_retries}): {error_msg}")
    
    if task.retries < task.max_retries:
        # Schedule retry with exponential backoff
        task.retries += 1
        task.status = TaskStatus.RETRYING
        task.error = error_msg
        
        delay = min(
            task_queue._base_delay * (2 ** (task.retries - 1)),
            task_queue._max_delay
        )
        
        def delayed_requeue() -> None:
            time.sleep(delay)
            if not task_queue.is_shutdown():
                with task_queue._tasks_lock:
                    current_task = task_queue._tasks.get(task.id)
                    if current_task and current_task.status == TaskStatus.RETRYING:
                        current_task.status = TaskStatus.PENDING
                        task_queue._task_queue.put(current_task.to_dict())
                        logger.info(f"Re-queued task {task.id} for retry {current_task.retries}/{current_task.max_retries}")
        
        Thread(target=delayed_requeue, daemon=True).start()
    else:
        # Max retries exceeded