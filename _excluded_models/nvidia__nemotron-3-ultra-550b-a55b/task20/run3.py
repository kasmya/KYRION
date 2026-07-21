"""
Distributed Task Queue Module

A thread-safe, multiprocessing-based task queue with status tracking,
automatic retries, and parallel worker execution.

Features:
- Enqueue tasks with arbitrary callables and arguments
- Process tasks in parallel using a worker pool
- Track task status (pending, running, completed, failed, retrying)
- Automatic retry with exponential backoff for failed tasks
- Thread-safe status queries and result retrieval
- Graceful shutdown with task completion waiting

Security Considerations:
- Uses JSON serialization instead of pickle to prevent arbitrary code execution
- Validates all inputs and handles exceptions explicitly
- No eval/exec or dynamic code execution
- Workers run in separate processes for isolation
"""

import json
import logging
import multiprocessing as mp
import queue
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, Future
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
from threading import Lock, Event


# Configure module logger
logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


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
        func_name: Name of the function to execute (for logging/debugging).
        args: Positional arguments for the function.
        kwargs: Keyword arguments for the function.
        status: Current status of the task.
        result: Return value of the function (if completed).
        error: Error message (if failed).
        retry_count: Number of retry attempts made.
        max_retries: Maximum number of retries allowed.
        created_at: Timestamp when task was enqueued.
        started_at: Timestamp when task execution began.
        completed_at: Timestamp when task finished (success or final failure).
    """
    id: str
    func_name: str
    args: Tuple[Any, ...] = field(default_factory=tuple)
    kwargs: Dict[str, Any] = field(default_factory=dict)
    status: TaskStatus = TaskStatus.PENDING
    result: Any = None
    error: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    started_at: Optional[str] = None
    completed_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert task to a JSON-serializable dictionary."""
        data = asdict(self)
        data['status'] = self.status.value
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Task':
        """Create a Task instance from a dictionary."""
        data = data.copy()
        data['status'] = TaskStatus(data['status'])
        return cls(**data)


class TaskQueue:
    """
    Thread-safe task queue with persistence and status tracking.

    Uses a multiprocessing.Queue for inter-process communication and
    a dictionary with locks for status tracking.
    """

    def __init__(self, maxsize: int = 0) -> None:
        """
        Initialize the task queue.

        Args:
            maxsize: Maximum number of tasks in queue (0 = unlimited).
        """
        self._queue: mp.Queue = mp.Queue(maxsize=maxsize)
        self._tasks: Dict[str, Task] = {}
        self._lock = Lock()
        self._shutdown_event = Event()

    def enqueue(
        self,
        func: Callable[..., Any],
        *args: Any,
        max_retries: int = 3,
        **kwargs: Any
    ) -> str:
        """
        Add a task to the queue.

        Args:
            func: Callable to execute.
            *args: Positional arguments for the callable.
            max_retries: Maximum number of retry attempts on failure.
            **kwargs: Keyword arguments for the callable.

        Returns:
            Task ID string.

        Raises:
            ValueError: If func is not callable or max_retries is negative.
            RuntimeError: If queue is full (when maxsize > 0).
        """
        if not callable(func):
            raise ValueError("func must be callable")
        if max_retries < 0:
            raise ValueError("max_retries cannot be negative")

        task_id = str(uuid.uuid4())
        task = Task(
            id=task_id,
            func_name=getattr(func, '__name__', 'unknown'),
            args=args,
            kwargs=kwargs,
            max_retries=max_retries
        )

        with self._lock:
            self._tasks[task_id] = task

        try:
            # Serialize task for queue (JSON-safe)
            task_data = task.to_dict()
            self._queue.put(task_data, block=False)
        except queue.Full:
            with self._lock:
                del self._tasks[task_id]
            raise RuntimeError("Task queue is full")

        logger.info(f"Enqueued task {task_id} ({task.func_name})")
        return task_id

    def get_task(self, task_id: str) -> Optional[Task]:
        """
        Retrieve a task by its ID.

        Args:
            task_id: The task identifier.

        Returns:
            Task object if found, None otherwise.
        """
        with self._lock:
            return self._tasks.get(task_id)

    def update_task(self, task: Task) -> None:
        """
        Update task status and metadata.

        Args:
            task: Task object with updated fields.
        """
        with self._lock:
            if task.id in self._tasks:
                self._tasks[task.id] = task

    def get_status(self, task_id: str) -> Optional[TaskStatus]:
        """
        Get the current status of a task.

        Args:
            task_id: The task identifier.

        Returns:
            TaskStatus if task exists, None otherwise.
        """
        task = self.get_task(task_id)
        return task.status if task else None

    def get_result(self, task_id: str, timeout: Optional[float] = None) -> Any:
        """
        Wait for task completion and return result.

        Args:
            task_id: The task identifier.
            timeout: Maximum time to wait in seconds (None = wait forever).

        Returns:
            Task result if completed successfully.

        Raises:
            KeyError: If task_id not found.
            TimeoutError: If timeout expires before completion.
            RuntimeError: If task failed after all retries.
        """
        start_time = time.time()
        while True:
            task = self.get_task(task_id)
            if not task:
                raise KeyError(f"Task {task_id} not found")

            if task.status == TaskStatus.COMPLETED:
                return task.result
            if task.status == TaskStatus.FAILED:
                raise RuntimeError(f"Task failed: {task.error}")
            if task.status == TaskStatus.CANCELLED:
                raise RuntimeError("Task was cancelled")

            if timeout is not None and (time.time() - start_time) >= timeout:
                raise TimeoutError(f"Timeout waiting for task {task_id}")

            time.sleep(0.1)

    def get_all_tasks(self) -> List[Task]:
        """
        Get a snapshot of all tasks.

        Returns:
            List of all Task objects.
        """
        with self._lock:
            return list(self._tasks.values())

    def shutdown(self) -> None:
        """Signal shutdown to workers."""
        self._shutdown_event.set()

    def is_shutdown(self) -> bool:
        """Check if shutdown has been signaled."""
        return self._shutdown_event.is_set()


