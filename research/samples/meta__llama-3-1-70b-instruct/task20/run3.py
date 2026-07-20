from typing import Callable, Dict, List
from dataclasses import dataclass
from enum import Enum
from queue import Queue
from threading import Thread, Lock
from time import sleep
from traceback import format_exc
import logging
import os
import uuid

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TaskStatus(Enum):
    """Enum representing task status"""
    PENDING = 1
    RUNNING = 2
    SUCCESS = 3
    FAILED = 4

@dataclass
class Task:
    """Dataclass representing a task"""
    id: str
    func: Callable
    args: List
    kwargs: Dict
    max_retries: int
    status: TaskStatus
    result: str = None

class TaskQueue:
    """Class representing a task queue"""
    def __init__(self, max_workers: int):
        self.queue = Queue()
        self.workers = []
        self.task_lock = Lock()
        self.tasks: Dict[str, Task] = {}
        for _ in range(max_workers):
            worker = Thread(target=self.worker_loop)
            worker.daemon = True
            worker.start()
            self.workers.append(worker)

    def add_task(self, func: Callable, *args, **kwargs):
        """Add a task to the queue"""
        task_id = str(uuid.uuid4())
        task = Task(task_id, func, list(args), kwargs, 3, TaskStatus.PENDING)
        with self.task_lock:
            self.tasks[task_id] = task
            self.queue.put(task)
        return task_id

    def worker_loop(self):
        """Worker loop to process tasks"""
        while True:
            task = self.queue.get()
            try:
                task.status = TaskStatus.RUNNING
                result = task.func(*task.args, **task.kwargs)
                task.status = TaskStatus.SUCCESS
                task.result = str(result)
            except Exception as e:
                task.status = TaskStatus.FAILED
                logger.error(f"Task {task.id} failed: {format_exc()}")
                if task.max_retries > 0:
                    task.max_retries -= 1
                    task.status = TaskStatus.PENDING
                    self.queue.put(task)
            finally:
                self.queue.task_done()

    def get_task_status(self, task_id: str):
        """Get the status of a task"""
        with self.task_lock:
            task = self.tasks.get(task_id)
            if task:
                return task.status
            else:
                return None

def example_task(x: int, y: int):
    """Example task function"""
    sleep(1)  # Simulate some work
    return x + y

if __name__ == "__main__":
    queue = TaskQueue(5)  # Create a task queue with 5 workers
    task_id = queue.add_task(example_task, 2, 3)
    print(f"Task {task_id} added")
    print(f"Task {task_id} status: {queue.get_task_status(task_id)}")