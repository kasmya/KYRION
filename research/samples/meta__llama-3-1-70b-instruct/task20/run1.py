import logging
import os
import random
import string
import time
from datetime import datetime, timedelta
from enum import Enum
from typing import Callable, List, Optional

import redis
from celery import Celery, Task
from celery.exceptions import Reject
from celery.utils.log import get_task_logger

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = get_task_logger(__name__)

# Initialize Celery and Redis
CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'redis://localhost:6379/0')
app = Celery('tasks', broker=CELERY_BROKER_URL)

class TaskStatus(Enum):
    PENDING = 'pending'
    RUNNING = 'running'
    SUCCESS = 'success'
    FAILURE = 'failure'
    RETRYING = 'retrying'

def create_task_id(length: int = 12) -> str:
    """Create a random task ID."""
    return ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(length))

class DistributedTask(Task):
    """Distributed task class."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.task_id = create_task_id()

    def __call__(self, *args, **kwargs):
        """Override the __call__ method to set the task status to running."""
        self.update_state(state=TaskStatus.RUNNING.value)
        return super().__call__(*args, **kwargs)

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Handle task failure."""
        self.update_state(state=TaskStatus.FAILURE.value)
        logger.error(f'Task {task_id} failed: {exc}')

    def on_success(self, retval, task_id, args, kwargs):
        """Handle task success."""
        self.update_state(state=TaskStatus.SUCCESS.value)
        logger.info(f'Task {task_id} succeeded')

    def on_retry(self, exc, task_id, args, kwargs, einfo):
        """Handle task retry."""
        self.update_state(state=TaskStatus.RETRYING.value)
        logger.info(f'Task {task_id} retrying')

    def update_state(self, state: str):
        """Update the task status."""
        redis_client = redis.Redis(host='localhost', port=6379, db=0)
        redis_client.hset(self.task_id, 'state', state)

def process_task(task_id: str, func: Callable, *args, **kwargs):
    """Process a task."""
    try:
        result = func(*args, **kwargs)
        return result
    except Exception as e:
        raise Reject(e, requeue=True)

@app.task(base=DistributedTask, bind=True)
def example_task(self, *args, **kwargs):
    """Example task."""
    logger.info(f'Running task {self.task_id}')
    time.sleep(2)
    logger.info(f'Task {self.task_id} completed')

def add_task(func: Callable, *args, **kwargs) -> str:
    """Add a task to the queue."""
    task_id = create_task_id()
    redis_client = redis.Redis(host='localhost', port=6379, db=0)
    redis_client.hset(task_id, 'state', TaskStatus.PENDING.value)
    result = app.apply_async((func, args, kwargs), task_id=task_id)
    return task_id

def get_task_status(task_id: str) -> Optional[TaskStatus]:
    """Get the task status."""
    redis_client = redis.Redis(host='localhost', port=6379, db=0)
    state = redis_client.hget(task_id, 'state')
    if state is None:
        return None
    return TaskStatus(state.decode('utf-8'))

if __name__ == '__main__':
    task_id = add_task(example_task)
    logger.info(f'Task ID: {task_id}')
    status = get_task_status(task_id)
    logger.info(f'Task status: {status}')