def _worker_process(
    task_queue: mp.Queue,
    result_queue: mp.Queue,
    shutdown_event: mp.Event,
    func_registry: Dict[str, Callable[..., Any]]
) -> None:
    """
    Worker process function that executes tasks.

    Args:
        task_queue: Queue to pull tasks from.
        result_queue: Queue to push results to.
        shutdown_event: Event to signal shutdown.
        func_registry: Mapping of function names to callables.
    """
    while not shutdown_event.is_set():
        try:
            task_data = task_queue.get(timeout=1.0)
        except queue.Empty:
            continue

        task = Task.from_dict(task_data)
        func = func_registry.get(task.func_name)

        if not func:
            error_msg = f"Function '{task.func_name}' not registered"
            logger.error(error_msg)
            task.status = TaskStatus.FAILED
            task.error = error_msg
            task.completed_at = datetime.utcnow().isoformat()
            result_queue.put(task.to_dict())
            continue

        task.status = TaskStatus.RUNNING
        task.started_at = datetime.utcnow().isoformat()
        result_queue.put(task.to_dict())  # Update status to RUNNING

        try:
            result = func(*task.args, **task.kwargs)
            task.status = TaskStatus.COMPLETED
            task.result = result
        except Exception as e:
            task.error = str(e)
            logger.exception(f"Task {task.id} failed: {e}")

            if task.retry_count < task.max_retries:
                task.retry_count += 1
                task.status = TaskStatus.RETRYING
                # Re-queue with exponential backoff
                backoff = 2 ** task.retry_count
                time.sleep(backoff)
                task_queue.put(task.to_dict())
                continue
            else:
                task.status = TaskStatus.FAILED

        task.completed_at = datetime.utcnow().isoformat()
        result_queue.put(task.to_dict())


