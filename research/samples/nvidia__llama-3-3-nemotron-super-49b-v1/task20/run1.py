from asyncio import Queue
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from enum import Enum
from logging import Logger, getLogger
from queue import Empty
from threading import Lock
from time import sleep
from typing import Callable, Dict, Optional

# Using standard library for simplicity; for production, consider Celery or RQ as suggested
class TaskStatus(Enum):
    """Enumeration for task statuses."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    FAILED = "failed"

@dataclass
class Task:
    """Represents a task with a function to execute and arguments."""
    id: str
    func: Callable
    args: tuple
    kwargs: Dict[str, str]
    retries: int = 3  # Default retries
    status: TaskStatus = TaskStatus.PENDING

class DistributedTaskQueue:
    """
    A basic distributed task queue system.

    :warning: This is a simplified example. For production, use Celery or RQ.
    """
    def __init__(self, max_workers: int = 5):
        self.task_queue = Queue()
        self.max_workers = max_workers
        self.task_status: Dict[str, TaskStatus] = {}
        self.logger: Logger = getLogger(__name__)
        self.lock = Lock()

    def add_task(self, task: Task):
        """
        Adds a task to the queue.

        :param task: The task to be added.
        """
        self.task_queue.put(task)
        with self.lock:
            self.task_status[task.id] = task.status
        self.logger.info(f"Task {task.id} added to queue.")

    def _process_task(self, task: Task):
        """
        Executes a task and updates its status.

        :param task: The task to process.
        """
        try:
            with self.lock:
                self.task_status[task.id] = TaskStatus.IN_PROGRESS
            task.func(*task.args, **task.kwargs)
            with self.lock:
                self.task_status[task.id] = TaskStatus.SUCCESS
            self.logger.info(f"Task {task.id} succeeded.")
        except Exception as e:
            with self.lock:
                self.task_status[task.id] = TaskStatus.FAILED
            self.logger.error(f"Task {task.id} failed: {e}. Retrying {task.retries} times.")
            self._retry_task(task)

    def _retry_task(self, task: Task):
        """
        Retries a failed task.

        :param task: The task to retry.
        """
        if task.retries > 0:
            sleep(1)  # Simple backoff strategy
            self.logger.info(f"Retrying task {task.id} with {task.retries} retries left.")
            task.retries -= 1
            self.task_queue.put(task)  # Put back into queue for retry
        else:
            self.logger.warning(f"Task {task.id} failed after all retries.")

    def start_workers(self):
        """
        Starts worker threads to process tasks in parallel.
        """
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            while True:
                try:
                    task = self.task_queue.get(block=False)
                except Empty:
                    # No tasks, wait briefly before checking again
                    sleep(0.5)
                    continue
                executor.submit(self._process_task, task)
                self.task_queue.task_done()

    def get_task_status(self, task_id: str) -> Optional[TaskStatus]:
        """
        Retrieves the status of a task.

        :param task_id: ID of the task.
        :return: Task status if found, otherwise None.
        """
        with self.lock:
            return self.task_status.get(task_id)

# Example usage
if __name__ == "__main__":
    import sys

    def example_task(name: str):
        """Example task that might fail."""
        import random
        if random.choice([True, False]):
            raise RuntimeError("Simulated failure")
        print(f"Hello, {name}!")

    if len(sys.argv) > 1 and sys.argv[1] == "worker":
        # Run as worker
        queue = DistributedTaskQueue()
        queue.start_workers()
    else:
        # Add tasks and query status
        queue = DistributedTaskQueue()
        task1 = Task("task1", example_task, ("World",), {})
        task2 = Task("task2", example_task, ("Universe",), {})

        # Simulate adding tasks and starting workers in separate threads/processes
        queue.add_task(task1)
        queue.add_task(task2)

        # For demonstration, manually start a worker in this thread
        import threading
        worker_thread = threading.Thread(target=queue.start_workers)
        worker_thread.daemon = True  # So it exits when main thread finishes
        worker_thread.start()

        # Wait a bit for tasks to process
        sleep(2)

        print(queue.get_task_status("task1"))
        print(queue.get_task_status("task2"))