# Import required packages
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from enum import Enum
from functools import wraps
from logging import getLogger, ERROR
from queue import Queue
from threading import Lock
from time import sleep
from typing import Callable, Any

# Set up logging
getLogger("task_queue").setLevel(ERROR)

# Define task status enum
class TaskStatus(Enum):
    """Enum for task statuses."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    FAILURE = "failure"

# Define task dataclass
@dataclass
class Task:
    """Dataclass for tasks."""
    id: int
    func: Callable
    args: tuple[Any, ...]
    kwargs: dict[str, Any]
    status: TaskStatus = TaskStatus.PENDING
    retries: int = 0
    max_retries: int = 3

# Define task queue class
class TaskQueue:
    """Class for a distributed task queue system."""
    def __init__(self, num_workers: int = 5):
        """Initialize the task queue with a specified number of workers."""
        self.task_id_counter = 0
        self.lock = Lock()
        self.queue = Queue()
        self.workers = ThreadPoolExecutor(max_workers=num_workers)
        self.tasks: dict[int, Task] = {}

    def add_task(self, func: Callable, *args: Any, **kwargs: Any) -> int:
        """Add a task to the queue and return its ID."""
        with self.lock:
            task_id = self.task_id_counter
            self.task_id_counter += 1
            task = Task(task_id, func, args, kwargs)
            self.tasks[task_id] = task
            self.queue.put(task)
            return task_id

    def process_tasks(self):
        """Process tasks in the queue."""
        while True:
            task = self.queue.get()
            try:
                self._process_task(task)
            except Exception as e:
                getLogger("task_queue").error(f"Error processing task {task.id}: {e}")
            finally:
                self.queue.task_done()

    def _process_task(self, task: Task):
        """Process a single task."""
        if task.retries < task.max_retries:
            try:
                task.status = TaskStatus.IN_PROGRESS
                result = task.func(*task.args, **task.kwargs)
                task.status = TaskStatus.SUCCESS
                return result
            except Exception as e:
                task.retries += 1
                task.status = TaskStatus.FAILURE
                getLogger("task_queue").warning(f"Task {task.id} failed (retry {task.retries}/{task.max_retries}): {e}")
                sleep(1)  # Wait before retrying
                self.queue.put(task)  # Retry the task
        else:
            task.status = TaskStatus.FAILURE
            getLogger("task_queue").error(f"Task {task.id} failed permanently after {task.max_retries} retries")

    def get_task_status(self, task_id: int) -> TaskStatus:
        """Get the status of a task."""
        return self.tasks.get(task_id, Task(0, lambda: None, (), {})).status

# Decorator for retrying failed tasks
def retry_on_failure(max_retries: int = 3):
    """Decorator to retry a function on failure."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt < max_retries:
                        getLogger("task_queue").warning(f"Attempt {attempt+1}/{max_retries+1} failed for {func.__name__}: {e}")
                        sleep(1)  # Wait before retrying
                    else:
                        raise
        return wrapper
    return decorator

# Example usage
if __name__ == "__main__":
    def example_task(name: str) -> str:
        """Example task that may fail."""
        import random
        if random.random() < 0.5:
            raise RuntimeError("Simulated failure")
        return f"Hello, {name}!"

    task_queue = TaskQueue()
    task_id = task_queue.add_task(example_task, "John")
    print(f"Task ID: {task_id}, Status: {task_queue.get_task_status(task_id)}")

    # Start a worker thread
    import threading
    worker_thread = threading.Thread(target=task_queue.process_tasks)
    worker_thread.daemon = True
    worker_thread.start()

    # Wait for the task to complete
    sleep(2)
    print(f"Task ID: {task_id}, Status: {task_queue.get_task_status(task_id)}")