import logging
from logging.config import dictConfig
from typing import Callable, Dict, List, Optional
from queue import Queue
from threading import Thread, Event
import time
import uuid
from datetime import datetime

# Define logging configuration
logging_config = {
    'version': 1,
    'formatters': {
        'default': {
            'format': '[%(asctime)s] %(levelname)s in %(module)s: %(message)s',
        }
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'stream': 'ext://sys.stdout',
            'formatter': 'default'
        }
    },
    'root': {
        'level': 'INFO',
        'handlers': ['console']
    }
}

# Apply logging configuration
dictConfig(logging_config)

class Task:
    """Represents a task with a unique ID and a callable function."""
    def __init__(self, func: Callable, *args, **kwargs):
        self.id = str(uuid.uuid4())
        self.func = func
        self.args = args
        self.kwargs = kwargs
        self.status = 'pending'
        self.retry_count = 0

    def run(self) -> None:
        """Runs the task and updates its status."""
        try:
            self.func(*self.args, **self.kwargs)
            self.status = 'success'
        except Exception as e:
            self.status = 'failed'
            self.retry_count += 1
            logging.error(f'Task {self.id} failed: {str(e)}')

class Worker(Thread):
    """A worker thread that processes tasks from a queue."""
    def __init__(self, queue: Queue, max_retries: int = 3):
        super().__init__()
        self.queue = queue
        self.max_retries = max_retries
        self.stop_event = Event()

    def run(self) -> None:
        """Runs the worker thread."""
        while not self.stop_event.is_set():
            task: Optional[Task] = self.queue.get()
            if task is None:
                break
            if task.retry_count < self.max_retries:
                task.run()
                if task.status == 'failed':
                    self.queue.put(task)
            else:
                logging.error(f'Task {task.id} failed after {self.max_retries} retries')
            self.queue.task_done()

class TaskQueue:
    """A distributed task queue system."""
    def __init__(self, num_workers: int = 5, max_retries: int = 3):
        self.queue = Queue()
        self.num_workers = num_workers
        self.max_retries = max_retries
        self.workers: List[Worker] = []

    def add_task(self, func: Callable, *args, **kwargs) -> Task:
        """Adds a task to the queue."""
        task = Task(func, *args, **kwargs)
        self.queue.put(task)
        return task

    def start(self) -> None:
        """Starts the task queue system."""
        for _ in range(self.num_workers):
            worker = Worker(self.queue, self.max_retries)
            worker.start()
            self.workers.append(worker)

    def stop(self) -> None:
        """Stops the task queue system."""
        for worker in self.workers:
            worker.stop_event.set()
        for worker in self.workers:
            worker.join()

# Example usage
def example_task(name: str) -> None:
    """An example task that prints a message."""
    print(f'Hello, {name}!')

if __name__ == '__main__':
    task_queue = TaskQueue(num_workers=5)
    task_queue.start()

    task1 = task_queue.add_task(example_task, 'Alice')
    task2 = task_queue.add_task(example_task, 'Bob')

    time.sleep(2)  # Wait for tasks to complete

    task_queue.stop()

    print(f'Task {task1.id} status: {task1.status}')
    print(f'Task {task2.id} status: {task2.status}')