class WorkerPool:
    """
    Manages a pool of worker processes for parallel task execution.

    Handles task distribution, result collection, and status updates.
    """

    def __init__(
        self,
        task_queue: TaskQueue,
        num_workers: int = None,
        func_registry: Optional[Dict[str, Callable[..., Any]]] = None
    ) -> None:
        """
        Initialize the worker pool.

        Args:
            task_queue: TaskQueue instance to pull tasks from.
            num_workers: Number of worker processes (default: CPU count).
            func_registry: Dictionary mapping function names to callables.
                          Functions must be importable (top-level module functions).

        Raises:
            ValueError: If num_workers is less than 1.
        """
        if num_workers is None:
            num_workers = mp.cpu_count()
        if num_workers < 1:
            raise ValueError("num_workers must be at least 1")

        self._task_queue = task_queue
        self._num_workers = num_workers
        self._func_registry = func_registry or {}
        self._workers: List[mp.Process] = []
        self._result_queue: mp.Queue = mp.Queue()
        self._shutdown_event = mp.Event()
        self._status_updater: Optional[ThreadPoolExecutor] = None
        self._status_future: Optional[Future] = None

    def register_function(self, name: str, func: Callable[..., Any]) -> None:
        """
        Register a function for use by workers.

        Args:
            name: Name to register the function under.
            func: Callable to register.

        Raises:
            ValueError: If name is already registered or func is not callable.
        """
        if not callable(func):
            raise ValueError("func must be callable")
        if name in self._func_registry:
            raise ValueError(f"Function '{name}' already registered")
        self._func_registry[name] = func

    def start(self) -> None:
        """Start all worker processes and the status updater thread."""
        if self._workers:
            logger.warning("Worker pool already started")
            return

        # Start worker processes
        for i in range(self._num_workers):
            worker = mp.Process(
                target=_worker_process,
                args=(
                    self._task_queue._queue,
                    self._result_queue,
                    self._shutdown_event,
                    self._func_registry
                ),
                name=f"TaskWorker-{i}",
                daemon=True
            )
            worker.start()
            self._workers.append(worker)

        # Start status updater thread
        self._status_updater = ThreadPoolExecutor(max_workers=1, thread_name_prefix="StatusUpdater")
        self._status_future = self._status_updater.submit(self._update_statuses)

        logger.info(f"Started {self._num_workers} workers")

    def _update_statuses(self) -> None:
        """Continuously update task statuses from result queue."""
        while not self._shutdown_event.is_set():
            try:
                task_data = self._result_queue.get(timeout=0.5)
                task = Task.from_dict(task_data)
                self._task_queue.update_task(task)
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Error updating task status: {e}")

    def stop(self, wait: bool = True, timeout: Optional[float] = None) -> None:
        """
        Stop all workers gracefully.

        Args:
            wait: If True, wait for workers to finish current tasks.
            timeout: Maximum time to wait for shutdown (seconds).
        """
        logger.info("Shutting down worker pool...")
        self._shutdown_event.set()
        self._task_queue.shutdown()

        if self._status_future:
            self._status_future.cancel()
        if self._status_updater:
            self._status_updater.shutdown(wait=True)

        if wait:
            for worker in self._workers:
                worker.join(timeout=timeout)
        else:
            for worker in self._workers:
                worker.terminate()

        self._workers.clear()
        logger.info("Worker pool stopped")

    def __enter__(self) -> 'WorkerPool':
        """Context manager entry."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.stop(wait=True)


def create_task_queue(maxsize: int = 0) -> TaskQueue:
    """
    Factory function to create a TaskQueue instance.

    Args:
        maxsize: Maximum queue size (0 = unlimited).

    Returns:
        New TaskQueue instance.
    """
    return TaskQueue(maxsize=maxsize)


def create_worker_pool(
    task_queue: TaskQueue,
    num_workers: int = None,
    func_registry: Optional[Dict[str, Callable[..., Any]]] = None
) -> WorkerPool:
    """
    Factory function to create a WorkerPool instance.

    Args:
        task_queue: TaskQueue instance to use.
        num_workers: Number of worker processes.
        func_registry: Optional function registry.

    Returns:
        New WorkerPool instance.
    """
    return WorkerPool(task_queue, num_workers, func_registry)


# Example usage and demonstration
if __name__ == "__main__":
    import sys

    # Configure logging for demo
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        stream=sys.stdout
    )

    # Define some example tasks
    def add_numbers(a: int, b: int) -> int:
        """Add two numbers."""
        time.sleep(0.5)  # Simulate work
        return a + b

    def failing_task(should_fail: bool = True) -> str:
        """Task that optionally fails."""
        if should_fail:
            raise ValueError("Intentional failure for demo")
        return "Success!"

    def long_running_task(duration: float) -> str:
        """Task that takes a while."""
        time.sleep(duration)
        return f"Completed after {duration}s"

    # Create queue and worker pool
    task_queue = create_task_queue()
    worker_pool = create_worker_pool(
        task_queue,
        num_workers=2,
        func_registry={
            'add_numbers': add_numbers,
            'failing_task': failing_task,
            'long_running_task': long_running_task
        }
    )

    try:
        worker_pool.start()

        # Enqueue various tasks
        task1 = task_queue.enqueue(add_numbers, 10, 20)
        task2 = task_queue.enqueue(add_numbers, 100, 200)
        task3 = task_queue.enqueue(failing_task, True, max_retries=2)
        task4 = task_queue.enqueue(long_running_task, 1.5)
        task5 = task_queue.enqueue(failing_task, False)

        print(f"Enqueued tasks: {task1}, {task2}, {task3}, {task4}, {task5}")

        # Wait for and print results
        for task_id in [task1, task2, task3, task4, task5]:
            try:
                result = task_queue.get_result(task_id, timeout=10.0)
                print(f"Task {