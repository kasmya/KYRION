import redis
from typing import Callable, Dict, List
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
import json
import time

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Set up Redis connection
redis_client = redis.Redis(host='localhost', port=6379, db=0)

@dataclass
class Task:
    """Represents a task in the queue."""
    id: str
    function: Callable
    args: List
    kwargs: Dict
    retries: int = 0
    status: str = 'pending'
    created_at: datetime = datetime.now()

class TaskQueue:
    """A distributed task queue system."""
    def __init__(self, name: str):
        self.name = name

    def add_task(self, task: Task):
        """Add a task to the queue."""
        task_data = {
            'id': task.id,
            'function': task.function.__name__,
            'args': task.args,
            'kwargs': task.kwargs,
            'retries': task.retries,
            'status': task.status,
            'created_at': task.created_at.isoformat()
        }
        redis_client.rpush(self.name, json.dumps(task_data))
        logger.info(f'Task {task.id} added to queue {self.name}')

    def process_tasks(self, num_workers: int):
        """Process tasks in parallel using workers."""
        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            while True:
                task_data = redis_client.lpop(self.name)
                if task_data is None:
                    break
                task_data = json.loads(task_data)
                task = Task(
                    id=task_data['id'],
                    function=getattr(__import__('builtins'), task_data['function']),
                    args=task_data['args'],
                    kwargs=task_data['kwargs'],
                    retries=task_data['retries'],
                    status=task_data['status'],
                    created_at=datetime.fromisoformat(task_data['created_at'])
                )
                executor.submit(self._process_task, task)

    def _process_task(self, task: Task):
        """Process a single task."""
        try:
            task.function(*task.args, **task.kwargs)
            task.status = 'success'
            self._update_task_status(task)
            logger.info(f'Task {task.id} succeeded')
        except Exception as e:
            task.retries += 1
            task.status = 'failed'
            self._update_task_status(task)
            logger.error(f'Task {task.id} failed with error: {str(e)}')
            if task.retries < 3:  # Retry failed tasks up to 3 times
                self.add_task(task)
            else:
                logger.error(f'Task {task.id} failed after 3 retries')

    def _update_task_status(self, task: Task):
        """Update the status of a task."""
        task_data = {
            'id': task.id,
            'function': task.function.__name__,
            'args': task.args,
            'kwargs': task.kwargs,
            'retries': task.retries,
            'status': task.status,
            'created_at': task.created_at.isoformat()
        }
        redis_client.hset(f'task:{task.id}', 'data', json.dumps(task_data))

def example_function(x: int, y: int) -> int:
    """An example function that adds two numbers."""
    return x + y

if __name__ == '__main__':
    queue = TaskQueue('my_queue')
    task = Task(
        id='task_1',
        function=example_function,
        args=[2, 3],
        kwargs={},
        retries=0,
        status='pending',
        created_at=datetime.now()
    )
    queue.add_task(task)
    queue.process_tasks(5)